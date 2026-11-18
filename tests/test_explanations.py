import unittest
from pa_lens.core import Engine, Bar

class ExplanationTests(unittest.TestCase):
    def test_inside_event_has_grounded_cards_and_uncertainty(self):
        e=Engine()
        e.update(Bar('T','1','2026-11-17T14:31:00Z',10,12,9,11))
        events=e.update(Bar('T','1','2026-11-17T14:32:00Z',10,11,9.5,10.5))
        item=next(x for x in events if x['family']=='inside_bar')
        self.assertIn('inside-sequences',item.get('knowledge_ids',[]))
        self.assertTrue(item['knowledge_references'][0]['source_urls'])
        self.assertTrue(item['uncertainty'])
        self.assertEqual(item['interpretation_type'],'observation_not_recommendation')
    def test_snapshot_has_knowledge_version_and_observation_purpose(self):
        s=Engine().snapshot()
        self.assertEqual(s.get('purpose'),'pattern_observation_and_explanation')
        self.assertEqual(len(s.get('knowledge_version','')),64)
    def test_observation_detector_flows_through_engine(self):
        engine=Engine()
        out=engine.update(Bar('T','1','2026-11-17T14:31:00Z',10,11,9,10))
        event=next((x for x in out if x['family']=='doji'),None)
        self.assertIsNotNone(event)
        self.assertIn('candle-body-vs-range',event['knowledge_ids'])
        self.assertEqual(event['rule_version'],'pa-lens/0.3.0')
    def test_advanced_parent_ids_resolve_to_published_events(self):
        from datetime import datetime,timedelta,timezone
        start=datetime(2026,11,17,14,31,tzinfo=timezone.utc)
        e=Engine();events=[]
        for i,h in enumerate([10,11,13,11,10,11,14,12,11,12,13.8,12,11,9]):
            events+=e.update(Bar('T','1',(start+timedelta(minutes=i)).isoformat(),h-.5,h,h-1,h-.2))
        wedge=[x for x in events if x['family']=='three_push_wedge']
        self.assertEqual([x['status'] for x in wedge],['candidate','confirmed'])
        self.assertEqual(wedge[1]['parent_id'],wedge[0]['id'])
    def test_source_references_preserve_review_scope_and_locator(self):
        e=Engine();out=e.update(Bar('T','1','2026-11-17T14:31:00Z',10,11,9,10))
        refs=out[0]['knowledge_references'][0]
        self.assertTrue(refs.get('sources'))
        self.assertTrue(refs['sources'][0]['locator'])
        self.assertTrue(refs['sources'][0]['review_method'])
    def test_generic_wedge_not_equated_with_parabolic_acceleration(self):
        from pa_lens.explanations import ground_event
        event=ground_event({'family':'three_push_wedge'})
        self.assertNotIn('parabolic-wedge',event['knowledge_ids'])
