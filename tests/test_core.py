import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pa_lens.core import Bar, Config, Engine


def bars_from_lows(lows):
    start = datetime(2026, 11, 17, 14, 31, tzinfo=timezone.utc)
    return [Bar('SOXL', '1', (start+timedelta(minutes=i)).isoformat(), x+.5, x+1, x, x+.6) for i,x in enumerate(lows)]

class CoreTests(unittest.TestCase):
    def test_invalid_ohlc_and_naive_time(self):
        with self.assertRaises(ValueError): Bar('SOXL','1','2026-11-17T14:31:00Z',10,9,8,10)
        with self.assertRaises(ValueError): Bar('SOXL','1','2026-11-17T14:31:00',10,11,9,10)
        with self.assertRaises(ValueError): Bar('SOXL','1','2026-11-17T14:31:00Z',10,float('nan'),9,10)
    def test_pivot_confirmation_not_backdated(self):
        engine=Engine(Config(pivot_right=2,pivot_left=2,min_separation=3,tolerance_atr=.6))
        bars=bars_from_lows([12,11,10,11,12,11,10.1,11,12,13,14])
        outputs=[engine.update(b) for b in bars]
        candidates=[e for out in outputs for e in out if e['family']=='double_bottom' and e['status']=='candidate']
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['observed_at'],bars[8].time)
        self.assertEqual(candidates[0]['anchors']['second_time'],bars[6].time)
        confirmations=[e for out in outputs for e in out if e['family']=='double_bottom' and e['status']=='confirmed']
        self.assertTrue(confirmations)
        self.assertIsNone(confirmations[0]['probability'])
        self.assertGreater(confirmations[0]['target'],confirmations[0]['trigger'])
    def test_prefix_invariance(self):
        bars=bars_from_lows([12,11,10,11,12,11,10.1,11,12,13,14])
        a=Engine(); events=[]
        for b in bars: events.extend(a.update(b))
        for n in range(1,len(bars)+1):
            e=Engine(); prefix=[]
            for b in bars[:n]: prefix.extend(e.update(b))
            self.assertEqual(prefix,[v for v in events if v['observed_at']<=bars[n-1].time])
    def test_duplicate_and_revision(self):
        e=Engine(); b=bars_from_lows([10])[0]; e.update(b)
        self.assertEqual(e.update(b),[])
        with self.assertRaises(ValueError): e.update(replace(b,close=10.7))
        with self.assertRaises(ValueError): e.update(replace(b,time='2026-11-17T14:30:00+00:00'))
    def test_gap_resets_structure(self):
        e=Engine(); bs=bars_from_lows([10,11,12]); e.update(bs[0])
        ev=e.update(bs[2]); self.assertTrue(any(v['family']=='data_gap' for v in ev))
        self.assertEqual(e.snapshot()['bars_in_segment'],1)
    def test_top_mirror(self):
        lows=[12,11,10,11,12,11,10.1,11,12,13,14]
        bs=bars_from_lows(lows)
        e=Engine(); out=[]
        for b in bs:
            out+=e.update(replace(b,open=30-b.open,high=30-b.low,low=30-b.high,close=30-b.close))
        self.assertTrue(any(v['family']=='double_top' and v['status']=='confirmed' for v in out))
    def test_range_projection_explicit_anchors(self):
        e=Engine(Config(range_window=5,min_history=5)); bs=bars_from_lows([10,10.2,10,10.1,10,12])
        out=[]
        for b in bs: out+=e.update(b)
        events=[v for v in out if v['family']=='range_breakout']
        self.assertTrue(events)
        for v in events:
            if v['direction']=='long': self.assertAlmostEqual(v['target'],v['anchors']['high']*2-v['anchors']['low'])
    def test_no_cross_session_structure(self):
        e=Engine(); b=bars_from_lows([10])[0]; e.update(b)
        e.update(replace(b,time='2026-11-18T14:31:00Z'))
        self.assertEqual(e.snapshot()['bars_in_segment'],1)
    def test_source_and_timeframe_mixing_rejected(self):
        e=Engine(); b=bars_from_lows([10])[0]; e.update(b)
        with self.assertRaises(ValueError): e.update(replace(b,time='2026-11-17T14:32:00Z',source='other'))
    def test_config_invalid(self):
        with self.assertRaises(ValueError): Config(pivot_right=0)

