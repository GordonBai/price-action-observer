import importlib.util
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from pa_lens.core import Bar


class AuditTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pa_lens.audit'), 'audit module is not implemented')
        from pa_lens import audit
        return audit

    def bars(self, n=40, start='2026-11-17T14:31:00+00:00'):
        t=datetime.fromisoformat(start)
        return [Bar('SOXL','1',(t+timedelta(minutes=i)).isoformat(),100,102 if i%2==0 else 101,98 if i%2==0 else 99,100,10,'synthetic') for i in range(n)]

    def test_event_tape_preserves_closed_bar_and_excludes_future_evidence(self):
        result=self.api().audit_bars(self.bars(), horizon=5)
        self.assertTrue(result['events'])
        for row in result['events']:
            self.assertEqual(row['event']['observed_at'],row['observed_bar']['time'])
            self.assertTrue(all(b['time']<=row['event']['observed_at'] for b in row['evidence_bars']))
            self.assertTrue(row['posthoc_path']['not_available_at_observation'])
        self.assertIsNone(result['summary']['precision'])
        self.assertEqual(result['summary']['known_case_date'],'2026-11-17')

    def test_future_path_stops_at_gap_or_session_and_never_counts_current_bar(self):
        a=self.api();bs=self.bars(3)
        bs.append(Bar('SOXL','1','2026-11-17T14:40:00+00:00',100,200,1,150))
        p=a.future_path(bs,1,5)
        self.assertEqual(p['bars_observed'],1)
        self.assertEqual(p['maximum_high'],102)
        self.assertTrue(p['censored'])
        self.assertEqual(a.future_path(self.bars(1),0,5)['bars_observed'],0)

    def test_calendar_sample_is_fixed_weekday_rule_not_event_selected(self):
        a=self.api();bs=self.bars(1,'2026-08-17T14:31:00+00:00')+self.bars(1,'2026-08-18T14:31:00+00:00')+self.bars(1,'2026-08-24T14:31:00+00:00')
        self.assertEqual(a.calendar_sample(bs),['2026-08-17','2026-08-24'])

    def test_prefix_checks_match_and_annotation_stays_unreviewed(self):
        result=self.api().audit_bars(self.bars(), horizon=5)
        self.assertTrue(result['summary']['prefix_consistency']['passed'])
        self.assertGreater(result['summary']['prefix_consistency']['checks'],0)
        self.assertTrue(result['annotations'])
        self.assertTrue(all(x['review_label'] is None for x in result['annotations']))
        self.assertTrue(any(x['kind']=='fixed_time_window' for x in result['annotations']))

    def test_multiday_prefix_reset_and_future_session_boundary(self):
        a=self.api();bs=self.bars(40)+self.bars(40,'2026-11-18T14:31:00+00:00')
        result=a.audit_bars(bs)
        self.assertTrue(result['summary']['prefix_consistency']['passed'])
        self.assertEqual(a.future_path(bs,39,5)['bars_observed'],0)

    def test_reproducibility_hashes_and_no_trade_metrics(self):
        result=self.api().audit_bars(self.bars())
        self.assertIn('observer_code_sha256',result['summary'])
        self.assertEqual(len(result['summary']['observer_code_sha256']),64)
        self.assertEqual(len(result['summary']['knowledge_sha256']),64)
        self.assertNotIn('win_rate',result['summary'])
        self.assertNotIn('net_return',result['summary'])

    def test_display_projection_uses_observed_bar_hours_not_overnight_span(self):
        a=self.api();bs=self.bars(40)+self.bars(40,'2026-11-18T14:31:00+00:00')
        result=a.audit_bars(bs)
        self.assertIn('display_projection',result['summary'])
        d=result['summary']['display_projection']
        self.assertEqual(d['config'],{'min_priority':3,'cooldown_minutes':15})
        self.assertEqual(d['observed_hours'],80/60)
        self.assertEqual(d['groups_per_hour'],d['stats']['displayed_groups']/(80/60))
        self.assertEqual(d['groups_per_session'],d['stats']['displayed_groups']/2)
        self.assertEqual(sum(d['groups_by_session'].values()),d['stats']['displayed_groups'])
        self.assertNotIn('groups',d)
        self.assertLessEqual(len(result['display_examples']),10)
        self.assertEqual(len(result['events']),result['summary']['event_count'])

    def test_bad_horizon_and_empty_input(self):
        a=self.api()
        for value in [0,-1,True,1.5]:
            with self.assertRaises(ValueError):a.audit_bars(self.bars(),horizon=value)
        with self.assertRaises(ValueError):a.audit_bars([])

    def test_write_only_to_repository_local_data(self):
        a=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):a.write_audit(a.audit_bars(self.bars()),Path(tmp))
        target=Path(a.__file__).resolve().parents[1]/'local_data'/'test-audit-output'
        try:
            a.write_audit(a.audit_bars(self.bars()),target)
            self.assertTrue((target/'summary.json').exists())
            self.assertTrue((target/'events.jsonl').exists())
        finally:
            import shutil
            if target.exists():shutil.rmtree(target)


if __name__=='__main__':unittest.main()
