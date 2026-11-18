"""Current native-only context. No historical reconstruction or local fallback."""
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from .robinhood import INTERVAL_MINUTES


def _time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def interpret(bar, snapshots, now, observation_seq, historical=False, bar_quality=None):
    base=dict(origin='robinhood_native_only',generated_at=now.isoformat(),observation_seq=observation_seq,
              fallback='disabled',source_quality='unknown',warmup='unknown',status='UNAVAILABLE',
              notice='原生数值仅作有来源的当前语境；质量/暖机未知，不是已验证交易信号。纯K线结构独立。')
    base['bar_quality']=bar_quality or {'status':'not_supplied'}
    base['interpretation_basis']='first_received_closed_bar'
    if bar_quality and bar_quality.get('quarantined_count',0):
        return dict(base,reason='K线存在已知修订/迟到数据；首次接收close未重算，暂停原生比较')
    if historical:return dict(base,status='HISTORICAL_UNAVAILABLE',reason='未记录当时原生解读，禁止以后来快照回填')
    parts=bar['source'].split(':');interval=next((k for k,v in INTERVAL_MINUTES.items() if str(v)==bar['timeframe']),None)
    if bar['timeframe']=='D':interval='day'
    semantics=parts[0]=='robinhood' and len(parts)>=4 and parts[1]==interval
    seconds=86400 if interval=='day' else INTERVAL_MINUTES.get(interval,0)*60
    for indicator,period,key in [('ema',20,'ema20'),('rsi',14,'rsi14')]:
        out=dict(status='UNAVAILABLE',reason='未取得匹配原生值；不回退本地计算')
        if not semantics:
            out['reason']='原生周期/来源不受支持（包括派生15m）；不得替用其它周期'
        else:
            candidates=[r for r in snapshots if r['symbol']==bar['symbol'] and r['indicator_type']==indicator
                        and r['requested']['interval']==interval and r['requested']['bounds']==parts[2]
                        and r['requested']['adjustment_type']==parts[3]
                        and (r['requested']['parameters'].get('period')==period or
                             (r.get('returned_params') or {}).get('period')==period)]
            row=max(candidates,key=lambda r:r['id']) if candidates else None
            if row:
                out.update(snapshot_id=row['id'],query_id=row.get('query_id'),source=row.get('source'),requested=row['requested'],returned_params=row.get('returned_params'),
                           received_at=row['received_at'],after_bar_seq=row['after_bar_seq'],native_status=row['status'])
                latest=row.get('latest');receipt=_time(row['received_at'])
                out['receipt_age_seconds']=(now-receipt).total_seconds()
                reason=None
                if receipt>now or row['after_bar_seq']>observation_seq:reason='原生结果在本次观察之后才可知'
                elif row['status']!='AVAILABLE_SOURCE_UNKNOWN':reason='原生结果非可用完整快照：'+row['status']
                elif (row.get('returned_params') or {}).get('period')!=period or row['requested']['parameters'].get('period',period) not in (None,period):reason='原生参数不是所需周期'
                elif not latest:reason='原生最新值缺失'
                else:
                    point=_time(latest['time']);out.update(effective_at=latest['time'],value_age_seconds=(now-point).total_seconds())
                    if point!=_time(bar['time']):reason='原生有效时点与当前K线不一致'
                    elif point>receipt or point>now:reason='接收或观察时尚未闭合'
                    elif (now-point).total_seconds()>max(120,seconds*2):reason='原生有效值已过期'
                    else:
                        try:
                            value=Decimal(str(latest['values']['value']))
                            if not value.is_finite():raise ValueError()
                            out.update(status='AVAILABLE_SOURCE_UNKNOWN',value=str(value),source_quality='unknown',warmup='unknown')
                            if indicator=='ema':
                                close=Decimal(str(bar['close']));out['relation']='above' if close>value else 'below' if close<value else 'equal'
                                out['explanation']=f'当前收盘 {close} 相对原生 EMA20 {value}：{out["relation"]}；不是买卖指令。'
                            else:out['explanation']=f'原生 RSI14 为 {value}；仅描述数值，不推断必然反转。'
                        except (KeyError,InvalidOperation,ValueError):reason='原生值未定义或格式无效'
                out['reason']=reason
        base[key]=out
    available=sum(base[k]['status']=='AVAILABLE_SOURCE_UNKNOWN' for k in ('ema20','rsi14'))
    base['status']='AVAILABLE_SOURCE_UNKNOWN' if available==2 else 'PARTIAL_NATIVE_CONTEXT' if available else 'UNAVAILABLE'
    return base
