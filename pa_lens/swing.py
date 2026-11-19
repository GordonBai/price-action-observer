"""One-shot research projection of completed XNYS daily bars."""
import argparse
from collections import defaultdict
from collections.abc import Sequence
import csv
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys

from .context_summary import summarize_stream
from .core import parse_time
from . import native_runtime, rh_runtime, robinhood, service
from .terminal_monitor import _level_text, _native_lines, _ny, terminal_output
from .timeframes import daily_close, daily_session

DEFAULT_SYMBOLS = ('SPY', 'QQQ', 'NVDA')
DEFAULT_WARMUP_DAYS = 250
DEFAULT_FOCUS_BARS = 25
_NOTICE = 'Research only: Trig, Stop and MM are structural reference coordinates. probability=None.'
_LIVE_OPTIONS = (
    'warmup_days', 'adjustment', 'infra_root', 'codex_binary', 'timeout', 'capture_dir',
    'strict_interpolation', 'no_native_context',
)


def add_arguments(parser):
    parser.add_argument('--symbols', nargs='+', help='1..10 tickers (live default: SPY QQQ NVDA)')
    parser.add_argument('--focus-bars', type=int, default=DEFAULT_FOCUS_BARS,
                        help='recent trading sessions to highlight (5..120, default: 25)')
    parser.add_argument('--input', help='offline canonical daily JSONL or CSV, incompatible with live options')
    parser.add_argument('--db', default=':memory:',
                        help='optional SQLite journal path under local_data/ or outside the project (default: in memory)')
    parser.add_argument('--output', choices=('text', 'jsonl'), help='text on a TTY, JSONL when piped')
    live = parser.add_argument_group('live Robinhood options', argument_default=argparse.SUPPRESS)
    live.add_argument('--warmup-days', type=int, help='calendar-day lookback (60..1825, default: 250)')
    live.add_argument('--adjustment', choices=('none', 'split', 'all'), help='price adjustment (default: split)')
    live.add_argument('--infra-root', help='existing Robinhood trading infrastructure')
    live.add_argument('--codex-binary', help='Codex executable (default: codex)')
    live.add_argument('--timeout', type=float, help='request timeout in seconds (default: 30)')
    live.add_argument('--capture-dir', help='optional private capture, inside project only under local_data/')
    live.add_argument('--strict-interpolation', action='store_true', help='reject omitted interpolation markers')
    live.add_argument('--no-native-context', action='store_true', help='skip daily native context requests')


def _offline_rows(path, symbols, now):
    """Validate canonical rows and order each independent stream by close."""
    groups = defaultdict(dict)
    is_csv = path.suffix.lower() == '.csv'
    with path.open(encoding='utf-8-sig', newline='') as handle:
        records = csv.DictReader(handle) if is_csv else handle
        for index, raw in enumerate(records, 2 if is_csv else 1):
            try:
                if is_csv:
                    row = dict(raw)
                    for key in ('open', 'high', 'low', 'close', 'volume'):
                        if row.get(key) not in (None, ''):
                            row[key] = float(row[key])
                        elif key == 'volume':
                            row.pop(key, None)
                    for key in ('final', 'bar_closed'):
                        if key in row:
                            row[key] = (row[key] or '').lower() in ('true', '1')
                else:
                    if not raw.strip():
                        continue
                    row = json.loads(raw)
                bar = service.normalize(row)
                if bar.timeframe != 'D':
                    raise ValueError('offline swing requires timeframe D')
                closed = parse_time(bar.time)
                session = daily_session(closed)
                if closed > now:
                    raise ValueError('future close time rejected; use completed daily bars')
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f'{"CSV row" if is_csv else "JSONL line"} {index}: {exc}') from exc
            if symbols is None or bar.symbol in symbols:
                group = groups[(bar.symbol, bar.timeframe, bar.source)]
                if session in group:
                    _check_same_bar(group[session], bar, session)
                else:
                    group[session] = bar
    _require_symbols(symbols or (), {key[0] for key in groups})
    if not groups:
        raise ValueError('offline input contains no daily bars')
    return groups


def _check_same_bar(prior, observed, session):
    if prior != replace(observed, time=prior.time):
        raise ValueError(f'conflicting daily bars for {observed.symbol} ({observed.source}) on {session}; '
                         'use a separate journal for corrected history')


