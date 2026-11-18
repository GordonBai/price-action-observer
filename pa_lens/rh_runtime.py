"""Active read-only acquisition: provider evidence is separate from local analysis."""
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from .core import Bar
from pathlib import Path
import json
from .robinhood import INTERVAL_MINUTES, RobinhoodError


def source_identity(interval, bounds='regular', adjustment_type='split', accept_unknown=False):
    period='15minute-derived-5minute' if interval=='15minute' else interval
    return f'robinhood:{period}:{bounds}:{adjustment_type}'+(':accept_unknown' if accept_unknown else '')


def quality_status(quality):
    if quality.get('interpolation_unknown', 0):
        return 'DATA_QUALITY_UNKNOWN'
    if not quality.get('emitted', 0):
        return 'NO_USABLE_BARS'
    if any(quality.get(k) for k in ('invalid','interpolated','missing_results','no_usable_symbols','out_of_range','incomplete_derived_buckets')):
        return 'PARTIAL_DATA'
    return 'ELIGIBLE_OBSERVATIONS'


def acquire(provider, journal, symbols, start, end, *, interval='minute', bounds='regular',
            adjustment_type='split', accept_unknown=False, capture_dir=None, include_quotes=False):
    if capture_dir:
        path=Path(capture_dir).expanduser().resolve()
        # Captures may contain licensed market data: never place in a tracked tree.
        repo=Path(__file__).resolve().parents[1]
        if path==repo or (repo in path.parents and repo/'local_data' not in (path,*path.parents)):
            raise ValueError('captures inside project must use ignored local_data/')
    source=source_identity(interval,bounds,adjustment_type,accept_unknown)
    timeframe='15' if interval=='15minute' else str(INTERVAL_MINUTES.get(interval, 'D'))
    actual_interval='5minute' if interval=='15minute' else interval
    if interval=='15minute' and bounds!='regular':raise ValueError('derived 15minute requires regular bounds')
    try:
        result=provider.fetch(symbols,start,end,interval=actual_interval,bounds=bounds,
                              adjustment_type=adjustment_type,accept_unknown=accept_unknown)
    except (RobinhoodError,ValueError):
        for symbol in symbols:
            journal.record_transport(source,symbol,'error',datetime.now(timezone.utc),0,timeframe=timeframe)
        raise
    if interval=='15minute':result=aggregate_fifteen(result)
    received=datetime.now(timezone.utc).isoformat()
    status=quality_status(result.quality)
    evidence=dict(source=result.source,symbols=list(symbols),timeframe=timeframe,received_at=received,
                  cutoff=result.cutoff,status=status,quality=result.quality,batches=list(result.batches),
                  bar_provenance=list(result.bar_provenance))
    acquisition_id=journal.record_acquisition(evidence)
    counts=dict(ingested=0,duplicates=0,quarantined=0)
    for bar in result.bars:
        item=journal.ingest_observation(asdict(bar))
        if item['quarantined']:counts['quarantined']+=1
        elif item['duplicate']:counts['duplicates']+=1
        else:counts['ingested']+=1
    for symbol in symbols:
        rows=sum(b.symbol==symbol for b in result.bars)
        journal.record_transport(result.source,symbol,'success' if rows else 'empty',received,rows,timeframe=timeframe)
    quotes=None
    if include_quotes:
        # Quotes are evidence only, never replacement OHLC or indicator inputs.
        q=provider.quotes(symbols)
        quotes=dict(raw_records=q.raw_records,batches=q.batches,quality=q.quality,
                    freshness='PROVIDER_TIMESTAMPS_NOT_INDEPENDENTLY_VERIFIED')
    if capture_dir:
        path.mkdir(parents=True,exist_ok=True)
        capture={**evidence,'raw_records':result.raw_records,'bars':[asdict(b) for b in result.bars],
                 'provider_quotes':quotes,'provider_indicators':'NOT_REQUESTED'}
        (path/f'acquisition-{acquisition_id}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json').write_text(
            json.dumps(capture,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(acquisition_id=acquisition_id,source=result.source,status=status,quality=result.quality,
                **counts,provider_quotes=quotes,provider_indicators='NOT_REQUESTED',live_verified=False,
                notice='Local EMA/RSI and PA observations are not provider indicators or verified predictive signals.')


def aggregate_fifteen(result):
    """Only complete 09:30 ET-anchored RTH triples; never fill absent input bars."""
    if not result.source.startswith('robinhood:5minute:regular:'):
        raise ValueError('derived 15minute requires regular five-minute input')
    source=result.source.replace(':5minute:',':15minute-derived-5minute:',1)
    groups={}; provenance={(p['symbol'],p['time']):p for p in result.bar_provenance}
    for bar in result.bars:
        closed=datetime.fromisoformat(bar.time.replace('Z','+00:00'))
        opened=(closed-timedelta(minutes=5)).astimezone(ZoneInfo('America/New_York'))
        minute=opened.hour*60+opened.minute-570
        if not 0<=minute<390 or minute%5 or opened.second or opened.microsecond:
            continue
        bucket=opened.replace(hour=9,minute=30,second=0,microsecond=0)+timedelta(minutes=(minute//15)*15)
        groups.setdefault((bar.symbol,bucket),[]).append(bar)
    bars=[];out_provenance=[];incomplete=0
    for (symbol,opened),parts in sorted(groups.items()):
        parts.sort(key=lambda b:b.time)
        expected=[(opened+timedelta(minutes=m)).astimezone(timezone.utc) for m in (5,10,15)]
        if len(parts)!=3 or [datetime.fromisoformat(b.time.replace('Z','+00:00')) for b in parts]!=expected:
            incomplete+=1;continue
        # Calendar validates regular-session close, including scheduled early closes.
        from .timeframes import calendar
        label=opened.date().isoformat()
        if not calendar().is_session(label) or expected[-1]>calendar().session_close(label).to_pydatetime():
            incomplete+=1;continue
        closed=expected[-1].isoformat()
        bars.append(Bar(symbol,'15',closed,parts[0].open,max(b.high for b in parts),min(b.low for b in parts),parts[-1].close,sum(b.volume for b in parts),source))
        inputs=[provenance[(b.symbol,b.time)] for b in parts]
        unknown=any(p['quality']=='DATA_QUALITY_UNKNOWN' for p in inputs)
        out_provenance.append(dict(symbol=symbol,time=closed,opened_at=opened.astimezone(timezone.utc).isoformat(),
            session_date=label,derived_from='5minute',input_bar_closes=[b.time for b in parts],
            input_provenance=inputs,quality='DATA_QUALITY_UNKNOWN' if unknown else 'INTERPOLATION_EXPLICIT_FALSE',
            interpolation='unknown' if unknown else 'explicit_false'))
    quality=dict(result.quality,source_bars_emitted=result.quality['emitted'],emitted=len(bars),
                 incomplete_derived_buckets=incomplete,derived_from='5minute',
                 derived_unknown_emitted=sum(p['quality']=='DATA_QUALITY_UNKNOWN' for p in out_provenance),
                 source_quality_count_unit='five_minute_input_bars',derived_count_unit='fifteen_minute_bars')
    quality['no_usable_symbols']=sorted({row['symbol'] for row in result.raw_records}-{bar.symbol for bar in bars})
    return replace(result,bars=tuple(bars),bar_provenance=tuple(out_provenance),source=source,quality=quality)


def next_poll_delay(now, interval, settle_seconds=10):
    """Next 09:30 ET-anchored intraday grid or XNYS daily session close plus settling delay.

    This scheduling helper does not assert a provider's actual publication latency.
    """
    import math
    if not math.isfinite(settle_seconds) or not 0<=settle_seconds<=300:
        raise ValueError('settle seconds must be 0..300')
    if interval=='day':
        from .timeframes import next_daily_close
        return next_daily_close(now,settle_seconds)
    seconds=900 if interval=='15minute' else INTERVAL_MINUTES[interval]*60
    stamp=now.timestamp()
    origin=now.astimezone(ZoneInfo('America/New_York')).replace(hour=9,minute=30,second=0,microsecond=0).timestamp()
    boundary=origin+(math.floor((stamp-origin-settle_seconds)/seconds)+1)*seconds+settle_seconds
    return max(0,boundary-stamp)


def poll_start(end, interval, lookback_minutes, last_closes, expected_streams=None, coverage_start=None):
    """Consistent aligned overlap, clamped to the first requested coverage boundary."""
    import math
    overlap=timedelta(days=7) if interval=='day' else timedelta(minutes=lookback_minutes)
    if not last_closes or (expected_streams is not None and len(last_closes)<expected_streams):
        start=end-(timedelta(days=180) if interval=='day' else overlap)
    else:
        oldest=min(datetime.fromisoformat(t.replace('Z','+00:00')) for t in last_closes)
        start=min(end-overlap,oldest-overlap)
    seconds=86400 if interval=='day' else 900 if interval=='15minute' else INTERVAL_MINUTES[interval]*60
    origin=0 if interval=='day' else start.astimezone(ZoneInfo('America/New_York')).replace(hour=9,minute=30,second=0,microsecond=0).timestamp()
    start=datetime.fromtimestamp(origin+math.floor((start.timestamp()-origin)/seconds)*seconds,timezone.utc)
    if coverage_start:
        start=max(start,datetime.fromisoformat(coverage_start.replace('Z','+00:00')))
    return start


def poll_windows(journal, symbols, end, interval, lookback_minutes, source, explicit_start=None):
    """Group symbols with equal ranges; new symbols never widen existing histories."""
    timeframe='15' if interval=='15minute' else str(INTERVAL_MINUTES.get(interval,'D'))
    groups={}
    for symbol in symbols:
        stream=journal.streams.get((symbol,timeframe,source))
        closes=[stream['bars'][-1]['time']] if stream else []
        start=explicit_start if explicit_start is not None else poll_start(end,interval,lookback_minutes,closes,
                     coverage_start=journal.coverage_start(symbol,timeframe,source))
        groups.setdefault(start,[]).append(symbol)
    return [(names,start) for start,names in groups.items()]
