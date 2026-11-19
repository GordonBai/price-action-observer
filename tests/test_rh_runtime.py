import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from pa_lens.robinhood import RobinhoodProvider
from pa_lens.service import Journal

NOW=datetime(2026,11,18,15,tzinfo=timezone.utc)
def provider(flag='missing'):
    def transport(tool,args):
        row=dict(begins_at='2026-11-17T14:30:00Z',open_price='10',high_price='11',low_price='9',close_price='10.5',volume=100,session='reg')
        if flag!='missing':row['interpolated']=flag
        return {'data':{'results':[dict(symbol=s,interval=args['interval'],bounds=args['bounds'],bars=[row]) for s in args['symbols']]}}
    return RobinhoodProvider(transport,clock=lambda:NOW)

class RuntimeTests(unittest.TestCase):
    def fetch(self, journal, flag='missing', strict=False):
        from pa_lens.rh_runtime import acquire
        return acquire(provider(flag),journal,['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z',strict_interpolation=strict)
    def test_omitted_markers_achieve_ready_for_research_when_warm(self):
        from pa_lens.rh_runtime import acquire, aggregate_fifteen, quality_status
        from tests.test_robinhood import Stub, bar
        rows = [bar(f'2026-11-18T14:{m:02d}:00Z') for m in range(54, 60)]
        for row in rows:
            del row['interpolated']
        warm_provider = RobinhoodProvider(Stub(rows), clock=lambda: NOW)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.db'; j=Journal(path)
            try:
                report=acquire(warm_provider,j,['SOXL'],'2026-11-18T14:54:00Z','2026-11-18T15:00:00Z')
                self.assertEqual(report['ingested'],6)
                self.assertEqual(report['status'],'ELIGIBLE_OBSERVATIONS')
                self.assertEqual(report['omitted_emitted_by_symbol'], {'SOXL': 6})
                snap=j.snapshot(NOW)
                self.assertTrue(snap['ready'])
                self.assertEqual(snap['readiness'],'READY_FOR_RESEARCH')
                self.assertIsNone(snap['data_quality']['acquisition_status'])
                self.assertEqual(snap['acquisitions'][0]['bar_provenance'][0]['interpolation'],'omitted')
                self.assertEqual(snap['acquisitions'][0]['bar_provenance'][0]['quality'],'INTERPOLATION_OMITTED')
                self.assertNotIn('interpolation_omitted_opens', snap['acquisitions'][0]['quality'])
            finally:j.close()
            j=Journal(path)
            try:
                self.assertTrue(j.health(NOW)['ready'])
                self.assertEqual(j.health(NOW)['readiness'],'READY_FOR_RESEARCH')
            finally:j.close()
        five_rows = [bar(f'2026-11-18T14:{m}:00Z') for m in ('30', '35', '40')]
        for row in five_rows:
            del row['interpolated']
        derived = aggregate_fifteen(RobinhoodProvider(Stub(five_rows), clock=lambda: NOW).fetch(
            ['SOXL'], '2026-11-18T14:30:00Z', '2026-11-18T15:00:00Z', interval='5minute'))
        self.assertEqual(len(derived.bars), 1)
        self.assertEqual(derived.bar_provenance[0]['interpolation'], 'omitted')
        self.assertEqual(derived.bar_provenance[0]['quality'], 'INTERPOLATION_OMITTED')
        self.assertEqual(quality_status(derived.quality), 'ELIGIBLE_OBSERVATIONS')

    def test_malformed_or_true_interpolation_always_rejected_and_marks_partial(self):
        from pa_lens.rh_runtime import acquire, quality_status
        from tests.test_robinhood import Stub, bar
        omitted = bar('2026-11-18T14:58:00Z'); del omitted['interpolated']
        filled = bar('2026-11-18T14:59:00Z', interpolated=True)
        malformed = dict(bar('2026-11-18T14:57:00Z'), interpolated=None)
        p_partial = RobinhoodProvider(Stub([omitted, filled]), clock=lambda: NOW)
        j = Journal(':memory:')
        try:
            report = acquire(p_partial, j, ['SOXL'], '2026-11-18T14:57:00Z', '2026-11-18T15:00:00Z')
            self.assertEqual(report['ingested'], 1)
            self.assertEqual(report['quality']['interpolated'], 1)
            self.assertEqual(report['status'], 'PARTIAL_DATA')
            self.assertEqual(quality_status(report['quality']), 'PARTIAL_DATA')
            self.assertFalse(j.snapshot(NOW)['ready'])
        finally: j.close()
        j = Journal(':memory:')
        try:
            bad = self.fetch(j, None, strict=False)
            self.assertEqual(bad['ingested'], 0)
            self.assertEqual(bad['quality']['invalid'], 1)
            self.assertEqual(bad['status'], 'NO_USABLE_BARS')
        finally: j.close()

    def test_strict_omitted_and_true_never_become_bars(self):
        from pa_lens.rh_runtime import quality_status, source_identity
        for flag,strict,status in [('missing',True,'NO_USABLE_BARS'),(True,False,'NO_USABLE_BARS')]:
            j=Journal(':memory:')
            try:
                report=self.fetch(j,flag,strict)
                self.assertEqual(report['ingested'],0)
                self.assertEqual(j.snapshot()['streams'],[])
                self.assertEqual(j.snapshot()['data_quality']['status'],status)
            finally:j.close()
        self.assertEqual(quality_status(dict(emitted=1, interpolation_omitted=1, strict_interpolation=True)), 'PARTIAL_DATA')
        with self.assertRaisesRegex(ValueError, 'boolean'):
            source_identity('minute', strict_interpolation='yes')
    def test_explicit_false_and_duplicates(self):
        j=Journal(':memory:')
        try:
            self.assertEqual(self.fetch(j,False)['ingested'],1)
            self.assertEqual(self.fetch(j,False)['duplicates'],1)
            self.assertEqual(j.snapshot()['streams'][0]['bar_count'],1)
        finally:j.close()
    def test_runtime_dependency_in_identity(self):
        j=Journal(':memory:')
        try:self.assertIn('exchange_calendars_version',j.identity)
        finally:j.close()

    def test_cli_primary_commands_and_invalid_range_never_open_transport(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-m','pa_lens','fetch-robinhood','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        for option in ('--symbols','--start','--end','--interval','--strict-interpolation','--accept-unknown'):self.assertIn(option,result.stdout)
        from unittest.mock import patch
        from contextlib import redirect_stderr
        from io import StringIO
        from pa_lens.__main__ import main
        with patch('sys.argv',['pa_lens','fetch-robinhood','--start','bad','--end','bad']),patch('pa_lens.robinhood.open_robinhood') as opened:
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):main()
            opened.assert_not_called()

    def test_partial_and_revision_persist(self):
        from pa_lens.rh_runtime import quality_status
        self.assertEqual(quality_status(dict(emitted=1,invalid=1)), 'PARTIAL_DATA')
        self.assertEqual(quality_status(dict(emitted=1,missing_results=[{'symbols':['QQQ']}])), 'PARTIAL_DATA')
        j=Journal(':memory:')
        try:
            self.fetch(j,False)
            bar=dict(j.snapshot()['streams'][0]['bars'][0]);bar['close']=10.6
            self.assertTrue(j.ingest_observation(bar)['quarantined'])
            self.assertEqual(j.health()['data_quality']['status'],'DATA_REVIEW_REQUIRED')
        finally:j.close()

    def test_dashboard_separates_local_values_and_hides_future(self):
        html=(Path(__file__).resolve().parents[1]/'pa_lens/dashboard.html').read_text()
        self.assertIn('id="local-indicators"',html)
        self.assertIn('focusEvent?',html)
        self.assertIn('供应商指标未请求',html)
        self.assertIn("stream.timeframe==='D'",html)

    def test_all_adjustment_daily_only(self):
        from pa_lens.robinhood import _options
        _options('day','regular','all')
        with self.assertRaises(ValueError):_options('5minute','regular','all')

    def test_provider_errors_are_not_empty_success(self):
        p=RobinhoodProvider(lambda *_:{'data':{'results':[],'errors':[{'message':'restricted'}]}},clock=lambda:NOW)
        from pa_lens.robinhood import RobinhoodError
        with self.assertRaises(RobinhoodError):p.fetch(['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z')

    def test_fifteen_requires_three_complete_regular_inputs(self):
        from pa_lens.rh_runtime import aggregate_fifteen
        from tests.test_robinhood import Stub,bar
        p=RobinhoodProvider(Stub([bar(f'2026-11-17T14:{m}:00Z') for m in ('30','35','40','45')]),clock=lambda:NOW)
        raw=p.fetch(['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z',interval='5minute')
        result=aggregate_fifteen(raw)
        self.assertEqual(len(result.bars),1)
        self.assertEqual(result.bars[0].timeframe,'15')
        self.assertEqual(result.bars[0].volume,300)
        self.assertEqual(result.bars[0].time,'2026-11-17T14:45:00+00:00')
        self.assertEqual(result.bar_provenance[0]['derived_from'],'5minute')
        self.assertEqual(result.quality['incomplete_derived_buckets'],1)

    def test_aligned_delay_respects_settle(self):
        from pa_lens.rh_runtime import next_poll_delay
        self.assertEqual(next_poll_delay(datetime(2026,11,17,14,45,5,tzinfo=timezone.utc),'15minute',10),5)
        self.assertEqual(next_poll_delay(datetime(2026,11,17,14,45,10,tzinfo=timezone.utc),'15minute',10),900)
        self.assertEqual(next_poll_delay(datetime(2026,11,17,21,0,5,tzinfo=timezone.utc),'day',10),5)
        self.assertEqual(next_poll_delay(datetime(2026,11,17,21,0,10,tzinfo=timezone.utc),'day',10),86400)

    def test_fifteen_missing_cross_session_and_omitted(self):
        from pa_lens.rh_runtime import aggregate_fifteen, quality_status
        from tests.test_robinhood import Stub,bar
        rows=[bar('2026-11-17T14:30:00Z'),bar('2026-11-17T14:40:00Z'),bar('2026-11-18T14:35:00Z')]
        p=RobinhoodProvider(Stub(rows),clock=lambda:NOW)
        result=aggregate_fifteen(p.fetch(['SOXL'],'2026-11-17T14:30:00Z','2026-11-18T15:00:00Z',interval='5minute'))
        self.assertEqual(result.bars,())
        rows=[bar(f'2026-11-17T14:{m}:00Z') for m in ('30','35','40')]
        for row in rows:row.pop('interpolated')
        p=RobinhoodProvider(Stub(rows),clock=lambda:NOW)
        result=aggregate_fifteen(p.fetch(['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z',interval='5minute'))
        self.assertFalse(result.source.endswith(':strict_interpolation'))
        self.assertEqual(result.bar_provenance[0]['interpolation'],'omitted')
        self.assertEqual(result.bar_provenance[0]['quality'],'INTERPOLATION_OMITTED')
        self.assertEqual(quality_status(result.quality),'ELIGIBLE_OBSERVATIONS')
        strict=aggregate_fifteen(p.fetch(['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z',interval='5minute',strict_interpolation=True))
        self.assertEqual(strict.bars,())
        self.assertTrue(strict.source.endswith(':strict_interpolation'))
        self.assertEqual(quality_status(strict.quality),'NO_USABLE_BARS')

    def test_poll_window_catches_up_without_repulling_all_daily_history(self):
        from pa_lens.rh_runtime import poll_start
        self.assertEqual(poll_start(NOW,'minute',120,['2026-11-17T15:00:00Z']),datetime(2026,11,17,13,tzinfo=timezone.utc))
        self.assertEqual((NOW-poll_start(NOW,'day',120,['2026-11-18T00:00:00Z'])).days,7)

    def test_omitted_and_revision_flags_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'quality.db';j=Journal(path)
            try:
                self.fetch(j,'missing',strict=False)
                payload=dict(j.snapshot()['streams'][0]['bars'][0]);payload['close']=10.6
                j.ingest_observation(payload)
                payload['time']='2026-11-17T14:32:00Z';payload['close']=10.9
                j.ingest_observation(payload)
                events=j.snapshot()['streams'][0]['events']
                flagged=[e for e in events if 'known_revision_or_late_data' in e.get('data_quality_flags',[])]
                self.assertTrue(flagged)
                self.assertTrue(all(e['data_quality']=='known_revision_or_late_data' for e in flagged))
            finally:j.close()
            j=Journal(path)
            try:self.assertEqual(events,j.snapshot()['streams'][0]['events'])
            finally:j.close()

    def test_fifteen_transport_error_then_success_clears_same_key(self):
        from pa_lens.rh_runtime import acquire
        from pa_lens.robinhood import RobinhoodError
        from tests.test_robinhood import Stub,bar
        bad=RobinhoodProvider(Stub(fail='unavailable'),clock=lambda:NOW)
        good=RobinhoodProvider(Stub([bar(f'2026-11-17T14:{m}:00Z') for m in ('30','35','40')]),clock=lambda:NOW)
        j=Journal(':memory:')
        try:
            args=(j,['SOXL'],'2026-11-17T14:30:00Z','2026-11-17T15:00:00Z')
            with self.assertRaises(RobinhoodError):acquire(bad,*args,interval='15minute')
            acquire(good,*args,interval='15minute')
            rows=j.health()['transport']
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['status'],'success')
        finally:j.close()

    def test_fifteen_early_close_and_derived_quality_units(self):
        from pa_lens.rh_runtime import aggregate_fifteen
        from tests.test_robinhood import Stub,bar
        rows=[bar('2026-11-27T'+t+'Z') for t in ('17:45:00','17:50:00','17:55:00','18:00:00','18:05:00','18:10:00')]
        for row in rows:row.pop('interpolated')
        p=RobinhoodProvider(Stub(rows),clock=lambda:datetime(2026,11,28,tzinfo=timezone.utc))
        r=aggregate_fifteen(p.fetch(['SOXL'],'2026-11-27T17:45:00Z','2026-11-27T19:00:00Z',interval='5minute'))
        self.assertEqual(len(r.bars),1)
        self.assertEqual(r.bars[0].time,'2026-11-27T18:00:00+00:00')
        self.assertEqual(r.quality['derived_omitted_emitted'],1)
        self.assertEqual(r.quality['omitted_emitted'],6)
        self.assertEqual(r.quality['derived_unknown_emitted'],0)

    def test_added_daily_symbol_gets_bootstrap_history(self):
        from pa_lens.rh_runtime import poll_start
        self.assertEqual((NOW-poll_start(NOW,'day',120,['2026-11-18T00:00:00Z'],expected_streams=2)).days,180)

    def test_poll_boundary_does_not_create_false_late_arrival(self):
        from pa_lens.rh_runtime import poll_start
        end=datetime(2026,11,17,16,46,56,tzinfo=timezone.utc)
        first=poll_start(end,'minute',30,[])
        second=poll_start(end.replace(minute=47),'minute',30,['2026-11-17T16:46:00Z'])
        self.assertEqual(first,datetime(2026,11,17,16,16,tzinfo=timezone.utc))
        self.assertGreaterEqual(second,first)
        self.assertEqual(poll_start(end,'15minute',30,[]),datetime(2026,11,17,16,15,tzinfo=timezone.utc))

    def test_delayed_stream_window_never_precedes_initial_coverage(self):
        from pa_lens.rh_runtime import poll_start
        end=datetime(2026,11,17,16,46,56,tzinfo=timezone.utc)
        first='2026-11-17T16:16:00Z'
        later=poll_start(end,'minute',30,['2026-11-17T16:43:00Z'],coverage_start=first)
        self.assertEqual(later,datetime(2026,11,17,16,16,tzinfo=timezone.utc))

    def test_two_poll_rounds_aligned_and_real_hole_still_quarantined(self):
        from pa_lens.rh_runtime import acquire,poll_windows,source_identity
        from tests.test_robinhood import bar
        for missing in (False,True):
            phase=[0]
            def transport(tool,args):
                rows=[bar(f'2026-11-17T16:{m:02d}:00Z') for m in range(10,45)
                      if not (missing and phase[0]==0 and m==20)]
                left=datetime.fromisoformat(args['start_time'].replace('Z','+00:00'))
                rows=[r for r in rows if datetime.fromisoformat(r['begins_at'].replace('Z','+00:00'))>=left]
                return {'data':{'results':[dict(symbol='SOXL',interval='minute',bounds='regular',bars=rows)]}}
            p=RobinhoodProvider(transport,clock=lambda:NOW)
            j=Journal(':memory:');source=source_identity('minute');end=datetime(2026,11,17,16,46,56,tzinfo=timezone.utc)
            try:
                windows=poll_windows(j,['SOXL'],end,'minute',30,source)
                first=acquire(p,j,windows[0][0],windows[0][1],end)
                phase[0]=1
                later=poll_windows(j,['SOXL'],end.replace(minute=47),'minute',30,source)
                self.assertEqual(later[0][1],windows[0][1])
                result=acquire(p,j,later[0][0],later[0][1],end.replace(minute=47))
                self.assertEqual(result['quarantined'],int(missing))
            finally:j.close()

    def test_coverage_survives_restart_and_new_symbol_has_separate_window(self):
        from pa_lens.rh_runtime import poll_windows,source_identity
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'c.db';j=Journal(path)
            self.fetch(j,False);j.close();j=Journal(path)
            try:
                source=source_identity('minute')
                self.assertEqual(j.coverage_start('SOXL','1',source),'2026-11-17T14:30:00Z')
                windows=poll_windows(j,['SOXL','QQQ'],NOW,'minute',30,source)
                self.assertEqual(len(windows),2)
                self.assertEqual({tuple(w[0]) for w in windows},{('SOXL',),('QQQ',)})
            finally:j.close()