def _offline_pending(journal, groups):
    """Validate every selected stream before appending the first input bar."""
    pending = []
    for key, bars in groups.items():
        stored = {}
        for (payload,) in journal.conn.execute(
                'SELECT payload FROM bars WHERE symbol=? AND timeframe=? AND source=? ORDER BY seq', key):
            bar = service.normalize(json.loads(payload))
            session = daily_session(parse_time(bar.time))
            if session in stored:
                raise ValueError(f'{bar.symbol} ({bar.source}) journal already contains multiple bars for {session}. '
                                 'Use a separate --db or the default in-memory journal.')
            stored[session] = bar
        if stored and max(stored) > max(bars):
            symbol, _, source = key
            raise ValueError(f'{symbol} ({source}) journal already contains bars after this input. '
                             'Use a separate --db or the default in-memory journal.')
        for session, bar in sorted(bars.items()):
            prior = stored.get(session)
            if prior is None:
                pending.append(bar)
            else:
                _check_same_bar(prior, bar, session)
    return pending


def _check_live_journal(journal, keys, start, end):
    """Protect an imported legacy bar's availability when its session will be requested again."""
    for symbol, timeframe, source in sorted(keys):
        for (stamp,) in journal.conn.execute(
                """SELECT time FROM bars WHERE symbol=? AND timeframe=? AND source=?
                   AND time GLOB '*T00:00:00Z'""", (symbol, timeframe, source)):
            legacy = parse_time(stamp)
            # Robinhood requests and filters daily bars by their midnight-UTC date labels.
            if start <= legacy - timedelta(days=1) < end:
                session = daily_session(legacy)
                raise ValueError(f'{symbol} ({source}) journal contains a legacy daily timestamp for {session} '
                                 'in the requested window. Use a separate --db or the default in-memory journal.')


def _open_journal(database):
    if database != ':memory:':
        database = Path(database).expanduser().resolve()
        repo = Path(__file__).resolve().parents[1]
        if database == repo or (repo in database.parents and repo / 'local_data' not in database.parents):
            raise ValueError('swing journals inside the project must use ignored local_data/')
        database.parent.mkdir(parents=True, exist_ok=True)
    try:
        return service.Journal(database)
    except RuntimeError as exc:
        if (isinstance(exc.__cause__, BlockingIOError)
                and str(exc) == 'journal already in use by another instance or process'):
            raise ValueError(str(exc)) from None
        raise


def _require_symbols(requested, available):
    missing = [symbol for symbol in requested if symbol not in available]
    if missing:
        raise ValueError('no usable daily bars for requested symbols: ' + ', '.join(missing))


def _focused_summary(stream, focus_bars):
    summary = stream.get('summary')
    if summary and summary['regime']['focus_window_bars'] == min(focus_bars, len(stream['bars'])):
        return summary
    return summarize_stream(stream['bars'], stream['events'], stream['state'],
                            stream.get('native_interpretation'), focus_bars=focus_bars)


def _session_close(stamp):
    return daily_close(daily_session(parse_time(stamp)))


def _quality(stream):
    quality = stream['data_quality']
    return ' / '.join(dict.fromkeys(value for value in
        (quality.get('status'), quality.get('acquisition_status'), stream.get('scan_acquisition_status')) if value))


def _format_setups(setups):
    for setup in setups:
        stage = f" / {setup['stage']}" if setup.get('stage') else ''
        day = daily_session(parse_time(setup['observed_at']))
        yield f"    {day}  {setup['family']} / {setup['status']}{stage} / {setup['direction']}"
        levels = _level_text(setup['levels'])
        if levels:
            yield f'      {levels}'
    if not setups:
        yield '    None'


def format_swing_report(streams: Sequence[dict], *, now: datetime, focus_bars: int,
                        warmup_days: int | None = None) -> str:
    """Render a focused daily summary without altering the underlying journal."""
    warmup_label = 'offline input' if warmup_days is None else f'{warmup_days} calendar days requested'
    lines = [f'[{_ny(now)}] Daily swing scan | {warmup_label} | focus requested={focus_bars} bars']
    for stream in streams:
        summary = _focused_summary(stream, focus_bars)
        regime = summary['regime']
        closed = _session_close(stream['last_bar_close'])
        lines.extend((
            '',
            f"{stream['symbol']}  {stream['source']} | warmup={regime['bars_total']} bars | "
            f"focus={regime['focus_window_bars']} bars",
            f"  XNYS close {_ny(closed)} | {stream['freshness']} | {_quality(stream)}",
            f"  {regime['context']} | 20D efficiency {regime['efficiency_20']:.2f}"
            f" | Close {stream['bars'][-1]['close']:.8g}",
        ))
        if stream.get('omitted_emitted'):
            lines.append('  Interp marker: omitted by provider')
        lines.extend(_native_lines(stream.get('native_interpretation', {}), daily=True))
        structures = summary['active_structures']
        lines.append('  Active swing structures')
        lines.extend(_format_setups(structures['live_setups']))
        lines.append('  Recently resolved')
        lines.extend(_format_setups(structures['recent_resolved']))
        lines.append('  Objective reference levels')
        levels = summary['key_levels']
        lines.extend(f"    {level['label']} {level['price']:.8g}" for level in levels)
        if not levels:
            lines.append('    None')
    lines.extend(('', _NOTICE))
    return '\n'.join(lines)


