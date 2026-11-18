import copy
import unittest
from datetime import datetime, timedelta, timezone
from pa_lens.presentation import summarize_events


def event(i, family='double_bottom', status='candidate', direction='long', minute=None):
    t=datetime(2026,11,17,14,31,tzinfo=timezone.utc)+timedelta(minutes=i if minute is None else minute)
    return {'id':str(i),'observed_at':t.isoformat(),'family':family,'status':status,'direction':direction,'context':'range_or_transition','explanation':'观察，不是订单'}

class PresentationTests(unittest.TestCase):
    def test_raw_unchanged_and_basic_hidden(self):
        es=[event(0,'doji','observed'),event(1)];before=copy.deepcopy(es)
        r=summarize_events(es)
        self.assertEqual(es,before)
        self.assertEqual(r['stats']['raw_events'],2)
        self.assertEqual(r['stats']['hidden_by_priority'],1)
        self.assertEqual(r['groups'][0]['event_ids'],['1'])
    def test_same_bar_aggregates_and_keeps_every_id(self):
        es=[event(1),event(2,'three_push_wedge',minute=1)]
        r=summarize_events(es)
        self.assertEqual(len(r['groups']),1)
        self.assertEqual(r['groups'][0]['event_ids'],['1','2'])
        self.assertEqual(len(r['groups'][0]['events']),2)
    def test_repeated_key_cooldown_but_confirmation_distinct(self):
        es=[event(0),event(1),event(2,status='confirmed'),event(15)]
        r=summarize_events(es)
        self.assertEqual([x for g in r['groups'] for x in g['event_ids']],['0','2','15'])
        self.assertEqual(r['stats']['hidden_by_cooldown'],1)
    def test_zero_cooldown_and_priority_zero_show_all(self):
        es=[event(0,'doji','observed'),event(1),event(2)]
        r=summarize_events(es,min_priority=0,cooldown_minutes=0)
        self.assertEqual(r['stats']['displayed_events'],3)
    def test_prefix_invariance(self):
        es=[event(i) for i in range(40)]
        full=summarize_events(es)
        for n in range(1,len(es)+1):
            p=summarize_events(es[:n])
            self.assertEqual(p['groups'],[g for g in full['groups'] if g['observed_at']<=es[n-1]['observed_at']])
    def test_key_uses_direction_and_status(self):
        es=[event(0),event(1,direction='short'),event(2,status='invalidated')]
        self.assertEqual(summarize_events(es)['stats']['displayed_events'],3)
    def test_observation_context_not_instruction(self):
        g=summarize_events([event(0)])['groups'][0]
        self.assertIn('观察优先',g['context_note'])
        self.assertNotIn('买入',g['context_note'])
    def test_duplicate_ids_do_not_inflate_display(self):
        e=event(0)
        r=summarize_events([e,e],cooldown_minutes=0)
        self.assertEqual(r['stats']['displayed_events'],1)
        self.assertEqual(r['stats']['hidden_duplicate_ids'],1)
    def test_invalid_parameters_and_order_rejected(self):
        for kwargs in ({'min_priority':True},{'min_priority':4},{'cooldown_minutes':-1},{'cooldown_minutes':float('nan')}):
            with self.assertRaises(ValueError):summarize_events([],**kwargs)
        with self.assertRaises(ValueError):summarize_events([event(2),event(1)])
    def test_return_is_detached_from_raw(self):
        e=event(0);r=summarize_events([e]);r['groups'][0]['events'][0]['explanation']='changed'
        self.assertEqual(e['explanation'],'观察，不是订单')

class IncrementalPresentationTests(unittest.TestCase):
    def test_incremental_full_tape_matches_batch(self):
        from pa_lens.presentation import PresentationProjector
        es=[event(i,status='confirmed' if i%5==0 else 'candidate') for i in range(80)]
        p=PresentationProjector();observed=[]
        for e in es:observed+=p.update([e])
        expected=summarize_events(es)
        self.assertEqual(observed,expected['groups'])
        self.assertEqual(p.snapshot(),expected)
    def test_trailing_window_eviction_does_not_reopen_cooldown(self):
        from pa_lens.presentation import PresentationProjector
        p=PresentationProjector(cooldown_minutes=1000)
        p.update([event(0)])
        for i in range(1,250):p.update([event(i,family='other-'+str(i),status='candidate')])
        self.assertEqual(len(p.snapshot()['groups']),200)
        self.assertEqual(p.update([event(250)]),[])
    def test_repeated_ingest_does_not_duplicate_visible_records(self):
        from pa_lens.presentation import PresentationProjector
        p=PresentationProjector();e=event(0);p.update([e]);groups=p.snapshot()['groups']
        self.assertEqual(p.update([e]),[])
        self.assertEqual(p.snapshot()['groups'],groups)
        self.assertEqual(p.snapshot()['stats']['displayed_events'],1)
    def test_invalid_batch_does_not_partially_apply(self):
        from pa_lens.presentation import PresentationProjector
        p=PresentationProjector()
        with self.assertRaises(ValueError):p.update([event(3),event(2)])
        self.assertEqual(p.snapshot()['stats']['raw_events'],0)
