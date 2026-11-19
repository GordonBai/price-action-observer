"""Project the current closed-bar context from a stream's retained observations."""
from collections.abc import Mapping, Sequence
from datetime import timedelta
import math

from .core import parse_time
from .timeframes import NY, calendar, consecutive_daily


RECENT_RESOLUTION_BARS = 5
_AVAILABLE = 'AVAILABLE_SOURCE_UNKNOWN'
_NATIVE_LABELS = {
    'ema20': 'EMA20', 'vwap': 'VWAP', 'atr14': 'ATR14', 'rsi14': 'RSI14',
    'pivot_points': 'Pivot', 'macd': 'MACD',
}
_MULTISTAGE = {
    'double_bottom', 'double_top', 'three_push_wedge', 'failed_failure',
    'opening_reversal', 'mtr_development', 'final_flag_development',
}
_ACTIONABLE = _MULTISTAGE | {
    'range_breakout', 'breakout_observation', 'failed_breakout',
    'opening_breakout_mode', 'tight_channel', 'high_attempt', 'low_attempt',
}
_OBSERVED_SETUPS = {'high_attempt', 'low_attempt', 'trend_line_retest'}
_TRACKED_TARGETS = {'double_bottom', 'double_top', 'range_breakout'}
_RESOLVED = {'invalidated', 'expired', 'reached'}
_COORDINATES = (
    'neckline', 'confirmation_level', 'invalidation_extreme', 'line_value',
    'trigger', 'stop', 'target', 'range_high', 'range_low', 'signal_bar_extreme',
)
_STRUCTURAL_LEVELS = {
    'neckline': 'Neckline', 'confirmation_level': 'Confirm',
    'trigger': 'Trig', 'stop': 'Stop', 'target': 'MM',
}


def _finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _native_summary(native):
    items = []
    for key, label in _NATIVE_LABELS.items():
        if key not in native:
            continue
        entry = native[key]
        status = entry.get('status', 'UNAVAILABLE')
        display_value = entry.get('value')
        values = entry.get('values', {})
        if key == 'pivot_points' and values:
            display_value = ' / '.join(
                f'{label} {values[field]}' for field, label in (('pivot', 'P'), ('r1', 'R1'), ('s1', 'S1'))
                if values.get(field) is not None
            )
        if key == 'macd' and values:
            fields = (('MACD', values.get('macd')), ('Sig', values.get('signal')),
                      ('Hist', values.get('histogram')), ('Δ', entry.get('histogram_delta')))
            display_value = ' / '.join(f'{label} {value}' for label, value in fields if value is not None)
        items.append(dict(
            key=key, label=label, status=status,
            display_value=str(display_value) if status == _AVAILABLE and display_value is not None else None,
            relation=entry.get('relation'), distance=_finite(entry.get('distance')),
            atr_multiple=_finite(entry.get('atr_multiple')), reason=entry.get('reason'),
        ))
    return {'status': native.get('status', 'UNAVAILABLE'), 'items': items}


def _setup_levels(event):
    anchors = event.get('anchors', {})
    levels = {}
    range_bounds = anchors.get('opening_range', {})
    if event['family'] in {'range_breakout', 'final_flag_development'}:
        range_bounds = anchors
    for key in _COORDINATES:
        value = _finite(event.get(key))
        if value is None:
            value = _finite(anchors.get(key))
        if value is None and key in ('range_high', 'range_low'):
            value = _finite(range_bounds.get(key.removeprefix('range_')))
        if value is not None:
            levels[key] = value
    return levels


def _breakout_key(event):
    anchors = event.get('anchors', {})
    key = (anchors.get('breakout_time'), event.get('direction'),
           anchors.get('range_high'), anchors.get('range_low'))
    return key if all(value is not None for value in key) else None


def _resolve_episode(episode, event, observed, index, status):
    episode['setup'].update(status=status, observed_at=event['observed_at'],
                            explanation=event.get('explanation', ''))
    episode.update(observed=observed, index=index)


def _setup(event, root, prior):
    family = event['family']
    anchors = event.get('anchors', {})
    stage = event.get('stage') or anchors.get('stage') or event.get('attempt_label')
    if family == 'trend_line_retest':
        stage = stage or family
    return dict(id=root, family=prior.get('family', family), status=event['status'],
                direction=event.get('direction', 'neutral'), observed_at=event['observed_at'],
                stage=stage, levels={**prior.get('levels', {}), **_setup_levels(event)},
                explanation=event.get('explanation', ''))


