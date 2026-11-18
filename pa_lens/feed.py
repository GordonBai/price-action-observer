"""Alpaca completed-minute polling adapter; no trading endpoints or credential storage.

Network entitlement is not established by offline tests. Never silently replace SIP
with IEX: feed choice is explicit and recorded in the bar stream identity.
"""
from datetime import datetime,timedelta,timezone,time
from zoneinfo import ZoneInfo
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError
from dataclasses import asdict
import json
import re
from .core import Bar,parse_time


class FeedError(RuntimeError):pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None  # Never forward API credentials to a redirect target.


def _transport(url,headers):
    request=Request(url,headers=headers)
    with build_opener(_NoRedirect()).open(request,timeout=15) as response:
        payload=response.read(8*1024*1024+1)
        if len(payload)>8*1024*1024:raise FeedError('provider response exceeds 8MB')
        return json.loads(payload)


class AlpacaFeed:
    def __init__(self,key_id,secret,feed='sip',transport=None):
        if not key_id or not secret:raise ValueError('APCA_API_KEY_ID and APCA_API_SECRET_KEY must be configured locally')
        if feed not in ('sip','iex'):raise ValueError('feed must explicitly be sip or iex')
        self.feed=feed;self._headers={'APCA-API-KEY-ID':key_id,'APCA-API-SECRET-KEY':secret};self._transport=transport or _transport

    def fetch(self,symbol,start,end):
        if not re.fullmatch(r'[A-Z0-9.\-]{1,20}',symbol):raise ValueError('invalid US equity symbol')
        parse_time(start);parse_time(end)
        query={'symbols':symbol,'timeframe':'1Min','start':start,'end':end,'limit':10000,'adjustment':'raw','feed':self.feed,'sort':'asc'}
        seen=set()
        for _ in range(100):
            url='https://data.alpaca.markets/v2/stocks/bars?'+urlencode(query)
            try:result=self._transport(url,self._headers)
            except HTTPError as ex:
                raise FeedError(f'Alpaca HTTP {ex.code}; check credentials, subscription and rate limits; no feed fallback attempted') from None
            except Exception:
                raise FeedError('Alpaca transport failed; secrets and provider error body suppressed') from None
            if not isinstance(result,dict) or not isinstance(result.get('bars'),dict):raise FeedError('invalid Alpaca bars response')
            rows=result['bars'].get(symbol,[])
            if rows is None:rows=[]
            if not isinstance(rows,list):raise FeedError('invalid Alpaca symbol bars')
            yield from rows
            token=result.get('next_page_token')
            if not token:return
            if not isinstance(token,str) or token in seen:raise FeedError('invalid/repeated pagination token')
            seen.add(token);query['page_token']=token
        raise FeedError('pagination limit reached; shorten requested lookback')


def normalize_alpaca(symbol,row,feed,now,grace_seconds=3,rth_only=True):
    """Raw t is bar-open; closed and settled-enough bars only. Returns None to skip."""
    if now.tzinfo is None:raise ValueError('now must be timezone-aware')
    try:
        opened=parse_time(row['t']);closed=opened+timedelta(minutes=1)
        if closed>now-timedelta(seconds=grace_seconds):return None
        local=opened.astimezone(ZoneInfo('America/New_York'))
        if rth_only and (local.weekday()>=5 or not time(9,30)<=local.time().replace(tzinfo=None)<time(16,0)):return None
        return Bar(symbol,'1',closed.isoformat(),row['o'],row['h'],row['l'],row['c'],row.get('v',0),'alpaca:'+feed+':raw')
    except (KeyError,TypeError) as ex:raise ValueError('invalid Alpaca bar fields') from ex


class Poller:
    def __init__(self,feed,journal,symbol,lookback_minutes=120,rth_only=True):
        if not isinstance(lookback_minutes,int) or not 1<=lookback_minutes<=10080:raise ValueError('lookback_minutes must be 1..10080')
        self.feed=feed;self.journal=journal;self.symbol=symbol;self.lookback_minutes=lookback_minutes;self.rth_only=rth_only

    def poll(self,now=None):
        now=now or datetime.now(timezone.utc)
        start=now-timedelta(minutes=self.lookback_minutes)
        source='alpaca:'+self.feed.feed+':raw'
        streams=self.journal.snapshot(now)['streams']
        matching=[s for s in streams if s['symbol']==self.symbol and s['timeframe']=='1' and s['source']==source]
        if matching:start=min(start,parse_time(matching[0]['last_bar_close'])-timedelta(minutes=1))
        inserted=duplicates=skipped=quarantined=rows=0
        try:
            for row in self.feed.fetch(self.symbol,start.isoformat(),(now-timedelta(seconds=3)).isoformat()):
                rows+=1
                bar=normalize_alpaca(self.symbol,row,self.feed.feed,now,rth_only=self.rth_only)
                if bar is None:skipped+=1;continue
                outcome=self.journal.ingest_observation(asdict(bar))
                if outcome.get('quarantined'):quarantined+=1
                elif outcome['duplicate']:duplicates+=1
                else:inserted+=1
        except (FeedError,ValueError) as exc:
            self.journal.record_transport(source,self.symbol,'error',now.isoformat(),rows,error='provider_or_ingestion_validation_error')
            raise FeedError('Provider/ingestion validation failed; original journal preserved; inspect audit and retry.') from None
        self.journal.record_transport(source,self.symbol,'success' if rows else 'empty',now.isoformat(),rows)
        health=self.journal.health(now)
        return {'inserted':inserted,'duplicates':duplicates,'quarantined':quarantined,'skipped':skipped,'feed':self.feed.feed,'source':source,
                'checked_at':now.isoformat(),'health':health,'notice':'Historical/recent REST bars, not tick streaming; verify entitlement and latency separately.'}


