import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pa_lens.core import Bar
from pa_lens.advanced import AdvancedDetector

def bars(highs):
    t=datetime(2026,11,17,14,31,tzinfo=timezone.utc)
    return [Bar('TEST','1',(t+timedelta(minutes=i)).isoformat(),h-1,h,h-2,h-1) for i,h in enumerate(highs)]

class AdvancedTests(unittest.TestCase):
    def collect(self,bs,context='trend_up'):
        d=AdvancedDetector();out=[]
        for b in bs:out+=d.update(b,context,1.0)
        return out
    def test_h2_needs_intervening_pullback(self):
        out=self.collect(bars([15,14,13,14,14.5,13.5,14]))
        hs=[e for e in out if e['family']=='high_attempt']
        self.assertEqual([e['attempt_count'] for e in hs],[1,2])
        self.assertEqual(hs[1]['anchors']['signal_bar_time'],bars([15,14,13,14,14.5,13.5,14])[5].time)
        self.assertEqual(hs[1]['context_label'],'bull_pullback')
        self.assertIsNone(hs[1]['probability'])
        self.assertNotIn('trigger',hs[1])
    def test_rising_highs_are_not_h2(self):
        out=self.collect(bars([15,14,13,14,14.2,14.4]))
        self.assertEqual([e['attempt_count'] for e in out if e['family']=='high_attempt'],[1])
    def test_mirror_low_attempt(self):
        bs=[replace(b,open=40-b.open,high=40-b.low,low=40-b.high,close=40-b.close) for b in bars([15,14,13,14,14.5,13.5,14])]
        ls=[e for e in self.collect(bs,'trend_down') if e['family']=='low_attempt']
        self.assertEqual([e['attempt_count'] for e in ls],[1,2])
        self.assertEqual(ls[1]['context_label'],'bear_pullback')
    def test_context_does_not_change_count(self):
        a=[e for e in self.collect(bars([15,14,13,14]),'trend_up') if e['family']=='high_attempt']
        b=[e for e in self.collect(bars([15,14,13,14]),'trend_down') if e['family']=='high_attempt']
        self.assertEqual(a[0]['attempt_count'],b[0]['attempt_count'])
        self.assertNotEqual(a[0]['context_label'],b[0]['context_label'])
    def test_outside_bar_does_not_invent_attempt_order(self):
        bs=bars([15,14,13]);last=bs[-1]
        bs.append(replace(last,time=(datetime.fromisoformat(last.time)+timedelta(minutes=1)).isoformat(),open=12,high=14,low=10,close=12))
        self.assertFalse(any(e['family']=='high_attempt' for e in self.collect(bs)))
    def test_episode_expiry(self):
        out=self.collect(bars([20,19]+[18]*25+[19]))
        hs=[e for e in out if e['family']=='high_attempt']
        self.assertFalse(hs)
    def test_three_push_confirmation_time_and_no_new_extreme_requirement(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11])
        out=self.collect(bs)
        wedge=[e for e in out if e['family']=='three_push_wedge']
        self.assertEqual(len(wedge),1)
        self.assertEqual(wedge[0]['direction'],'short')
        self.assertEqual(wedge[0]['observed_at'],bs[12].time)
        self.assertEqual(wedge[0]['anchors']['pushes'][-1]['time'],bs[10].time)
        self.assertEqual(wedge[0]['status'],'candidate')
    def test_repeated_equal_tops_not_directional_wedge(self):
        out=self.collect(bars([10,11,13,11,10,11,13,11,10,11,13,11,10]))
        self.assertFalse(any(e['family']=='three_push_wedge' for e in out))
    def test_prefix_invariance(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11])
        full=self.collect(bs)
        for n in range(1,len(bs)+1):
            self.assertEqual(self.collect(bs[:n]),[e for e in full if e['observed_at']<=bs[n-1].time])
    def test_bounded_state(self):
        d=AdvancedDetector()
        for b in bars([10+i%4 for i in range(1000)]):d.update(b,'range_or_transition',1)
        self.assertLessEqual(len(d.bars),5)
        self.assertLessEqual(len(d.swings),5)
    def test_duplicate_idempotent_and_invalid_atr(self):
        d=AdvancedDetector();b=bars([10])[0];d.update(b,'warmup',1)
        self.assertEqual(d.update(b,'warmup',1),[])
        with self.assertRaises(ValueError): d.update(b,'warmup',float('nan'))

class AdvancedLifecycleTests(unittest.TestCase):
    collect = AdvancedTests.collect
    def test_h2_crossing_reference_is_counted_before_episode_ends(self):
        out=self.collect(bars([15,14,13,14,13.5,17]))
        self.assertEqual([e['attempt_count'] for e in out if e['family']=='high_attempt'],[1,2])
        mirrored=[replace(b,open=40-b.open,high=40-b.low,low=40-b.high,close=40-b.close) for b in bars([15,14,13,14,13.5,17])]
        self.assertEqual([e['attempt_count'] for e in self.collect(mirrored,'trend_down') if e['family']=='low_attempt'],[1,2])

    def test_wedge_lifecycle_confirms_only_on_later_bar(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11,9])
        wedges=[e for e in self.collect(bs) if e['family']=='three_push_wedge']
        self.assertEqual([e['status'] for e in wedges],['candidate','confirmed'])
        self.assertEqual(wedges[1]['observed_at'],bs[-1].time)
        self.assertEqual(wedges[1]['confirmed_at'],bs[-1].time)
        self.assertEqual(wedges[1]['parent_id'],wedges[0]['id'])
        self.assertIn('swing-structure',wedges[0]['knowledge_ids'])
        self.assertNotIn('parabolic-wedge',wedges[0]['knowledge_ids'])
        self.assertIn('不是',wedges[1]['explanation'])
        self.assertIsNone(wedges[1]['probability'])

    def test_wedge_invalidates_on_new_original_direction_extreme(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11,15])
        w=[e for e in self.collect(bs) if e['family']=='three_push_wedge']
        self.assertEqual([e['status'] for e in w],['candidate','invalidated'])

    def test_wedge_expires_and_never_reuses_expired_candidate(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11]+[11]*22+[9])
        w=[e for e in self.collect(bs) if e['family']=='three_push_wedge']
        self.assertEqual([e['status'] for e in w],['candidate','expired'])

    def test_lifecycle_prefix_invariance(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11,9,11,15])
        full=self.collect(bs)
        for n in range(1,len(bs)+1):
            self.assertEqual(self.collect(bs[:n]),[e for e in full if e['observed_at']<=bs[n-1].time])

    def test_mirror_wedge_confirmation(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11,9])
        bs=[replace(b,open=40-b.open,high=40-b.low,low=40-b.high,close=40-b.close) for b in bs]
        w=[e for e in self.collect(bs,'trend_down') if e['family']=='three_push_wedge']
        self.assertEqual([e['status'] for e in w],['candidate','confirmed'])
        self.assertEqual(w[-1]['direction'],'long')

    def test_same_bar_confirmation_and_invalidation_is_not_confirmation(self):
        bs=bars([10,11,13,11,10,11,14,12,11,12,13.8,12,11,9])
        bs[-1]=replace(bs[-1],high=15)
        w=[e for e in self.collect(bs) if e['family']=='three_push_wedge']
        self.assertEqual([e['status'] for e in w],['candidate','invalidated'])

    def test_wedge_pending_state_is_bounded(self):
        d=AdvancedDetector()
        for b in bars([10+i%4 for i in range(2000)]):d.update(b,'range_or_transition',1)
        self.assertLessEqual(len(d.wedges),20)