if __name__=='__main__': unittest.main()

class ProjectionTests(unittest.TestCase):
    def test_equal_leg_has_explicit_anchors(self):
        from pa_lens.core import project_equal_leg
        result=project_equal_leg(100,110,105)
        self.assertEqual(result['target'],115)
        self.assertEqual(result['anchors'],{'a':100,'b':110,'c':105})
        self.assertEqual(project_equal_leg(110,100,105)['target'],95)
    def test_equal_leg_rejects_nan(self):
        from pa_lens.core import project_equal_leg
        with self.assertRaises(ValueError): project_equal_leg(1,float('nan'),3)

class LifecycleTests(unittest.TestCase):
    def test_invalidated_projection_cannot_later_reach(self):
        e=Engine();bs=bars_from_lows([12,11,10,11,12,11,10.1,11,12,13])
        all_events=[]
        for b in bs:all_events+=e.update(b)
        confirmed=[x for x in all_events if x['family']=='double_bottom' and x['status']=='confirmed'][0]
        t=parse= datetime.fromisoformat(bs[-1].time)
        bad=Bar('SOXL','1',(t+timedelta(minutes=1)).isoformat(),10,11,8,9)
        ev=e.update(bad)
        self.assertTrue(any(x['family']=='measured_move' and x['status']=='invalidated' and x['parent_id']==confirmed['id'] for x in ev))
        future=Bar('SOXL','1',(t+timedelta(minutes=2)).isoformat(),10,20,9,19)
        ev=e.update(future)
        self.assertFalse(any(x['status']=='reached' and x.get('parent_id')==confirmed['id'] for x in ev))

class BoundedStateTests(unittest.TestCase):
    def test_events_bounded_but_update_returns_new_events(self):
        e=Engine()
        start=datetime(2026,11,1,14,31,tzinfo=timezone.utc)
        for i in range(1200):
            # Alternate strict inside/outside shapes with constant close.
            width=1 if i%2 else 2
            b=Bar('SOXL','1',(start+timedelta(minutes=i)).isoformat(),10,10+width,10-width,10)
            out=e.update(b)
            if i: self.assertTrue(out)
        self.assertLessEqual(len(e.events),500)
        self.assertEqual(out[-1]['observed_at'],b.time)
    def test_bool_config_rejected(self):
        with self.assertRaises(ValueError):Config(pivot_right=True)
        with self.assertRaises(ValueError):Config(tick=True)

class AdvancedIntegrationTests(unittest.TestCase):
    def test_attempts_flow_through_engine_with_version(self):
        from test_advanced import bars
        e=Engine();out=[]
        for b in bars([15,14,13,14,14.5,13.5,14]):out+=e.update(b)
        events=[x for x in out if x['family']=='high_attempt']
        self.assertEqual([x['attempt_label'] for x in events],['H1','H2'])
        self.assertEqual(events[-1]['rule_version'],'pa-lens/0.3.0')
        self.assertIsNone(events[-1]['probability'])
    def test_gap_resets_advanced_episodes(self):
        from test_advanced import bars
        e=Engine();bs=bars([15,14,13,14]);out=[]
        for b in bs[:3]:e.update(b)
        out=e.update(replace(bs[-1],time='2026-11-17T15:00:00Z'))
        self.assertFalse(any(x['family']=='high_attempt' for x in out))

class StaleTargetTests(unittest.TestCase):
    def test_projection_already_reached_at_creation_not_tracked(self):
        e=Engine(Config(range_window=5,min_history=5))
        bs=bars_from_lows([10,10.2,10,10.1,10,14])
        out=[]
        for b in bs:out+=e.update(b)
        breakout=next(x for x in out if x['family']=='range_breakout')
        self.assertEqual(breakout.get('target_state_at_creation'),'already_touched')
        self.assertNotIn(breakout['id'],[p['id'] for p in e.projections])
