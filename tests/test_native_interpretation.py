import unittest
from datetime import datetime,timezone
from pa_lens.presentation import PresentationProjector

class NativeInterpretationTests(unittest.TestCase):
    def fixture(self):
        bar=dict(symbol='SOXL',timeframe='5',source='robinhood:5minute:regular:split',time='2026-11-18T16:00:00Z',close=11)
        row=dict(id=1,symbol='SOXL',indicator_type='ema',requested=dict(interval='5minute',bounds='regular',adjustment_type='split',parameters={'period':20},start='2026-11-18T14:30:00Z',end='2026-11-18T16:00:00Z'),returned_params={'period':20},status='AVAILABLE_SOURCE_UNKNOWN',latest=dict(time=bar['time'],values={'value':'10'}),received_at='2026-11-18T16:00:10Z',after_bar_seq=5,source_quality='unknown',warmup='unknown')
        return bar,row
    def test_matching_native_used_not_local_and_no_historical_backfill(self):
        from pa_lens.native_interpretation import interpret
        bar,row=self.fixture();now=datetime(2026,11,18,16,0,20,tzinfo=timezone.utc)
        result=interpret(bar,[row],now,5)
        self.assertEqual(result['ema20']['status'],'AVAILABLE_SOURCE_UNKNOWN')
        self.assertEqual(result['ema20']['relation'],'above')
        self.assertEqual(result['rsi14']['status'],'UNAVAILABLE')
        self.assertEqual(interpret(bar,[row],now,5,historical=True)['status'],'HISTORICAL_UNAVAILABLE')
    def test_wrong_period_timeframe_late_receipt_stale_and_error_unavailable(self):
        from pa_lens.native_interpretation import interpret
        now=datetime(2026,11,18,16,0,20,tzinfo=timezone.utc)
        for mutate in (lambda r:r['returned_params'].update(period=9),lambda r:r['requested'].update(interval='minute'),lambda r:r.update(received_at='2026-11-18T16:00:30Z'),lambda r:r.update(after_bar_seq=6),lambda r:r.update(status='PARTIAL'),lambda r:r.update(status='ERROR'),lambda r:r['latest'].update(time='2026-11-18T15:55:00Z')):
            bar,row=self.fixture();mutate(row)
            self.assertEqual(interpret(bar,[row],now,5)['ema20']['status'],'UNAVAILABLE')
        bar,row=self.fixture()
        self.assertEqual(interpret(bar,[row],datetime(2026,11,18,17,tzinfo=timezone.utc),5)['ema20']['status'],'UNAVAILABLE')
    def test_local_ema_family_never_primary_even_at_priority_zero(self):
        p=PresentationProjector(min_priority=0)
        e=dict(id='x',family='ema_gap',status='observed',observed_at='2026-11-18T16:00:00Z')
        p.update([e]);self.assertEqual(p.snapshot()['groups'],[])
    def test_default_context_requests_exact_periods_and_all_stays18(self):
        from pa_lens.native_runtime import native_specs,context_specs
        specs=context_specs([],interval='5minute')
        self.assertEqual({(r['type'],r['parameters']['period']) for r in specs},{('ema',20),('rsi',14)})
        self.assertEqual(len(context_specs(native_specs('all',None,'5minute','latest'),interval='5minute')),18)
        self.assertEqual(context_specs([],interval='15minute'),[])
        self.assertEqual(context_specs([],interval='5minute',enabled=False),[])
    def test_revision_quality_blocks_original_close_comparison(self):
        from pa_lens.native_interpretation import interpret
        bar,row=self.fixture()
        result=interpret(bar,[row],datetime(2026,11,18,16,0,20,tzinfo=timezone.utc),5,
                         bar_quality={'quarantined_count':1,'status':'DATA_REVIEW_REQUIRED'})
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertIn('修订',result['reason'])
    def test_cli_default_requests_native20_14_and_optout_does_not(self):
        from pa_lens.__main__ import main
        from unittest.mock import patch
        from contextlib import redirect_stdout
        from io import StringIO
        import tempfile
        from pathlib import Path
        for optout in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                args=['pa_lens','fetch-robinhood','--start','2026-11-18T14:30:00Z','--end','2026-11-18T16:00:00Z','--interval','5minute','--db',str(Path(tmp)/'x.db')]+(['--no-native-context'] if optout else [])
                with patch('sys.argv',args),patch('pa_lens.robinhood.open_robinhood'),patch('pa_lens.rh_runtime.acquire',return_value={}),patch('pa_lens.native_runtime.acquire_native',return_value=[]) as native,redirect_stdout(StringIO()):
                    main()
                    if optout:native.assert_not_called()
                    else:
                        self.assertEqual(native.call_count,1)
                        specs=native.call_args.args[5]
                        self.assertEqual({(s['type'],s['parameters']['period']) for s in specs},{('ema',20),('rsi',14)})
    def test_semantics_and_unusable_status_matrix(self):
        from pa_lens.native_interpretation import interpret
        now=datetime(2026,11,18,16,0,20,tzinfo=timezone.utc)
        for field,value in [('bounds','extended'),('adjustment_type','none')]:
            bar,row=self.fixture();row['requested'][field]=value
            self.assertEqual(interpret(bar,[row],now,5)['ema20']['status'],'UNAVAILABLE')
        for status in ('UNDEFINED','RAW_ONLY','EMPTY'):
            bar,row=self.fixture();row['status']=status
            self.assertEqual(interpret(bar,[row],now,5)['ema20']['status'],'UNAVAILABLE')
        bar,row=self.fixture();row['indicator_type']='rsi';row['returned_params']['period']=14;row['requested']['parameters']['period']=14
        result=interpret(bar,[row],now,5)
        self.assertEqual(result['status'],'PARTIAL_NATIVE_CONTEXT')
        self.assertEqual(result['ema20']['status'],'UNAVAILABLE')
        self.assertEqual(result['rsi14']['value'],'10')

    def test_journal_context_restart_same_asof(self):
        from pa_lens.service import Journal
        import tempfile
        from pathlib import Path
        bar,row=self.fixture();bar.update(open=10,high=12,low=9,volume=100)
        row.pop('id');row.pop('after_bar_seq');row.update(slot_key='synthetic',points=[],batches=[])
        now=datetime(2026,11,18,16,0,20,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.db';j=Journal(path);j.ingest(bar);j.record_native(row)
            before=j.snapshot(now)['streams'][0]['native_interpretation'];j.close()
            j=Journal(path)
            try:self.assertEqual(before,j.snapshot(now)['streams'][0]['native_interpretation'])
            finally:j.close()
