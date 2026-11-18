import unittest, copy
from datetime import datetime,timedelta,timezone
from pa_lens.core import Bar
from pa_lens.structures import StructureDetector

BASE=datetime(2026,11,17,14,31,tzinfo=timezone.utc)
def bar(i,o=10,h=11,l=9,c=10):
    return Bar('SOXL','1',(BASE+timedelta(minutes=i)).isoformat(),o,h,l,c)
def run(bs,context='trend_up',atr=1):
    d=StructureDetector();out=[]
    for b in bs:out.extend(d.update(b,context,atr))
    return out

class StructureTests(unittest.TestCase):
    def test_failed_failure_preserves_three_stage_chain(self):
        bs=[bar(i) for i in range(10)]
        bs += [bar(10,10.5,12,10.4,11.8),bar(11,11.5,11.6,10.2,10.5),bar(12,10.6,12,10.5,11.9)]
        es=[e for e in run(bs) if e['family']=='failed_failure']
        self.assertEqual([e['status'] for e in es],['candidate','confirmed'])
        self.assertEqual(es[-1]['parent_id'],es[0]['id'])
        self.assertEqual(es[-1]['anchors']['original_breakout_time'],bs[10].time)
        self.assertEqual(es[-1]['observed_at'],bs[12].time)
        self.assertIsNone(es[-1]['probability'])
    def test_breakout_without_prior_failure_not_failed_failure(self):
        bs=[bar(i) for i in range(10)]+[bar(10,10,12,9.5,11.8),bar(11,11.8,12.5,11.7,12.3)]
        self.assertFalse(any(e['family']=='failed_failure' for e in run(bs)))
    def test_gap_role_is_hypothesis_and_fill_not_reverse(self):
        bs=[bar(0),bar(1,10,13,9.5,12.8),bar(2,12.6,13.4,12.4,13),bar(3,13,13.6,12.6,13.2),bar(4,13.2,13.7,12.7,13.4),bar(5,13,13.5,10.8,11)]
        es=[e for e in run(bs) if e['family']=='gap_development']
        self.assertTrue(any(e['anchors']['stage']=='held' for e in es))
        self.assertTrue(any(e['anchors']['stage']=='filled' for e in es))
        self.assertTrue(all(e['status']=='observed' for e in es))
    def test_completed_higher_timeframe_not_published_early(self):
        bs=[bar(i,10+i*.1,11+i*.1,9+i*.1,10.1+i*.1) for i in range(10)]
        es=[e for e in run(bs) if e['family']=='higher_timeframe_bar']
        self.assertEqual([e['observed_at'] for e in es],[bs[4].time,bs[9].time])
        self.assertEqual(es[0]['anchors']['open'],10)
        self.assertEqual(es[0]['anchors']['close'],10.5)
        self.assertEqual(es[0]['anchors']['component_bars'],5)
    def test_partial_higher_timeframe_window_not_emitted(self):
        es=run([bar(i) for i in range(2,7)])
        self.assertFalse(any(e['family']=='higher_timeframe_bar' for e in es))
    def test_opening_requires_actual_open_coverage(self):
        es=run([bar(i) for i in range(20,30)]+[bar(30,10,12,9,10),bar(31,10,11,8,10)])
        self.assertFalse(any(e['family'].startswith('opening_') for e in es))
    def test_opening_both_sides_rejected_are_neutral_candidate(self):
        bs=[bar(i) for i in range(5)]+[bar(5,10,12,9.5,10.5),bar(6,10.5,11,8,10)]
        es=[e for e in run(bs) if e['family']=='opening_breakout_mode']
        self.assertEqual(len(es),1);self.assertEqual(es[0]['direction'],'neutral')
        self.assertEqual(es[0]['status'],'candidate')
        self.assertEqual(es[0]['observed_at'],bs[-1].time)
    def test_tight_channel_rejects_compression(self):
        bs=[bar(i,10,15-i*.2,5+i*.2,10) for i in range(9)]
        self.assertFalse(any(e['family']=='tight_channel' for e in run(bs)))
    def test_tight_channel_directional_candidate(self):
        bs=[bar(i,10+i*.5,10.7+i*.5,9.9+i*.5,10.5+i*.5) for i in range(9)]
        es=[e for e in run(bs) if e['family']=='tight_channel']
        self.assertEqual(len(es),1);self.assertEqual(es[0]['status'],'candidate')
    def test_prefix_invariance_and_no_mutation(self):
        bs=[bar(i,10+i%3*.2,11+i%3*.2,9+i%3*.2,10+i%3*.2) for i in range(35)]
        full=run(bs)
        for n in range(1,len(bs)+1):self.assertEqual(run(bs[:n]),[e for e in full if e['observed_at']<=bs[n-1].time])
        d=StructureDetector();old=[]
        for b in bs[:10]:old+=d.update(b,'trend_up',1)
        saved=copy.deepcopy(old)
        for b in bs[10:]:d.update(b,'trend_up',1)
        self.assertEqual(old,saved)
    def test_duplicates_revisions_and_bounded_state(self):
        d=StructureDetector();b=bar(0);d.update(b,'warmup',1)
        self.assertEqual(d.update(b,'warmup',1),[])
        with self.assertRaises(ValueError):d.update(bar(0,c=10.5),'warmup',1)
        for i in range(1,2000):d.update(bar(i),'range_or_transition',1)
        self.assertLessEqual(len(d.bars),90)
        self.assertLessEqual(len(d.gaps),8)