def run_swing(args, parser) -> int:
    """Validate and execute one scan using read-only Robinhood or supplied bars."""
    offline = args.input is not None
    conflicts = [f"--{name.replace('_', '-')}" for name in _LIVE_OPTIONS if hasattr(args, name)]
    if offline and conflicts:
        parser.error('--input cannot be combined with ' + ', '.join(conflicts))
    if args.symbols is not None and not 1 <= len(args.symbols) <= robinhood.MAX_SYMBOLS:
        parser.error('--symbols requires 1..10 tickers')
    symbols = robinhood._symbols(args.symbols) if args.symbols is not None else None
    if not 5 <= args.focus_bars <= 120:
        parser.error('--focus-bars must be 5..120')

    now = datetime.now(timezone.utc)
    warmup_days = None
    acquisition = None
    specs = []
    if offline:
        groups = _offline_rows(Path(args.input), symbols, now)
        keys = set(groups)
    else:
        symbols = symbols or DEFAULT_SYMBOLS
        warmup_days = getattr(args, 'warmup_days', DEFAULT_WARMUP_DAYS)
        if not 60 <= warmup_days <= 1825:
            parser.error('--warmup-days must be 60..1825')
        timeout = getattr(args, 'timeout', 30.0)
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            parser.error('--timeout must be greater than 0 and at most 300 seconds')
        start = now - timedelta(days=warmup_days)
        adjustment = getattr(args, 'adjustment', 'split')
        strict = getattr(args, 'strict_interpolation', False)
        capture_dir = getattr(args, 'capture_dir', None)
        source = rh_runtime.source_identity('day', 'regular', adjustment, strict)
        keys = {(symbol, 'D', source) for symbol in symbols}
        specs = native_runtime.context_specs(
            [], interval='day', bounds='regular', enabled=not getattr(args, 'no_native_context', False))
        native_runtime.validate_native(symbols, start, now, specs, 'regular', adjustment)

    journal = _open_journal(args.db)
    try:
        if offline:
            for bar in _offline_pending(journal, groups):
                journal.ingest_observation(asdict(bar))
        else:
            _check_live_journal(journal, keys, start, now)
            try:
                with robinhood.open_robinhood(infra_root=getattr(args, 'infra_root', None),
                                             binary=getattr(args, 'codex_binary', 'codex'), timeout=timeout) as provider:
                    acquisition = rh_runtime.acquire(
                        provider, journal, symbols, start, now, interval='day', bounds='regular',
                        adjustment_type=adjustment, strict_interpolation=strict, capture_dir=capture_dir)
                    missing = set(acquisition['quality']['no_usable_symbols'])
                    _require_symbols(symbols, set(symbols) - missing)
                    if specs:
                        native_runtime.acquire_native(
                            provider, journal, symbols, start, now, specs, bounds='regular',
                            adjustment_type=adjustment, capture_dir=capture_dir)
            except robinhood.RobinhoodError as exc:
                raise ValueError(str(exc)) from None
        observed_at = datetime.now(timezone.utc)
        streams = [s for s in journal.snapshot(now=observed_at)['streams']
                   if (s['symbol'], s['timeframe'], s['source']) in keys]
        _require_symbols(symbols or (), {s['symbol'] for s in streams})
        order = {symbol: i for i, symbol in enumerate(symbols or ())}
        streams.sort(key=lambda s: (order.get(s['symbol'], 0), s['symbol'], s['source']))
        for stream in streams:
            if not specs:
                stream['native_interpretation'] = {'status': 'NOT_REQUESTED'}
                stream.pop('summary')
            if acquisition:
                stream['scan_acquisition_status'] = acquisition['status']
                stream['omitted_emitted'] = acquisition['omitted_emitted_by_symbol'].get(stream['symbol'], 0)
            stream['summary'] = _focused_summary(stream, args.focus_bars)
    finally:
        journal.close()
    if terminal_output(args.output, sys.stdout) == 'text':
        print(format_swing_report(streams, now=observed_at, focus_bars=args.focus_bars, warmup_days=warmup_days))
    else:
        for stream in streams:
            record = {key: stream[key] for key in ('symbol', 'timeframe', 'source', 'bar_count', 'last_bar_close',
                                                   'freshness', 'readiness', 'data_quality', 'summary')}
            record.update(session_close=_session_close(stream['last_bar_close']).isoformat(),
                          focus_bars=args.focus_bars, warmup_days=warmup_days, probability=None, mode='research_only',
                          acquisition_status=stream.get('scan_acquisition_status'),
                          omitted_emitted=stream.get('omitted_emitted'), notice=_NOTICE)
            print(json.dumps(record, ensure_ascii=False, allow_nan=False))
    return 0
