import unittest
from datetime import datetime,timedelta,timezone
from pa_lens.core import Bar
try:
    from pa_lens.observations import ObservationDetector
except ImportError:
    ObservationDetector=None


def bars(rows):
    start=datetime(2026,11,17,14,31,tzinfo=timezone.utc)
    return [Bar('TEST','1',(start+timedelta(minutes=i)).isoformat(),*r) for i,r in enumerate(rows)]

class ObservationTests(unittest.TestCase):
    def detector(self):
        self.assertIsNotNone(ObservationDetector,'ObservationDetector is not implemented')
        return ObservationDetector()
    def run_rows(self,rows,context='range_or_transition',atr=1):
        d=self.detector();events=[]
        for b in bars(rows):events.extend(d.update(b,context,atr))
        return d,events
    def test_ii_strict_full_range_not_body(self):
        _,e=self.run_rows([(10,15,5,10),(10,14,6,11),(11,13,7,12)])
        self.assertTrue(any(x['family']=='ii' for x in e))
        _,e=self.run_rows([(10,15,5,10),(10,14,6,11),(11,14,7,12)])
        self.assertFalse(any(x['family']=='ii' for x in e))
    def test_ioi_requires_four_bars(self):
        _,e=self.run_rows([(10,15,5,10),(10,14,6,11),(11,16,4,12),(12,15,5,13)])
        self.assertEqual(sum(x['family']=='ioi' for x in e),1)
    def test_trend_reversal_doji_evidence(self):
        _,e=self.run_rows([(10,11,9,10),(10,12,9.9,11.9),(10,11,7,10.8)])
        fs={x['family'] for x in e}
        self.assertTrue({'doji','trend_bar','reversal_bar'}<=fs)
    def test_microchannel_requires_strict_lows(self):
        _,e=self.run_rows([(10+i,11+i,9+i,10.8+i) for i in range(5)],'trend_up')
        self.assertTrue(any(x['family']=='micro_channel' and x['direction']=='long' for x in e))
        _,e=self.run_rows([(10,11+i,9,10.8) for i in range(5)],'trend_up')
        self.assertFalse(any(x['family']=='micro_channel' and x['direction']=='long' for x in e))
    def test_gaps_are_separate_and_causal(self):
        bs=bars([(10,11,9,10.5),(12,13,11.5,12.9),(14,15,13.5,14.5)])
        d=self.detector();a=d.update(bs[0],'trend_up',1);b=d.update(bs[1],'trend_up',1);c=d.update(bs[2],'trend_up',1)
        self.assertFalse(any(x['family']=='micro_gap' for x in b))
        self.assertTrue({'micro_gap','body_gap','gap_open'}<={x['family'] for x in c})
        self.assertTrue(all(x['observed_at']==bs[2].time for x in c))
    def test_barbwire_requires_doji_and_overlap(self):
        _,e=self.run_rows([(10,11,9,10)]*8)
        self.assertTrue(any(x['family']=='barbwire' for x in e))
        _,e=self.run_rows([(9.2,11,9,10.8)]*8)
        self.assertFalse(any(x['family']=='barbwire' for x in e))
    def test_breakout_then_followthrough_is_not_backdated(self):
        base=[(10,11,9,10)]*10
        bs=bars(base+[(10,12,9.9,11.8),(11.8,13,11.7,12.8)])
        d=self.detector();out=[d.update(b,'range_or_transition',1) for b in bs]
        self.assertFalse(any(x['family']=='breakout_follow_through' for x in out[-2]))
        ft=[x for x in out[-1] if x['family']=='breakout_follow_through']
        self.assertEqual(len(ft),1);self.assertEqual(ft[0]['status'],'confirmed')
    def test_breakout_failure_and_test_separate(self):
        base=[(10,11,9,10)]*10
        _,e=self.run_rows(base+[(10,12,9.9,11.8),(11.8,12,10.8,11.5)])
        self.assertTrue(any(x['family']=='breakout_test' for x in e))
        _,e=self.run_rows(base+[(10,12,9.9,11.8),(11.8,12,10,10.2)])
        self.assertTrue(any(x['family']=='failed_breakout' for x in e))
    def test_climax_only_candidate(self):
        _,e=self.run_rows([(10+i*.2,11+i*.2,9+i*.2,10.5+i*.2) for i in range(10)]+[(12,18,11.9,17.9)],'trend_up')
        xs=[x for x in e if x['family']=='climax']
        self.assertEqual(len(xs),1);self.assertEqual(xs[0]['status'],'candidate')
    def test_ema_first_return_after_separation(self):
        rows=[(10+i,11+i,9.9+i,10.9+i) for i in range(40)]
        d,e=self.run_rows(rows,'trend_up')
        b=Bar('TEST','1','2026-11-17T15:11:00+00:00',49,51,20,50)
        xs=d.update(b,'trend_up',1)
        self.assertTrue(any(x['family']=='ema_first_return' for x in xs))
    def test_prefix_duplicate_validation_and_bounds(self):
        rows=[(10+i*.01,11+i*.01,9+i*.01,10.5+i*.01) for i in range(300)]
        bs=bars(rows);d=self.detector();all_events=[]
        for b in bs:all_events.extend(d.update(b,'trend_up',1))
        q=self.detector();prefix=[]
        for b in bs[:100]:prefix.extend(q.update(b,'trend_up',1))
        self.assertEqual(prefix,[x for x in all_events if x['observed_at']<=bs[99].time])
        self.assertEqual(d.update(bs[-1],'trend_up',1),[])
        self.assertLessEqual(len(d.bars),32)
        with self.assertRaises(ValueError):d.update(bs[0],'trend_up',1)
        with self.assertRaises(ValueError):q.update(bs[100],'trend_up',float('nan'))
        for x in all_events:
            self.assertIsNone(x['probability']);self.assertTrue(x['knowledge_ids']);self.assertIn('工程',x['explanation'])
    def test_microgap_requires_directional_middle_bar(self):
        _,e=self.run_rows([(10,11,9,10.5),(12,15,8,12),(14,15,13.5,14.5)])
        self.assertFalse(any(x['family']=='micro_gap' for x in e))
    def test_breakout_test_can_preserve_space_without_touch(self):
        base=[(10,11,9,10)]*10
        _,e=self.run_rows(base+[(10,12,9.9,11.8),(11.8,13,11.6,12.8),(12.8,12.9,11.4,12)])
        tests=[x for x in e if x['family']=='breakout_test']
        self.assertEqual(len(tests),1)
        self.assertEqual(tests[0]['anchors']['test_type'],'space_preserved')
    def test_nested_doji_compression_is_not_directional_microchannel(self):
        _,events=self.run_rows([(10,15-i,5+i,10) for i in range(5)])
        self.assertFalse(any(e['family']=='micro_channel' for e in events))