def _active_structures(segment_times, events, focus_count, target_parents):
    live, recent = [], []
    if not segment_times or not focus_count:
        return {'live_setups': live, 'recent_resolved': recent}
    focus_start = segment_times[-min(focus_count, len(segment_times))]
    recent_start = segment_times[-min(focus_count, len(segment_times), RECENT_RESOLUTION_BARS)]
    segment_start, latest = segment_times[0], segment_times[-1]

    episodes, confirmation_ids, breakout_ids = {}, {}, {}
    for index, event in enumerate(events):
        family, status = event['family'], event['status']
        if family not in _ACTIONABLE and family not in ('trend_line_retest', 'measured_move'):
            continue
        observed = parse_time(event['observed_at'])
        if not segment_start <= observed <= latest:
            continue
        parent = event.get('parent_id')
        if family == 'measured_move':
            if status not in ('reached', 'invalidated'):
                continue
            episode = episodes.get(confirmation_ids.get(parent))
            if episode is None and observed >= recent_start and parent in target_parents:
                confirmed = target_parents[parent]
                root = confirmed.get('parent_id') or confirmed['id']
                episode = dict(setup=_setup(confirmed, root, {}), latest_family=confirmed['family'])
                episodes[root] = episode
            if episode is not None:
                _resolve_episode(episode, event, observed, index, status)
                episode['setup']['target_state'] = status
            continue

        parent_episode = episodes.get(parent)
        root = event['id']
        if family == 'trend_line_retest':
            if parent_episode is None or parent_episode['setup']['family'] != 'mtr_development':
                continue
            root = parent
        elif family in _MULTISTAGE and parent_episode is not None and parent_episode['setup']['family'] == family:
            root = parent
        elif family in _TRACKED_TARGETS and status == 'confirmed' and parent and parent_episode is None:
            root = parent
        prior = episodes.get(root, {}).get('setup', {})
        setup = _setup(event, root, prior)
        if family in _TRACKED_TARGETS and status == 'confirmed':
            confirmation_ids[event['id']] = root
            creation = event.get('target_state_at_creation')
            if creation == 'already_touched':
                setup.update(status='reached', target_state='reached')
            elif creation == 'pending':
                setup['target_state'] = 'pending'
        episodes[root] = dict(setup=setup, observed=observed, index=index, latest_family=family)

        if status == 'confirmed' and family in ('breakout_observation', 'failed_breakout'):
            key = _breakout_key(event)
            if key is not None:
                if family == 'breakout_observation':
                    breakout_ids[key] = root
                elif key in breakout_ids:
                    original = episodes[breakout_ids.pop(key)]
                    _resolve_episode(original, event, observed, index, 'invalidated')

    for episode in sorted(episodes.values(), key=lambda row: (row['observed'], row['index']), reverse=True):
        setup = episode['setup']
        status = setup['status']
        if status in _RESOLVED and episode['observed'] >= recent_start:
            recent.append(setup)
        elif episode['observed'] >= focus_start and (
            status in ('candidate', 'confirmed')
            or (status == 'observed' and episode['latest_family'] in _OBSERVED_SETUPS)
        ):
            live.append(setup)
    return {'live_setups': live, 'recent_resolved': recent}


def _swing_levels(segment):
    for side, label, sign in (('high', 'SwHi', 1), ('low', 'SwLo', -1)):
        for index in range(len(segment) - 3, 1, -1):
            price = segment[index][side]
            neighbors = segment[index - 2:index] + segment[index + 1:index + 3]
            if all(sign * price > sign * bar[side] for bar in neighbors):
                yield f'swing_{side}', label, price, 'swing'
                break


def _prior_session_levels(bars, times):
    if len(bars) < 2:
        return
    timeframe = bars[-1]['timeframe']
    if timeframe == 'D':
        if consecutive_daily(*times[-2:]):
            yield 'prior_session_high', 'PrevDayHi', bars[-2]['high'], 'swing'
            yield 'prior_session_low', 'PrevDayLo', bars[-2]['low'], 'swing'
        return

    schedule = calendar()
    try:
        session = schedule.previous_session(times[-1].astimezone(NY).date().isoformat())
    except (ValueError, OverflowError):
        # Manual intraday feeds can include non-session dates or older history.
        return
    opened = schedule.session_open(session).to_pydatetime()
    closed = schedule.session_close(session).to_pydatetime()
    step = timedelta(minutes=int(timeframe))
    expected, remainder = divmod(closed - opened, step)
    if remainder:
        return
    prior = [(bar, time) for bar, time in zip(bars, times) if opened < time <= closed]
    if len(prior) != expected or any(time != opened + i * step for i, (_, time) in enumerate(prior, 1)):
        return
    yield 'prior_session_high', 'PDH', max(bar['high'] for bar, _ in prior), 'swing'
    yield 'prior_session_low', 'PDL', min(bar['low'] for bar, _ in prior), 'swing'