def connector_bars(payload,symbol,expected_feed,now,*,retrieved_at):
    """Validate a saved get_stock_bars *structured* connector result.

    This is an import bridge, not connector authentication or a scheduler. Feed
    must be explicit; connector adjustment is unknown and must never be labeled
    raw. Caller stores the request/response and receipt time privately. Entire
    batch is validated before returning, then normal Journal rules still apply.
    """
    from dataclasses import replace
    if expected_feed not in ('iex','sip','delayed_sip'):raise ValueError('explicit supported connector feed required')
    if not isinstance(payload,dict) or payload.get('tool')!='get_stock_bars' or 'error' in payload:
        raise ValueError('expected successful get_stock_bars structured result')
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:raise ValueError('retrieved_at must be timezone aware')
    validation_time=min(now,retrieved_at)
    request=payload.get('request',{})
    if request.get('feed')!=expected_feed or request.get('timeframe')!='1Min' or request.get('symbols')!=[symbol]:
        raise ValueError('connector request provenance does not match symbol/feed/1Min')
    rows=payload.get('bars',{}).get(symbol)
    if not isinstance(rows,list):raise ValueError('connector bars missing')
    result=[];last=None
    for row in rows:
        if not isinstance(row,dict) or row.get('symbol')!=symbol:raise ValueError('mixed or missing connector symbol')
        try:
            stamp=parse_time(row['timestamp'])
            if last is not None and stamp<=last:raise ValueError('connector rows must be strictly ordered without revisions')
            last=stamp
            raw={a:row[b] for a,b in [('t','timestamp'),('o','open'),('h','high'),('l','low'),('c','close'),('v','volume')]}
        except (KeyError,TypeError) as exc:raise ValueError('invalid connector fields') from exc
        bar=normalize_alpaca(symbol,raw,expected_feed,validation_time)
        if bar is not None:result.append(replace(bar,source='alpaca-connector:'+expected_feed+':adjustment_unverified'))
    return result


def connector_import_main(argv=None):
    """One-shot local import, not a daemon; obtains no credentials."""
    import argparse
    from pathlib import Path
    from .service import Journal
    parser=argparse.ArgumentParser(description='Import a saved Alpaca connector result; does NOT schedule or authenticate a feed')
    parser.add_argument('input',type=Path)
    parser.add_argument('--feed',choices=('iex','sip','delayed_sip'),required=True)
    parser.add_argument('--symbol',default='SOXL')
    parser.add_argument('--captured-at',required=True,help='conservative pre-request clock, ISO timezone required; not later import time')
    parser.add_argument('--db',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        now=datetime.now(timezone.utc)
        captured=parse_time(args.captured_at)
        if captured>now:raise ValueError('capture clock is in the future')
        bars=connector_bars(json.loads(args.input.read_text()),args.symbol,args.feed,now,retrieved_at=captured)
        args.db.parent.mkdir(parents=True,exist_ok=True)
        journal=Journal(args.db)
        try:
            outcomes=[journal.ingest_observation(asdict(bar)) for bar in bars]
            print(json.dumps({'accepted_closed_rows':len(bars),'inserted':sum(not x['duplicate'] and not x.get('quarantined') for x in outcomes),
                'duplicates':sum(x['duplicate'] and not x.get('quarantined') for x in outcomes),'quarantined':sum(bool(x.get('quarantined')) for x in outcomes),'captured_at':captured.isoformat(),
                'checked_at':now.isoformat(),'feed':args.feed,'health':journal.health(now),
                'mode':'one_shot_connector_import_not_continuous_service'},ensure_ascii=False))
        finally:journal.close()
    except (OSError,ValueError) as ex:parser.error(str(ex))


if __name__=='__main__':connector_import_main()
