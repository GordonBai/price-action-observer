"""Non-trading, closed-bar observation audit and explicitly post-hoc path review.

No strategy, fill simulation, forecast score, or automatically invented ground
truth. All artifacts containing source bars are restricted to local_data/.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import Engine, parse_time
from .replay import _validated, load_bars, run_replay
from .presentation import summarize_events

NY = ZoneInfo('America/New_York')
KNOWN_CASE = '2026-11-17'


def session_date(bar):
    return parse_time(bar.time).astimezone(NY).date().isoformat()


def calendar_sample(bars):
    """First observed session of every ISO week; selected without seeing events."""
    weeks = {}
    for b in bars:
        day = parse_time(b.time).astimezone(NY).date()
        week = day.isocalendar()[:2]
        weeks.setdefault(week, day.isoformat())
    return sorted(weeks.values())


def future_path(bars, index, horizon):
    """Separate research diagnostic, never passed back to Engine.update()."""
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError('horizon must be a positive integer')
    current = bars[index]
    future = []
    previous = current
    for b in bars[index + 1:index + 1 + horizon]:
        if session_date(b) != session_date(current):
            break
        if parse_time(b.time)-parse_time(previous.time) != timedelta(minutes=int(current.timeframe)):
            break
        future.append(b)
        previous = b
    return {
        'mode': 'posthoc_price_path_not_pattern_correctness_or_trade_return',
        'not_available_at_observation': True,
        'requested_bars': horizon, 'bars_observed': len(future),
        'censored': len(future) < horizon,
        'reference_close': current.close,
        'end_time': future[-1].time if future else None,
        'end_close_change': future[-1].close-current.close if future else None,
        'maximum_high': max(b.high for b in future) if future else None,
        'minimum_low': min(b.low for b in future) if future else None,
        'note': '仅事后路径；不是胜率、盈亏、成交或形态真值。跨会话或缺数即截断。',
    }


def _anchor_times(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and (key.endswith('time') or key in ('start','end','confirmed_at','episode_start')):
                try:
                    yield parse_time(item).isoformat()
                except ValueError:
                    pass
            elif isinstance(item, (dict,list)):
                yield from _anchor_times(item)
    elif isinstance(value, list):
        for item in value:
            yield from _anchor_times(item)


def _fingerprint(events):
    return hashlib.sha256(json.dumps(events, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def audit_bars(bars, config=None, *, horizon=20, known_case_date=KNOWN_CASE):
    """Replay once, then attach historical evidence and independent future paths.

    Calendar sample consists of first session per ISO week plus known-case day.
    Prefix checks use 1,5,20,60,120 and final bar on each selected session. Each
    checkpoint is independently rebuilt from that session's first bar, consistent
    with Engine's session reset. The cross-session reset marker is excluded from
    this comparison, not from the exported event tape.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError('horizon must be a positive integer')
    bars = _validated(bars)
    if not bars:
        raise ValueError('audit requires at least one bar')
    replay = run_replay(bars, config)
    events = replay['events']
    index = {b.time: i for i,b in enumerate(bars)}
    by_day = defaultdict(list)
    events_day = defaultdict(list)
    for b in bars:
        by_day[session_date(b)].append(b)
    for e in events:
        events_day[session_date(bars[index[e['observed_at']]])].append(e)
    selected = calendar_sample(bars)
    if known_case_date in by_day and known_case_date not in selected:
        selected.append(known_case_date)
        selected.sort()
    checks = []
    for day in selected:
        session_bars = by_day[day]
        for count in sorted({min(n,len(session_bars)) for n in (1,5,20,60,120,len(session_bars))}):
            rebuilt = run_replay(session_bars[:count], config)['events']
            expected = [e for e in events_day[day] if e['observed_at'] <= session_bars[count-1].time and e['family'] != 'session_reset']
            checks.append({'session':day,'bars':count,'until':session_bars[count-1].time,
                           'passed':rebuilt==expected,'rebuilt_sha256':_fingerprint(rebuilt),
                           'full_prefix_sha256':_fingerprint(expected)})
    tape = []
    for e in events:
        i = index[e['observed_at']]
        times = set(_anchor_times(e.get('anchors', {})))
        times.update(b.time for b in bars[max(0,i-4):i+1] if session_date(b)==session_date(bars[i]))
        evidence = [asdict(bars[index[t]]) for t in sorted(times) if t in index and index[t] <= i]
        tape.append({'event':e, 'observed_bar':asdict(bars[i]), 'evidence_bars':evidence,
                     'evidence_note':'最近最多5根及可解析的历史锚点；完整窗口请按源行情复核，不是完整图表证明。',
                     'posthoc_path':future_path(bars,i,horizon),
                     'known_case_not_blind':session_date(bars[i])==known_case_date})
    annotations = []
    for day in selected:
        for e in events_day[day]:
            annotations.append({'kind':'emitted_event','session':day,'observed_at':e['observed_at'],
                                'event_id':e['id'],'family':e['family'],'review_label':None,
                                'reviewer':None,'notes':None,'missed_patterns':[],
                                'known_case_not_blind':day==known_case_date})
        for i in range(0,len(by_day[day]),60):
            window=by_day[day][i:i+60]
            annotations.append({'kind':'fixed_time_window','session':day,'start':window[0].time,
                                'end':window[-1].time,'event_id':None,'family':None,'review_label':None,
                                'reviewer':None,'notes':None,'missed_patterns':[],
                                'known_case_not_blind':day==known_case_date})
    display = summarize_events(events, min_priority=3, cooldown_minutes=15)
    display_counts = dict.fromkeys(by_day, 0)
    for group in display['groups']:
        day = parse_time(group['observed_at']).astimezone(NY).date().isoformat()
        display_counts[day] += 1
    observed_hours = sum(int(b.timeframe) for b in bars)/60
    display_summary = {
        'stats':display['stats'], 'config':display['config'],
        'presentation_version':display['presentation_version'],
        'groups_by_session':display_counts,
        'groups_per_session':display['stats']['displayed_groups']/len(by_day),
        'groups_per_hour':display['stats']['displayed_groups']/observed_hours,
        'observed_hours':observed_hours,
        'denominator_note':'观测bar数量×各bar周期，不含隔夜、缺失时段；不是墙钟覆盖时长。',
        'interpretation':'展示优先级与冷却仅降噪，不是置信度、准确率或交易建议；原始事件全部保留。',
    }
    package = Path(__file__).resolve().parent
    code_digest = hashlib.sha256()
    code_files = sorted(package.glob('*.py'))
    for source_file in code_files:
        code_digest.update(source_file.name.encode()+b'\0'+source_file.read_bytes()+b'\0')
    knowledge_file = package.parent/'knowledge'/'concepts.json'
    summary = dict(replay['summary'])
    summary.update({
        'mode':'observation_audit_no_trading_policy', 'schema':'pa-lens/audit-v1',
        'observer_code_sha256':code_digest.hexdigest(),
        'observer_code_files':[p.name for p in code_files],
        'knowledge_sha256':hashlib.sha256(knowledge_file.read_bytes()).hexdigest(),
        'known_case_date':known_case_date,'known_case_present':known_case_date in by_day,
        'known_case_note':'11/17已被观察，仅为已知案例，不是盲测。',
        'selection_rule':'first_observed_session_per_ISO_week_plus_known_case_no_event_or_return_selection',
        'sample_sessions':selected, 'sample_bars':sum(len(by_day[d]) for d in selected),
        'sample_events':sum(len(events_day[d]) for d in selected),
        'annotation_rows':len(annotations),'completed_human_labels':0,
        'precision':None,'recall':None,'insight_accuracy':None,
        'accuracy_note':'待独立人工标注；事件数量、因果一致性和后续涨跌都不是准确率。固定时间窗用于审查漏报。',
        'future_horizon_bars':horizon,
        'prefix_consistency':{'passed':all(c['passed'] for c in checks),'checks':len(checks),'details':checks},
        'event_count':len(events),
        'display_projection':display_summary,
        'sessions':len(by_day),
        'daily_events':{d:dict(Counter(e['family']+':'+e['status'] for e in es)) for d,es in events_day.items()},
        'limitations':['形态阈值为工程近似；语境或候选不等于方向预测。','仅已提供行情；不宣称完整市场时段或已核验复权。',
                       '样本内来源和已知案例有选择偏差；没有独立人工真值。','路径指标不含交易执行，也不构成投资建议。'],
    })
    return {'summary':summary,'events':tape,'annotations':annotations,
            'display_examples':display['groups'][:10]}