def _level_candidates(bars, times, segment, live_setups, native):
    yield from _swing_levels(segment)
    yield from _prior_session_levels(bars, times)
    if len(segment) >= 20:
        yield 'range_high', '20B Hi', max(bar['high'] for bar in segment[-20:]), 'swing'
        yield 'range_low', '20B Lo', min(bar['low'] for bar in segment[-20:]), 'swing'
    for setup in live_setups:
        for key, label in _STRUCTURAL_LEVELS.items():
            yield key, label, setup['levels'].get(key), 'structure'
    for key in ('ema20', 'vwap'):
        entry = native.get(key, {})
        if entry.get('status') == _AVAILABLE:
            yield key, _NATIVE_LABELS[key], entry.get('value'), 'native'
    pivots = native.get('pivot_points', {})
    if pivots.get('status') == _AVAILABLE:
        values = pivots.get('values', {})
        yield 'pivot', 'Pivot P', values.get('pivot', pivots.get('value')), 'native'
        yield 'r1', 'R1', values.get('r1'), 'native'
        yield 's1', 'S1', values.get('s1'), 'native'


def _key_levels(bars, times, segment, live_setups, native, atr):
    if not bars:
        return []
    levels, seen = [], set()
    for kind, label, value, source in _level_candidates(bars, times, segment, live_setups, native):
        price = _finite(value)
        if price is None or (kind, round(price, 4)) in seen:
            continue
        distance = _finite(bars[-1]['close'] - price)
        if distance is None:
            continue
        seen.add((kind, round(price, 4)))
        multiple = _finite(distance / atr) if atr else None
        levels.append(dict(kind=kind, label=label, price=price, distance=distance,
                           atr_multiple=round(multiple, 2) if multiple is not None else None, source=source))
    return sorted(levels, key=lambda entry: entry['price'], reverse=True)


def summarize_stream(
    bars: Sequence[dict], events: Sequence[dict], engine_state: dict,
    native_interpretation: dict | None = None, *, focus_bars: int | None = None,
    target_parents: Mapping[str, dict] | None = None,
) -> dict:
    """Summarize ordered bars and events at the latest bar close.

    Target parents map confirmation IDs to originating events that may have
    aged out of the retained bars or events.
    """
    bars = list(bars)
    times = [parse_time(bar['time']) for bar in bars]
    native = native_interpretation or {}
    bars_in_segment = engine_state.get('bars_in_segment', len(bars))
    segment_start = max(0, len(bars) - bars_in_segment)
    segment = bars[segment_start:]
    focus_count = min(len(bars), max(0, focus_bars or 30))

    closes = [bar['close'] for bar in segment[-20:]]
    path = sum(abs(end - start) for start, end in zip(closes, closes[1:]))
    efficiency = abs(closes[-1] - closes[0]) / path if path else 0.0
    engine_atr = _finite(engine_state.get('local_indicators', {}).get('atr_engine', {}).get('value'))
    atr14 = native.get('atr14', {})
    native_atr = _finite(atr14.get('value')) if atr14.get('status') == _AVAILABLE else None
    reference_atr, atr_origin = None, None
    if native_atr is not None and native_atr > 0:
        reference_atr, atr_origin = native_atr, 'robinhood_native_atr14'
    elif engine_atr is not None and engine_atr > 0:
        reference_atr, atr_origin = engine_atr, 'local_engine_atr15'

    active = _active_structures(times[segment_start:], events, focus_count, target_parents or {})
    return {
        'regime': dict(context=engine_state.get('context', 'warmup'), efficiency_20=efficiency,
                       bars_total=engine_state.get('total_bars', len(bars)), bars_in_segment=bars_in_segment,
                       focus_window_bars=focus_count, engine_atr=engine_atr,
                       reference_atr=reference_atr, atr_origin=atr_origin),
        'native_summary': _native_summary(native),
        'active_structures': active,
        'key_levels': _key_levels(bars, times, segment, active['live_setups'], native, reference_atr),
        'htf_alignment': None,
    }
