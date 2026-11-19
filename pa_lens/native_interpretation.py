"""Current native-only context. No historical reconstruction or local fallback."""
from datetime import datetime, timezone
from decimal import Decimal, DecimalException

from .native_runtime import DAILY_CONTEXT_PACK, INTRADAY_CONTEXT_PACK
from .provider_indicators import INDICATOR_DEFAULTS, INDICATOR_FIELDS
from .robinhood import INTERVAL_MINUTES
from .timeframes import is_daily_fresh


_AVAILABLE = 'AVAILABLE_SOURCE_UNKNOWN'
_PERIOD_KEYS = {'ema': 'ema20', 'atr': 'atr14', 'rsi': 'rsi14'}


def _time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def _decimal(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('non-finite native value')
    return number


def _histogram_delta(row, latest, histogram):
    points = row.get('points', ())
    if len(points) >= 2 and points[-1]['time'] == latest['time']:
        previous = points[-2]['values'].get('histogram')
        if previous is not None:
            try:
                return str(histogram - _decimal(previous))
            except (DecimalException, ValueError):
                pass
    return None


def _interpret_indicator(bar, snapshots, now, observation_seq, interval, bounds, adjustment,
                         name, parameters, atr=None):
    unavailable = dict(status='UNAVAILABLE', reason='未取得匹配原生值；不回退本地计算')
    candidates = (
        row for row in snapshots
        if row['symbol'] == bar['symbol'] and row['indicator_type'] == name
        and row['requested']['interval'] == interval and row['requested']['bounds'] == bounds
        and row['requested']['adjustment_type'] == adjustment
        and {**INDICATOR_DEFAULTS[name], **row['requested']['parameters']} == parameters
    )
    row = max(candidates, key=lambda candidate: candidate['id'], default=None)
    if row is None:
        return unavailable

    returned = row.get('returned_params')
    receipt = _time(row['received_at'])
    out = dict(
        unavailable, snapshot_id=row['id'], query_id=row.get('query_id'), source=row.get('source'),
        requested=row['requested'], returned_params=returned, received_at=row['received_at'],
        after_bar_seq=row['after_bar_seq'], native_status=row['status'],
        receipt_age_seconds=(now - receipt).total_seconds(),
    )
    if receipt > now or row['after_bar_seq'] > observation_seq:
        return dict(out, reason='原生结果在本次观察之后才可知')
    if row['status'] != _AVAILABLE:
        return dict(out, reason='原生结果非可用完整快照：' + row['status'])
    if name in ('vwap', 'pivot_points'):
        params_match = returned in ({}, {'method': 'classic'})
    else:
        params_match = returned is not None and all(returned.get(key) == value for key, value in parameters.items())
    if not params_match:
        return dict(out, reason='原生参数与所需参数不一致')

    latest = row.get('latest')
    if not latest:
        return dict(out, reason='原生最新值缺失')
    point = _time(latest['time'])
    age = (now - point).total_seconds()
    out.update(effective_at=latest['time'], value_age_seconds=age)
    if point != _time(bar['time']):
        return dict(out, reason='原生有效时点与当前K线不一致')
    if point > receipt or point > now:
        return dict(out, reason='接收或观察时尚未闭合')
    try:
        if interval == 'day':
            fresh = is_daily_fresh(point, now)
        else:
            interval_seconds = INTERVAL_MINUTES[interval] * 60
            fresh = age <= max(120, 2 * interval_seconds)
    except ValueError:
        return dict(out, reason='原生有效时点不符合交易日收盘语义')
    if not fresh:
        return dict(out, reason='原生有效值已过期')

    value_field = {'pivot_points': 'pivot', 'macd': 'histogram'}.get(name, 'value')
    try:
        values = {field: _decimal(latest['values'][field]) for field in INDICATOR_FIELDS[name]}
        value = values[value_field]
        fields = {'value': str(value)}
        if value_field != 'value':
            fields['values'] = {field: str(number) for field, number in values.items()}
        if name in ('ema', 'vwap', 'pivot_points'):
            close = _decimal(bar['close'])
            distance = close - value
            relation = 'above' if close > value else 'below' if close < value else 'equal'
            fields.update(relation=relation, distance=str(distance),
                          atr_multiple=str((distance / atr).quantize(Decimal('0.01'))) if atr is not None else None)
            if name == 'ema':
                fields['explanation'] = f'当前收盘 {close} 相对原生 EMA20 {value}：{relation}；不是买卖指令。'
        elif name == 'macd':
            fields['histogram_delta'] = _histogram_delta(row, latest, value)
        elif name == 'rsi':
            fields['explanation'] = f'原生 RSI14 为 {value}；仅描述数值，不推断必然反转。'
    except (KeyError, DecimalException, ValueError):
        return dict(out, reason='原生值未定义或格式无效')
    return dict(out, **fields, status=_AVAILABLE, source_quality='unknown', warmup='unknown', reason=None)


def interpret(bar, snapshots, now, observation_seq, historical=False, bar_quality=None):
    base = dict(origin='robinhood_native_only', generated_at=now.isoformat(), observation_seq=observation_seq,
                fallback='disabled', source_quality='unknown', warmup='unknown', status='UNAVAILABLE',
                notice='原生数值仅作有来源的当前语境；质量/暖机未知，不是已验证交易信号。纯K线结构独立。',
                bar_quality=bar_quality or {'status': 'not_supplied'}, interpretation_basis='first_received_closed_bar')
    if bar_quality and bar_quality.get('quarantined_count', 0):
        return dict(base, reason='K线存在已知修订/迟到数据；首次接收close未重算，暂停原生比较')
    if historical:
        return dict(base, status='HISTORICAL_UNAVAILABLE', reason='未记录当时原生解读，禁止以后来快照回填')

    parts = bar['source'].split(':')
    if bar['timeframe'] == 'D':
        interval = 'day'
        pack = DAILY_CONTEXT_PACK
        allowed_bounds = ('regular',)
    else:
        interval = next((name for name, minutes in INTERVAL_MINUTES.items() if str(minutes) == bar['timeframe']), None)
        pack = INTRADAY_CONTEXT_PACK
        allowed_bounds = ('regular', 'extended')
    if (len(parts) < 4 or parts[0] != 'robinhood' or parts[1] != interval
            or parts[2] not in allowed_bounds):
        unavailable = dict(status='UNAVAILABLE', reason='原生周期/来源不受支持（包括派生15m）；不得替用其它周期')
        return dict(base, ema20=unavailable.copy(), rsi14=unavailable.copy())

    args = (bar, snapshots, now, observation_seq, interval, parts[2], parts[3])
    atr14 = _interpret_indicator(*args, 'atr', pack['atr'])
    atr = Decimal(atr14['value']) if atr14['status'] == _AVAILABLE else None
    if atr is not None and atr <= 0:
        atr = None
    available = 0
    for name, parameters in pack.items():
        key = _PERIOD_KEYS.get(name, name)
        entry = atr14 if name == 'atr' else _interpret_indicator(*args, name, parameters, atr=atr)
        base[key] = entry
        available += entry['status'] == _AVAILABLE
    base['status'] = _AVAILABLE if available == len(pack) else 'PARTIAL_NATIVE_CONTEXT' if available else 'UNAVAILABLE'
    return base
