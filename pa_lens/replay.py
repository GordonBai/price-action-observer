"""Causal replay and explicitly hypothetical, long-only OHLC execution estimates.

This is not a broker, fill simulator with tick precision, or profitability claim.
All event and bar timestamps denote availability / interval close, not exact fills.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, time, timedelta
import csv
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import Bar, Config, Engine, parse_time

NY = ZoneInfo('America/New_York')


def _validated(bars):
    """Validate one stream in input order and remove identical adjacent duplicates."""
    out = []
    for b in bars:
        if not isinstance(b, Bar):
            raise ValueError('expected Bar objects')
        if out:
            prev = out[-1]
            if (b.symbol, b.timeframe, b.source) != (prev.symbol, prev.timeframe, prev.source):
                raise ValueError('mixed bar streams')
            if parse_time(b.time) < parse_time(prev.time):
                raise ValueError('out-of-order bars; input is not silently sorted')
            if b.time == prev.time:
                if b == prev:
                    continue
                raise ValueError('conflicting revision; choose an explicit data version')
        out.append(b)
    return out


def load_bars(path, *, open_time_minutes=None):
    """Read canonical JSONL or CSV. `time` is UTC/aware bar CLOSE, not open time."""
    if open_time_minutes is not None and (isinstance(open_time_minutes,bool) or not isinstance(open_time_minutes,int) or not 1 <= open_time_minutes <= 240):
        raise ValueError('open_time_minutes must be integer 1..240')
    def normalize(row):
        if not isinstance(row,dict):raise ValueError('bar must be an object')
        if 'timestamp' in row and 'time' not in row:
            if open_time_minutes is None:
                raise ValueError('timestamp requires explicit open_time_minutes adapter')
            row=dict(row)
            row['time']=(parse_time(row['timestamp'])+timedelta(minutes=open_time_minutes)).isoformat()
            row['timeframe']=str(open_time_minutes)
            row['source']=':'.join(str(row.get(k,'unknown')) for k in ('source','feed','adjustment'))
        return Bar.from_dict(row)
    path = Path(path)
    records = []
    if path.suffix.lower() == '.csv':
        with path.open(newline='', encoding='utf-8-sig') as f:
            for rownum, row in enumerate(csv.DictReader(f), 2):
                try:
                    for field in ('open','high','low','close','volume'):
                        if field in row and row[field] != '':
                            row[field] = float(row[field])
                        elif field == 'volume':
                            row.pop(field, None)
                    if 'final' in row:
                        if row['final'].lower() not in ('true','1'):
                            raise ValueError('nonfinal CSV bar')
                        row['final'] = True
                    records.append(normalize(row))
                except (ValueError, TypeError, KeyError) as ex:
                    raise ValueError(f'CSV row {rownum}: {ex}') from ex
    else:
        with path.open(encoding='utf-8') as f:
            for rownum, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    records.append(normalize(json.loads(line)))
                except (ValueError, TypeError, KeyError) as ex:
                    raise ValueError(f'JSONL line {rownum}: {ex}') from ex
    return _validated(records)


def run_replay(bars, config=None):
    """Feed completed bars sequentially; no look-ahead or future parameter fitting."""
    bars = _validated(bars)
    engine = Engine(config)
    events = []
    daily = defaultdict(int)
    digest = hashlib.sha256()
    for b in bars:
        events.extend(engine.update(b))
        daily[parse_time(b.time).astimezone(NY).date().isoformat()] += 1
        digest.update((json.dumps(asdict(b),sort_keys=True)+'\n').encode())
    return {
        'events': events,
        'summary': {
            'bars':len(bars), 'sessions':len(daily), 'bars_per_session':dict(daily),
            'first_bar':bars[0].time if bars else None,
            'last_bar':bars[-1].time if bars else None,
            'stream':engine.stream, 'config':asdict(engine.config),
            'config_hash':engine.config_hash,'canonical_data_sha256':digest.hexdigest(),
            'events_by_family_status':dict(Counter(e['family']+':'+e['status'] for e in events)),
            'unexpected_gaps':engine.gap_count,
            'mode':'sequential_closed_bar_replay',
            'coverage_note':'Observed sessions/bars only; no exchange-calendar completeness claim.',
        },
        'snapshot':engine.snapshot(),
    }


def evaluate(bars, events, cost_bps=3.0, expiry_bars=20):
    """Estimate a fixed one-position, 100%-notional, long-only paper policy.

    Confirmed events arm AFTER their bar closes. Oldest pending setup wins; new
    setups while armed/in position are ignored. No shorts or actual orders.
    Fill proxy=max(trigger,next bar open), only if positive remaining reward.
    Stop-first on ambiguous bars; gap stops use worse open. Profit limits never
    get gap improvement. On missing data exit at next observed open and flag it.
    RTH 16:00 closes flatten; incomplete EOF positions get a disclosed mark.
    cost_bps applies adverse price friction on EACH side, not measured quotes.
    """
    if isinstance(cost_bps,bool) or not isinstance(cost_bps,(int,float)) or not math.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise ValueError('cost_bps must be finite and in [0,10000)')
    if isinstance(expiry_bars,bool) or not isinstance(expiry_bars,int) or expiry_bars < 1:
        raise ValueError('expiry_bars must be a positive integer')
    bars = _validated(bars)
    if bars and bars[0].timeframe=="D": raise ValueError("legacy policy is intraday only")
    index = {b.time:i for i,b in enumerate(bars)}
    by_bar = defaultdict(list)
    seen = set()
    ignored_short = 0
    for event in events:
        if not isinstance(event,dict):raise ValueError('event must be an object')
        if event.get('status') != 'confirmed':continue
        observed = parse_time(event.get('observed_at')).isoformat()
        confirmed = event.get('confirmed_at')
        if confirmed is not None:
            confirmed = parse_time(confirmed).isoformat()
            if parse_time(confirmed) < parse_time(observed):
                raise ValueError('confirmed_at precedes availability')
            observed = confirmed
        if observed not in index:raise ValueError('confirmed event time is not in input bars')
        if event.get('direction') != 'long':
            ignored_short += int(event.get('direction') == 'short');continue
        if not all(k in event for k in ('trigger','stop','target')):continue
        if any(isinstance(event[k],bool) or not isinstance(event[k],(float,int)) or not math.isfinite(event[k]) for k in ('trigger','stop','target')):
            raise ValueError('nonfinite or nonnumeric trade levels')
        identity = event.get('id') or json.dumps(event,sort_keys=True)
        if identity in seen:continue
        seen.add(identity)
        by_bar[index[observed]].append(event)
    trades=[]; pending=None; position=None; equity=1.0; peak=1.0; max_dd=0.0
    curve=[]; daily={}; prev=None; exposed=0; ambiguity_count=0
    skipped_reward=0; cancelled=0; expired=0; ignored_busy=0; gap_exits=0
    rate=cost_bps/10000

    def close_position(b, raw_price, reason, ambiguous=False):
        nonlocal position,equity
        p=position
        adjusted_entry=p['entry_price']*(1+rate)
        adjusted_exit=raw_price*(1-rate)
        net=adjusted_exit/adjusted_entry-1
        gross=raw_price/p['entry_price']-1
        equity=p['equity_before']*(1+net)
        trades.append({
            'event_id':p['event_id'],'family':p['family'],'direction':'long',
            'signal_available_at':p['signal_available_at'],'entry_bar_close':p['entry_bar_close'],
            'exit_bar_close':b.time,'entry_price':p['entry_price'],'exit_price':raw_price,
            'cost_adjusted_entry':adjusted_entry,'cost_adjusted_exit':adjusted_exit,
            'stop':p['stop'],'target':p['target'],'exit_reason':reason,
            'ambiguous':ambiguous,'gross_return':gross,'net_return':net,
            'equity_after':equity,'cost_bps_per_side':cost_bps,
            'execution':'hypothetical_OHLC_proxy_not_actual_fill'})
        position=None

    for i,b in enumerate(bars):
        local=parse_time(b.time).astimezone(NY)
        day=local.date().isoformat()
        is_rth=time(9,30)<local.time().replace(tzinfo=None)<=time(16,0)
        daily.setdefault(day, {'bars':0,'equity_open':equity,'equity_close':equity,'trades':0})
        daily[day]['bars']+=1
        day_changed=prev is not None and parse_time(prev.time).astimezone(NY).date()!=local.date()
        gap=prev is not None and (parse_time(b.time)-parse_time(prev.time)).total_seconds()!=int(b.timeframe)*60
        in_bar_ambiguity=False
        if gap:
            pending=None
            if position:
                close_position(b,b.open,'data_gap_exit')
                gap_exits+=1
        if day_changed:pending=None
        if position:
            exposed+=1
            stop_hit=b.low<=position['stop'];target_hit=b.high>=position['target']
            in_bar_ambiguity=stop_hit and target_hit
            if stop_hit:close_position(b,min(b.open,position['stop']),'stop',in_bar_ambiguity)
            elif target_hit:close_position(b,position['target'],'target')
        elif pending and is_rth:
            age=i-pending['index']
            if age>expiry_bars:
                expired+=1;pending=None
            elif b.open<=pending['stop']:
                # Open is the first observed price: invalidation precedes any rally.
                cancelled+=1;pending=None
            elif b.high>=pending['trigger']:
                raw_entry=max(b.open,pending['trigger'])
                if raw_entry>=pending['target'] or raw_entry<=pending['stop']:
                    skipped_reward+=1;pending=None
                else:
                    position={**pending,'entry_price':raw_entry,'entry_bar_close':b.time,'equity_before':equity}
                    pending=None;exposed+=1
                    stop_hit=b.low<=position['stop'];target_hit=b.high>=position['target']
                    # Stop may precede trigger within OHLC; stop-first is pessimistic.
                    in_bar_ambiguity=stop_hit
                    if stop_hit:close_position(b,position['stop'],'stop',True)
                    elif target_hit:close_position(b,position['target'],'target')
            elif b.low<=pending['stop']:
                cancelled+=1;pending=None
        if in_bar_ambiguity:ambiguity_count+=1
        if local.time().replace(tzinfo=None)==time(16,0):
            if position:close_position(b,b.close,'scheduled_rth_close')
            pending=None
        # Only now does this bar's newly confirmed signal become available.
        if is_rth and local.time().replace(tzinfo=None)<time(16,0):
            for ev in by_bar.get(i,[]):
                if ev['target']<=ev['trigger'] or ev['stop']>=ev['trigger'] or ev['stop']<=0:
                    skipped_reward+=1;continue
                if position or pending:
                    ignored_busy+=1;continue
                pending={**ev,'event_id':ev.get('id'),'family':ev.get('family'),
                         'signal_available_at':b.time,'index':i}
        marked=equity
        if position:marked=position['equity_before']*(b.close*(1-rate))/(position['entry_price']*(1+rate))
        peak=max(peak,marked);max_dd=max(max_dd,1-marked/peak)
        curve.append({'time':b.time,'equity_marked':marked,'equity_realized':equity,'position_open':bool(position)})
        daily[day]['equity_close']=marked
        prev=b
    incomplete_mark=position is not None
    if position:
        close_position(bars[-1],bars[-1].close,'end_of_data_mark_not_fill')
        curve[-1].update(equity_realized=equity,position_open=False)
    for tr in trades:
        day=parse_time(tr['exit_bar_close']).astimezone(NY).date().isoformat()
        daily[day]['trades']+=1
    n=len(trades)
    gross_equity=math.prod(1+t['gross_return'] for t in trades)
    returns=[t['net_return'] for t in trades]
    return {'trades':trades,'equity_curve':curve,'sessions':daily,'summary':{
        'policy':'long_only_one_position_100pct_notional_no_leverage',
        'trades':n,'net_return':equity-1,'gross_return':gross_equity-1,
        'expectancy_mean_trade_return':sum(returns)/n if n else None,
        'win_rate':sum(r>0 for r in returns)/n if n else None,
        'max_close_marked_drawdown':max_dd,'exposure_bar_fraction':exposed/len(bars) if bars else 0,
        'turnover_sides':2*n,'ambiguous_bars':ambiguity_count,'gap_exits':gap_exits,
        'skipped_no_reward':skipped_reward,'cancelled_before_trigger':cancelled,'expired':expired,
        'ignored_while_busy':ignored_busy,'ignored_short_setups':ignored_short,
        'end_of_data_mark_not_fill':incomplete_mark,'cost_bps_per_side':cost_bps,
        'cost_model':'adverse entry/exit price friction; includes assumed spread/slippage, excludes unmodeled fees',
        'limits':['OHLC cannot reveal intrabar sequence; stop-first conservative.',
                  'No historical quotes, borrow, liquidity, market impact or actual fills.',
                  'RTH close fixed at 16:00 New York; early-close days require externally filtered policy/calendar.',
                  'Missing bars force next-observed-open exit; EOF mark is not an executable fill.',
                  'Return is a fixed-policy research estimate, not pattern accuracy or a guarantee.'],
    }}


SPLITS = {
    'development':('2026-08-17','2026-09-30','chronological_development'),
    'validation':('2026-10-01','2026-10-23','chronological_validation'),
    'frozen_evaluation':('2026-10-26','2026-11-16','fixed_config_historical_evaluation_not_pristine_after_inspection'),
    'known_case_2026_11_17':('2026-11-17','2026-11-17','known_case_not_blind'),
}


def evaluate_splits(bars, config=None, cost_grid=(0,1,3,5)):
    """Fixed-date slices, same frozen config, no search/selection or parameter fit."""
    bars=_validated(bars)
    if bars and bars[0].timeframe=='D': raise ValueError('legacy policy is intraday only')
    result={'splits':{},'config':asdict(config or Config()),
            'method':'fixed chronological partitions; no parameter tuning performed by this function',
            'data_scope':'2026-08-17 through 2026-11-17; known case separate from prior three calendar months'}
    for name,(start,end,label) in SPLITS.items():
        subset=[b for b in bars if start<=parse_time(b.time).astimezone(NY).date().isoformat()<=end]
        replay=run_replay(subset,config)
        scenarios={str(c):evaluate(subset,replay['events'],cost_bps=c) for c in cost_grid}
        result['splits'][name]={'start':start,'end':end,'label':label,'bars':len(subset),
            'status':'observed_data_only' if subset else 'no_data',
            'replay_summary':replay['summary'],'cost_scenarios':scenarios}
    return result
