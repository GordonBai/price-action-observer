import copy
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import unittest

from pa_lens.context_summary import summarize_stream
from pa_lens.service import Journal
from pa_lens.timeframes import calendar


def bars(count, timeframe='D'):
    if timeframe == 'D':
        sessions = calendar().sessions_in_range('2026-10-05', '2026-11-17')[:count]
        closes = (calendar().session_close(session) for session in sessions)
    else:
        start = datetime(2026, 10, 5, 20, tzinfo=timezone.utc)
        step = timedelta(minutes=int(timeframe))
        closes = (start + i * step for i in range(count))
    return [
        dict(symbol='XYZ', timeframe=timeframe, time=closed.isoformat(),
             open=100, high=101, low=99, close=100, source='test')
        for closed in closes
    ]


def event(id_, bar, family, status='candidate', **fields):
    return dict(id=id_, observed_at=bar['time'].replace('+00:00', 'Z'), family=family,
                status=status, direction='long', explanation='结构观察', **fields)


class StreamSummaryTests(unittest.TestCase):
    def test_double_bottom_target_resolution_uses_confirmation_id(self):
        tape = bars(10)
        candidate = event('root', tape[0], 'double_bottom', anchors={'neckline': 101})
        confirmed = event('confirmation', tape[1], 'double_bottom', 'confirmed',
                          parent_id='root', trigger=102, stop=99, target=104)
        self.assertEqual(
            summarize_stream(tape[:1], [candidate], {})['active_structures']['live_setups'][0]['levels'],
            {'neckline': 101},
        )
        live = summarize_stream(tape[:2], [candidate, confirmed], {})['active_structures']['live_setups']
        self.assertEqual([(row['id'], row['status']) for row in live], [('root', 'confirmed')])
        self.assertEqual(live[0]['levels'], {'neckline': 101, 'trigger': 102, 'stop': 99, 'target': 104})
        for status in ('invalidated', 'reached'):
            with self.subTest(status=status):
                child = event('target', tape[3], 'measured_move', status, parent_id='confirmation')
                events = [candidate, confirmed, child]
                active = summarize_stream(tape[:4], events, {})['active_structures']
                self.assertEqual(active['live_setups'], [])
                resolved, = active['recent_resolved']
                self.assertEqual((resolved['family'], resolved['status'], resolved['target_state']),
                                 ('double_bottom', status, status))
                self.assertEqual(resolved['observed_at'], child['observed_at'])
                self.assertEqual(resolved['levels'], live[0]['levels'])
                self.assertEqual(summarize_stream(tape, events, {})['active_structures']['recent_resolved'], [])

    def test_already_touched_range_breakout_resolves_on_creation(self):
        tape = bars(1)
        breakout = event('break', tape[0], 'range_breakout', 'confirmed',
                         anchors={'high': 101, 'low': 99}, target=103,
                         target_state_at_creation='already_touched')
        active = summarize_stream(tape, [breakout], {})['active_structures']
        self.assertEqual(active['live_setups'], [])
        resolved, = active['recent_resolved']
        self.assertEqual((resolved['status'], resolved['target_state']), ('reached', 'reached'))
        self.assertEqual(resolved['levels'], {'range_high': 101, 'range_low': 99, 'target': 103})

    def test_final_flag_fanout_preserves_one_episode(self):
        tape = bars(3)
        stages = ('late_consolidation', 'continuation_breakout', 'breakout_failed')
        events = [
            event(str(i), bar, 'final_flag_development', anchors={'stage': stage, 'high': 101, 'low': 99},
                  **({'parent_id': '0'} if i else {}))
            for i, (bar, stage) in enumerate(zip(tape, stages))
        ]
        final, = summarize_stream(tape, events, {})['active_structures']['live_setups']
        self.assertEqual((final['id'], final['status'], final['stage']), ('0', 'candidate', 'breakout_failed'))
        self.assertEqual(final['levels'], {'range_high': 101, 'range_low': 99})

    def test_mtr_retest_and_attempts_are_observed_in_the_focus_window(self):
        tape = bars(4)
        events = [
            event('mtr', tape[0], 'mtr_development', anchors={'stage': 'trend_line_broken', 'line_value': 103}),
            event('test', tape[2], 'trend_line_retest', 'observed', parent_id='mtr', anchors={'line_value': 102}),
            event('attempt', tape[3], 'high_attempt', 'observed', attempt_label='H2',
                  anchors={'signal_bar_extreme': 101}),
        ]
        attempt, retest = summarize_stream(tape, events, {}, focus_bars=2)['active_structures']['live_setups']
        self.assertEqual((attempt['stage'], attempt['levels']), ('H2', {'signal_bar_extreme': 101}))
        self.assertEqual((retest['id'], retest['family'], retest['status'], retest['stage']),
                         ('mtr', 'mtr_development', 'observed', 'trend_line_retest'))
        self.assertEqual(retest['levels'], {'line_value': 102})

    def test_key_levels_and_reference_atr(self):
        tape = bars(22)
        tape[-5].update(high=108, low=94)
        tape[-2].update(high=110, low=92)
        setup = event('db', tape[-1], 'double_bottom', 'confirmed', anchors={'neckline': 103},
                      trigger=104, stop=95, target=109)
        duplicate = dict(setup, id='db2', target=109.00001)
        available = 'AVAILABLE_SOURCE_UNKNOWN'
        native = {
            'status': 'PARTIAL_NATIVE_CONTEXT',
            'ema20': dict(status=available, value='99.25', relation='above', distance='0.75', atr_multiple='0.38'),
            'atr14': dict(status=available, value='2'),
            'pivot_points': dict(status=available, value='100', values={'pivot': '100', 'r1': '105', 's1': '95'}),
        }
        result = summarize_stream(tape, [setup, duplicate], {
            'context': 'range_or_transition', 'total_bars': 500,
            'local_indicators': {'atr_engine': {'value': 1}},
        }, native)
        levels = result['key_levels']
        self.assertEqual([row['price'] for row in levels], sorted((row['price'] for row in levels), reverse=True))
        prices = {row['label']: row['price'] for row in levels}
        self.assertEqual(prices, {'SwHi': 108, 'SwLo': 94, 'PrevDayHi': 110, 'PrevDayLo': 92,
                                 '20B Hi': 110, '20B Lo': 92, 'Neckline': 103, 'Trig': 104,
                                 'Stop': 95, 'MM': 109.00001, 'EMA20': 99.25, 'Pivot P': 100, 'R1': 105, 'S1': 95})
        self.assertEqual(len(levels), len(prices))
        self.assertTrue(all(math.isfinite(row['distance']) and math.isfinite(row['atr_multiple']) for row in levels))
        self.assertEqual(next(row['atr_multiple'] for row in levels if row['label'] == 'EMA20'), .38)
        regime = result['regime']
        self.assertEqual((regime['bars_total'], regime['reference_atr'], regime['atr_origin']),
                         (500, 2, 'robinhood_native_atr14'))
        self.assertEqual([row['key'] for row in result['native_summary']['items']], ['ema20', 'atr14', 'pivot_points'])

    def test_segment_reset_clears_old_structures_and_technical_windows(self):
        tape = bars(22, '1')
        tape[-4].update(high=106, low=90)
        tape[-2]['time'] = '2026-10-06T13:31:00+00:00'
        tape[-1]['time'] = '2026-10-06T13:32:00+00:00'
        tape[-2]['close'] = 99
        events = [event('old', tape[-3], 'double_top'), event('new', tape[-2], 'double_bottom')]
        result = summarize_stream(tape, events, {'bars_in_segment': 2, 'context': 'warmup'})
        self.assertEqual(result['regime']['efficiency_20'], 1)
        self.assertEqual(result['regime']['focus_window_bars'], 22)
        self.assertEqual([row['id'] for row in result['active_structures']['live_setups']], ['new'])
        self.assertEqual({row['label']: row['price'] for row in result['key_levels']}, {'PDH': 106, 'PDL': 90})

    def test_prefix_is_deterministic_and_inputs_are_detached(self):
        tape = bars(5)
        events = [event('candidate', tape[1], 'opening_reversal', anchors={'opening_range': {'high': 101}}),
                  event('invalid', tape[3], 'opening_reversal', 'invalidated', parent_id='candidate')]
        native = {'status': 'UNAVAILABLE', 'ema20': {'status': 'UNAVAILABLE', 'reason': 'absent'}}
        before = copy.deepcopy((tape, events, native))
        state = {'local_indicators': {'atr_engine': {'value': 2}}}
        prefix = summarize_stream(tape[:3], events[:1], state, native)
        self.assertEqual(prefix, summarize_stream(tape[:3], events, state, native))
        self.assertIsNone(prefix['htf_alignment'])
        self.assertEqual(prefix['regime']['atr_origin'], 'local_engine_atr15')
        json.dumps(prefix, allow_nan=False)
        prefix['active_structures']['live_setups'][0]['levels']['range_high'] = -1
        prefix['native_summary']['items'][0]['reason'] = ''
        self.assertEqual((tape, events, native), before)

    def test_journal_snapshot_attaches_summary_to_every_stream(self):
        with closing(Journal(':memory:')) as journal:
            bar, = bars(1, '1')
            journal.ingest(bar)
            journal.ingest(dict(bar, symbol='ABC'))
            snapshot = journal.snapshot(datetime.fromisoformat(bar['time']))
        self.assertEqual(len(snapshot['streams']), 2)
        for stream in snapshot['streams']:
            self.assertEqual(stream['summary']['regime']['bars_total'], 1)
            self.assertEqual(stream['summary']['regime']['context'], stream['state']['context'])
            self.assertEqual(stream['summary']['native_summary']['status'], stream['native_interpretation']['status'])
