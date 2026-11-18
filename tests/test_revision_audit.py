import json
import tempfile
import unittest
from pathlib import Path
from pa_lens.service import Journal


def payload(minute=1, close=10):
    return dict(symbol='SOXL', timeframe='1', source='test', time=f'2026-01-02T14:{minute:02d}:00Z', open=10, high=12, low=9, close=close, volume=100)


class RevisionAuditTests(unittest.TestCase):
    def test_revision_quarantined_without_rewriting_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.db'
            j=Journal(path)
            j.ingest(payload())
            before=j.snapshot()['streams'][0]
            changed=payload(close=11); changed['token']='DO_NOT_SAVE'
            result=j.ingest_observation(changed)
            self.assertTrue(result['quarantined']); self.assertFalse(result['duplicate'])
            self.assertEqual(result['audit']['kind'],'revision')
            self.assertEqual(j.snapshot()['streams'][0]['bars'],before['bars'])
            self.assertEqual(j.snapshot()['streams'][0]['events'],before['events'])
            duplicate=j.ingest_observation(changed)
            self.assertTrue(duplicate['duplicate'])
            self.assertEqual(duplicate['audit']['fingerprint'],result['audit']['fingerprint'])
            self.assertNotIn('DO_NOT_SAVE',str(j.conn.execute('SELECT * FROM observation_audit').fetchall()))
            j.close(); j=Journal(path)
            self.assertEqual(j.health()['readiness'],'DATA_REVIEW_REQUIRED')
            self.assertFalse(j.health()['ready'])
            self.assertEqual(j.health()['data_quality']['quarantined_count'],1)
            self.assertEqual(j.health()['data_quality']['duplicate_count'],1)
            j.close()

    def test_volume_only_revision_marks_later_events_without_mutating_old(self):
        j=Journal(':memory:')
        try:
            for i in range(1, 20):
                j.ingest(payload(i))
            before=json.dumps(j.snapshot()['streams'][0]['events'],sort_keys=True)
            correction=payload(1); correction['volume']=101
            self.assertTrue(j.ingest_observation(correction)['quarantined'])
            self.assertEqual(json.dumps(j.snapshot()['streams'][0]['events'],sort_keys=True),before)
            result=j.ingest_observation(payload(20))
            self.assertEqual(result['data_quality'],'known_revision_or_late_data')
            self.assertTrue(result['events'])
            self.assertTrue(all(e['data_quality']=='known_revision_or_late_data' for e in result['events']))
        finally: j.close()

    def test_transport_persists_and_does_not_store_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.db'
            j=Journal(path)
            j.record_transport('test','SOXL','error','2026-01-02T15:00:00Z',0,error='secret-token')
            self.assertEqual(j.health()['readiness'],'TRANSPORT_ERROR')
            self.assertNotIn('secret-token',json.dumps(j.health()))
            j.close(); j=Journal(path)
            self.assertEqual(j.health()['transport'][0]['status'],'error')
            j.record_transport('test','SOXL','empty','2026-01-02T15:01:00Z',0)
            self.assertEqual(j.health()['transport'][0]['last_response_rows'],0)
            self.assertEqual(j.health()['readiness'],'WAITING_FOR_DATA')
            j.close()

    def test_restart_preserves_historical_event_quality(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.db'
            j=Journal(path)
            for i in range(1,20): j.ingest_observation(payload(i))
            j.ingest_observation(payload(1,11))
            j.ingest_observation(payload(20))
            events=j.snapshot()['streams'][0]['events']
            self.assertTrue(any('data_quality' not in e for e in events))
            self.assertTrue(any('data_quality' in e for e in events))
            j.close(); j=Journal(path)
            self.assertEqual(events,j.snapshot()['streams'][0]['events'])
            j.close()

    def test_late_arrival_and_stream_isolation(self):
        j=Journal(':memory:')
        try:
            j.ingest(payload(1)); j.ingest(payload(3))
            result=j.ingest_observation(payload(2))
            self.assertEqual(result['audit']['kind'],'late_arrival')
            self.assertIsNone(result['audit']['original'])
            self.assertEqual(j.snapshot()['streams'][0]['bar_count'],2)
            other=payload(); other['source']='other'
            j.ingest_observation(other)
            states=j.snapshot()['streams']
            self.assertEqual(states[0]['data_quality']['quarantined_count'],1)
            self.assertEqual(states[1]['data_quality']['quarantined_count'],0)
            self.assertFalse(j.ingest_observation(payload(4))['quarantined'])
        finally: j.close()

    def test_strict_ingest_and_invalid_payload_still_rejected(self):
        j=Journal(':memory:')
        try:
            j.ingest(payload(2))
            with self.assertRaises(ValueError): j.ingest(payload(2,11))
            with self.assertRaises(ValueError): j.ingest(payload(1))
            bad=payload(2,30)
            with self.assertRaises(ValueError): j.ingest_observation(bad)
            self.assertEqual(j.health()['data_quality']['quarantined_count'],0)
            self.assertTrue(j.ingest_observation(payload(2))['duplicate'])
        finally: j.close()

class RuntimeIdentityTests(unittest.TestCase):
    def test_ingestion_semantics_are_part_of_persisted_identity(self):
        import hashlib
        import pa_lens.service as service
        names=('core.py','advanced.py','observations.py','structures.py','explanations.py','presentation.py','service.py','feed.py','journal_lock.py','analytics.py','timeframes.py','robinhood.py','rh_runtime.py','provider_indicators.py','native_runtime.py')
        digest=hashlib.sha256()
        for name in names:
            digest.update(name.encode()+b'\0'+Path(service.__file__).with_name(name).read_bytes())
        self.assertEqual(service.CORE_SHA256,digest.hexdigest())

class ReceiptOrderingTests(unittest.TestCase):
    def test_same_or_backward_wall_clock_does_not_relabel_old_events(self):
        from unittest.mock import patch
        from datetime import datetime,timezone,timedelta
        for backward in (False,True):
            with self.subTest(backward=backward),tempfile.TemporaryDirectory() as folder:
                stamp=datetime(2026,11,18,15,0,tzinfo=timezone.utc)
                class Clock(datetime):
                    current=stamp
                    @classmethod
                    def now(cls,tz=None):return cls.fromtimestamp(cls.current.timestamp(),tz=tz)
                with patch('pa_lens.service.datetime',Clock):
                    path=Path(folder)/'db';j=Journal(path)
                    for i in range(1,20):j.ingest_observation(payload(i))
                    old=list(j.snapshot()['streams'][0]['events'])
                    if backward:Clock.current=stamp-timedelta(seconds=1)
                    j.ingest_observation(payload(1,11));j.ingest_observation(payload(20))
                    before=j.snapshot()['streams'][0]['events'];j.close();j=Journal(path)
                    self.assertEqual(before,j.snapshot()['streams'][0]['events'])
                    self.assertEqual(old,before[:len(old)])
                    self.assertTrue(any('data_quality' in e for e in before[len(old):]))
                    j.close()