def write_audit(result, out):
    """Never accidentally export licensed raw bars into tracked/public locations."""
    root = Path(__file__).resolve().parents[1]/'local_data'
    out = Path(out).resolve()
    if not out.is_relative_to(root.resolve()) or out == root.resolve():
        raise ValueError('audit output must be a subdirectory of repository local_data/')
    out.mkdir(parents=True, exist_ok=True)
    (out/'summary.json').write_text(json.dumps(result['summary'],ensure_ascii=False,indent=2)+'\n')
    for key in ('events','annotations','display_examples'):
        (out/(key+'.jsonl')).write_text(''.join(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n' for row in result[key]))
    (out/'README.txt').write_text('LOCAL ONLY: includes third-party OHLCV evidence. Do not commit or redistribute without data rights.\n'
        'events.jsonl: causal events plus separate posthoc future paths.\n'
        'annotations.jsonl: blank human labels, including fixed time windows to detect omissions.\n'
        'No prediction accuracy, trading performance or verified human ground truth is claimed.\n')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--open-time-minutes',type=int)
    p.add_argument('--session',help='Optional NY session YYYY-MM-DD; warmup from that session only')
    p.add_argument('--horizon',type=int,default=20)
    args=p.parse_args(argv)
    bars=load_bars(args.input,open_time_minutes=args.open_time_minutes)
    if args.session:
        bars=[b for b in bars if session_date(b)==args.session]
    result=audit_bars(bars,horizon=args.horizon)
    result['summary']['input_file_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    write_audit(result,args.out)
    print(json.dumps({'bars':len(bars),'events':result['summary']['event_count'],
                      'sample_sessions':result['summary']['sample_sessions'],
                      'prefix_checks_passed':result['summary']['prefix_consistency']['passed'],
                      'accuracy':None},ensure_ascii=False))


if __name__=='__main__':
    main()