class DevelopmentTests(unittest.TestCase):
    def test_frozen_line_break_retest_and_mtr_development_not_full_mtr(self):
        lows=[10,10,9,10,11,11,10,11,12]
        bs=[bar(i,x+.4,x+1,x,x+.6) for i,x in enumerate(lows)]
        bs += [bar(9,10.4,11,9.5,9.8),bar(10,10.1,11.1,9.8,10.5),bar(11,10,10.2,9,9.3)]
        es=run(bs)
        lines=[e for e in es if e['family']=='trend_line']
        self.assertTrue(lines)
        self.assertEqual(lines[0]['anchors']['pivots'][1]['confirmed_at'],bs[8].time)
        stages=[e for e in es if e['family']=='mtr_development']
        self.assertEqual([e['anchors']['stage'] for e in stages],['trend_line_broken','local_reversal_evidence'])
        self.assertTrue(all(e['status']=='candidate' for e in stages))
        self.assertEqual(stages[-1]['observed_at'],bs[-1].time)
        self.assertEqual(stages[-1]['parent_id'],stages[0]['id'])
    def test_final_flag_candidate_before_failure_and_no_full_final_claim(self):
        bs=[bar(i,10+i*.5,10.7+i*.5,9.9+i*.5,10.5+i*.5) for i in range(10)]
        bs += [bar(i,15,15.5,14.7,15.1) for i in range(10,15)]
        bs += [bar(15,15.1,16,15,15.9),bar(16,15.8,15.9,14.8,15.1)]
        es=[e for e in run(bs) if e['family']=='final_flag_development']
        self.assertEqual([e['anchors']['stage'] for e in es],['late_consolidation','continuation_breakout','breakout_failed'])
        self.assertNotIn('failed-failure',es[-1]['knowledge_ids'])
        self.assertEqual(es[0]['observed_at'],bs[14].time)
        self.assertTrue(all(e['status']=='candidate' for e in es))
        self.assertEqual(es[-1]['parent_id'],es[0]['id'])
    def test_opening_invalidation_emits_once(self):
        bs=[bar(i,10,11,9,10.5) for i in range(5)]
        bs += [bar(5,9.5,10,8,8.5),bar(6,10,12,9.8,11.5),bar(7,11.5,13,11,12)]
        es=[e for e in run(bs) if e['family']=='opening_reversal']
        self.assertEqual([e['status'] for e in es],['candidate','invalidated'])

class CounterexampleTests(unittest.TestCase):
    def test_tight_channel_rejects_large_counter_wicks(self):
        bs=[bar(i,10+i*.5,18+i*.5,2+i*.5,10.5+i*.5) for i in range(9)]
        self.assertFalse(any(e['family']=='tight_channel' for e in run(bs)))
    def test_outside_opening_bar_does_not_invent_test_order(self):
        bs=[bar(i) for i in range(5)]+[bar(5,10,12,8,10)]
        self.assertFalse(any(e['family']=='opening_breakout_mode' for e in run(bs)))
    def test_mirror_failed_failure_and_tight_channel(self):
        from dataclasses import replace
        bs=[bar(i) for i in range(10)]+[bar(10,10.5,12,10.4,11.8),bar(11,11.5,11.6,10.2,10.5),bar(12,10.6,12,10.5,11.9)]
        mirror=[replace(b,open=50-b.open,high=50-b.low,low=50-b.high,close=50-b.close) for b in bs]
        a=[e for e in run(bs) if e['family']=='failed_failure'];b=[e for e in run(mirror,'trend_down') if e['family']=='failed_failure']
        self.assertEqual([e['status'] for e in a],[e['status'] for e in b]);self.assertTrue(all(e['direction']=='short' for e in b))
    def test_lifecycle_prefix_invariance(self):
        bs=[bar(i,10+i*.5,10.7+i*.5,9.9+i*.5,10.5+i*.5) for i in range(10)]
        bs += [bar(i,15,15.5,14.7,15.1) for i in range(10,15)]+[bar(15,15.1,16,15,15.9),bar(16,15.8,15.9,14.8,15.1)]
        full=run(bs)
        for n in range(1,len(bs)+1):self.assertEqual(run(bs[:n]),[e for e in full if e['observed_at']<=bs[n-1].time])
    def test_expired_failed_failure_not_resurrected(self):
        bs=[bar(i) for i in range(10)]+[bar(10,10.5,12,10.4,11.8),bar(11,11.5,11.6,10.2,10.5)]
        bs += [bar(i) for i in range(12,27)]+[bar(27,10,12,9.5,11.8)]
        es=[e for e in run(bs) if e['family']=='failed_failure']
        self.assertEqual([e['status'] for e in es],['candidate','expired'])
    def test_early_close_not_inferred_from_calendar_date(self):
        # No synthetic remaining-bar count or end-of-day claim is emitted.
        es=run([bar(i) for i in range(30)])
        self.assertTrue(all('expected_session_bars' not in e['anchors'] for e in es))
    def test_gap_after_window_does_not_reclassify_expired_history(self):
        bs=[bar(0),bar(1,10,13,9.5,12.8),bar(2,12.6,13.4,12.4,13)]
        bs += [bar(i,13,13.5,12.6,13.1) for i in range(3,18)]
        bs += [bar(18,13,13.5,10,11)]
        es=[e for e in run(bs) if e['family']=='gap_development' and e['anchors']['created_at']==bs[2].time]
        self.assertEqual(es[-1]['anchors']['stage'],'expired')

class AlignmentTests(unittest.TestCase):
    def test_second_offset_bars_are_not_rth_aligned_aggregate_or_opening(self):
        from dataclasses import replace
        bs=[replace(bar(i),time=(BASE+timedelta(minutes=i,seconds=30)).isoformat()) for i in range(10)]
        es=run(bs)
        self.assertFalse(any(e['family']=='higher_timeframe_bar' or e['family'].startswith('opening_') for e in es))
