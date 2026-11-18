"""Independent native-indicator snapshots. Never used as PA detector inputs."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from .provider_indicators import INDICATOR_DEFAULTS,validate_indicator_request
from .robinhood import _symbols,_time,_wire,RobinhoodError

MAX_NATIVE_CALLS=64


def native_specs(selection=None, configuration=None, interval='5minute', output='latest'):
    specs=[]
    if selection:
        names=list(INDICATOR_DEFAULTS) if selection=='all' else selection.split(',')
        specs.extend(dict(type=name,parameters={'period':20} if selection=='all' and name=='ema' else {},interval=interval,output=output) for name in names)
    if configuration is not None:
        if not isinstance(configuration,list):raise ValueError('native config must be a list')
        for item in configuration:
            if not isinstance(item,dict) or not {'type'}<=item.keys() or not item.keys()<={'type','parameters','interval','output'}:
                raise ValueError('native config permits only type/parameters/interval/output')
            specs.append(dict(type=item['type'],parameters=item.get('parameters',{}),interval=item.get('interval',interval),output=item.get('output',output)))
    if len(specs)>MAX_NATIVE_CALLS:raise ValueError('at most 64 native indicator requests')
    # Contract validation occurs before opening transport, even if no data requested yet.
    for spec in specs:
        _request(['SOXL'],'2026-11-17T00:00:00Z','2026-11-18T00:00:00Z',spec,'regular','split')
    return specs


def _request(symbols,start,end,spec,bounds,adjustment):
    if not isinstance(spec,dict) or set(spec)!={'type','parameters','interval','output'} or not isinstance(spec['parameters'],dict):
        raise ValueError('invalid native request configuration')
    args=dict(symbols=list(symbols),start_time=_wire(_time(start)),end_time=_wire(_time(end)),type=spec['type'],
              interval=spec['interval'],bounds=bounds,adjustment_type=adjustment,output=spec['output'])
    if set(spec['parameters']) & set(args):raise ValueError('native parameters cannot override request controls')
    args.update(spec['parameters']);validate_indicator_request(args)
    return args


def validate_native(symbols,start,end,specs,bounds='regular',adjustment_type='split'):
    names=_symbols(symbols)
    groups=[names[i:i+10] for i in range(0,len(names),10)]
    if len(specs)*len(groups)>MAX_NATIVE_CALLS:raise ValueError('native request budget exceeds 64 calls')
    for spec in specs:
        for group in groups:_request(group,start,end,spec,bounds,adjustment_type)
    return names


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def slot_identity(symbol,spec,bounds,adjustment_type):
    return _hash(dict(symbol=symbol,indicator_type=spec['type'],parameters=spec['parameters'],interval=spec['interval'],
                      bounds=bounds,adjustment_type=adjustment_type,output=spec['output']))


def restore_native_start(journal,symbols,specs,bounds='regular',adjustment_type='split'):
    starts=[]
    for symbol in symbols:
        for spec in specs:
            raw=journal.conn.execute('SELECT payload FROM native_snapshots WHERE slot_key=? ORDER BY id DESC LIMIT 1',
                (slot_identity(symbol,spec,bounds,adjustment_type),)).fetchone()
            if raw:starts.append(json.loads(raw[0])['requested']['start'])
    if len({_time(value) for value in starts})>1:
        raise ValueError('saved native windows differ; provide explicit --native-window-start to choose a common window')
    return starts[0] if starts else None


def acquire_native(provider,journal,symbols,start,end,specs,*,bounds='regular',adjustment_type='split',capture_dir=None):
    """One fixed window; each request failure retains successful sibling snapshots."""
    names=validate_native(symbols,start,end,specs,bounds,adjustment_type)
    start=_wire(_time(start));end=_wire(min(_time(end),datetime.now(timezone.utc)))
    validate_native(names,start,end,specs,bounds,adjustment_type)
    if capture_dir:
        path=Path(capture_dir).expanduser().resolve();repo=Path(__file__).resolve().parents[1]
        if path==repo or (repo in path.parents and repo/'local_data' not in (path,*path.parents)):
            raise ValueError('native captures inside project must use ignored local_data/')
        path.mkdir(parents=True,exist_ok=True)
    output=[]
    for spec in specs:
        requested=dict(indicator_type=spec['type'],parameters=spec['parameters'],interval=spec['interval'],bounds=bounds,
                       adjustment_type=adjustment_type,output=spec['output'],start=start,end=end)
        received=datetime.now(timezone.utc).isoformat();result=None
        try:
            result=provider.indicators(names,start,end,spec['type'],spec['interval'],bounds=bounds,
                    adjustment_type=adjustment_type,output=spec['output'],parameters=spec['parameters'])
        except (RobinhoodError,ValueError,OSError):
            pass  # Only a safe fixed status is persisted, not exception text.
        received=datetime.now(timezone.utc).isoformat()
        for symbol in names:
            row=next((r for r in result.series if r['symbol']==symbol),None) if result else None
            latest=row.get('latest') if row else None
            quality=result.quality if result else {'source_quality':'unknown','warmup':'unknown'}
            if result is None:status='ERROR'
            elif not quality.get('normalization_supported',row.get('normalization_supported',True) if row else True):status='RAW_ONLY'
            elif row is None or not row.get('points'):status='EMPTY'
            elif symbol in quality.get('no_usable_symbols',[]) or not latest or all(v is None for v in latest['values'].values()):status='UNDEFINED'
            elif any(quality.get(k) for k in ('invalid','missing_fields','missing_symbols','not_found','out_of_range')):status='PARTIAL'
            else:status='AVAILABLE_SOURCE_UNKNOWN'
            # Slot is stable across changing query windows. Complete windows are
            # independently identified and preserved; no time-window stitching.
            slot={k:v for k,v in requested.items() if k not in ('start','end')};slot['symbol']=symbol
            record=dict(symbol=symbol,indicator_type=spec['type'],requested=requested,returned_params=row.get('params') if row else None,
                status=status,latest=latest,points=row.get('points',[]) if row else [],source=result.source if result else 'robinhood:native',
                source_quality='unknown',warmup='unknown',quality=quality,received_at=received,cutoff=result.cutoff if result else end,
                query_id=_hash(dict(symbol=symbol,**requested)),slot_key=_hash(slot),batches=list(result.batches) if result else [],
                error='NATIVE_REQUEST_FAILED' if result is None else None,series_id=row.get('series_id') if row else None)
            ident=journal.record_native(record)
            output.append({k:v for k,v in record.items() if k not in ('points','batches')}|{'snapshot_id':ident})
        if capture_dir:
            payload=dict(requested=requested,received_at=received,raw_records=result.raw_records if result else [],
                         series=result.series if result else [],batches=result.batches if result else [],status='ERROR' if result is None else 'RECEIVED')
            (path/f'native-{output[-1]["snapshot_id"]}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return output


def context_specs(specs,interval='5minute',enabled=True,bounds='regular'):
    result=list(specs)
    if not enabled or interval=='15minute' or bounds not in ('regular','extended'):return result
    for name,period in (('ema',20),('rsi',14)):
        if not any(s['type']==name and s['interval']==interval and s['parameters'].get('period',INDICATOR_DEFAULTS[name]['period'])==period for s in result):
            result.append(dict(type=name,parameters={'period':period},interval=interval,output='latest'))
    return result
