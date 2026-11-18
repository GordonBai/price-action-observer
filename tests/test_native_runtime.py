import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from pa_lens.service import Journal
from pa_lens.provider_indicators import INDICATOR_FIELDS,IndicatorResult

START='2026-11-18T14:30:00Z'; END='2026-11-18T16:00:00Z'
class FakeNative:
    def __init__(self,fail=None):self.calls=[];self.fail=fail
    def indicators(self,symbols,start,end,indicator_type,interval,**kwargs):
        self.calls.append((symbols,start,end,indicator_type,interval,kwargs))
        if indicator_type==self.fail:raise ValueError('secret upstream exception must not leak')
        values={k:('-1' if k=='direction' else None if k=='histogram' else '12.30') for k in INDICATOR_FIELDS[indicator_type]}
        series=[dict(symbol=s,indicator_type=indicator_type,params=kwargs['parameters'],points=[dict(time='2026-11-18T15:55:00+00:00',begins_at='2026-11-18T15:50:00+00:00',values=values,missing_fields=[])],latest=dict(time='2026-11-18T15:55:00+00:00',values=values),series_id=s+indicator_type,batch=0,source='robinhood:native',interval=interval) for s in symbols]
        return IndicatorResult(tuple(series),(),({'request':{},'received_at':END},),dict(no_usable_symbols=[],normalization_supported=True,warmup='unknown',source_quality='unknown'),'robinhood:native',END)

class NativeRuntimeTests(unittest.TestCase):
    def test_all18_partial_failure_keeps_values_and_restart(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        specs=native_specs('all',None,'5minute','latest')
        self.assertEqual(len(specs),18)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'n.db';j=Journal(path);p=FakeNative('ema')
            try:
                summaries=acquire_native(p,j,['SOXL'],START,END,specs)
                self.assertEqual(len(summaries),18)
                self.assertEqual(next(s for s in summaries if s['indicator_type']=='ema')['status'],'ERROR')
                macd=next(s for s in summaries if s['indicator_type']=='macd')
                self.assertEqual(macd['latest']['values']['histogram'],None)
                supertrend=next(s for s in summaries if s['indicator_type']=='supertrend')
                self.assertEqual(supertrend['latest']['values']['direction'],'-1')
                before=j.snapshot()['native_indicators']
                self.assertNotIn('secret upstream',str(before))
            finally:j.close()
            j=Journal(path)
            try:self.assertEqual(before,j.snapshot()['native_indicators'])
            finally:j.close()

    def test_config_validation_before_calls_and_no_implicit_15m(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        with self.assertRaises(ValueError):native_specs('all',None,'15minute','latest')
        specs=native_specs(None,[{'type':'ema','parameters':{'period':20}},{'type':'ema','parameters':{'period':50}}],'5minute','latest')
        self.assertEqual(len(specs),2)
        with self.assertRaises(ValueError):native_specs(None,[{'type':'ema','account_number':'bad'}],'5minute','latest')
        j=Journal(':memory:');p=FakeNative()
        try:
            with self.assertRaises(ValueError):acquire_native(p,j,['SOXL'],START,END,specs+[{'type':'trade'}])
            self.assertEqual(p.calls,[])
        finally:j.close()

    def test_new_error_replaces_current_success_not_old_values(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        specs=native_specs('ema',None,'5minute','latest');j=Journal(':memory:')
        try:
            acquire_native(FakeNative(),j,['SOXL'],START,END,specs)
            acquire_native(FakeNative('ema'),j,['SOXL'],START,'2026-11-18T16:05:00Z',specs)
            rows=j.snapshot()['native_indicators']['items']
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'ERROR');self.assertIsNone(rows[0]['latest'])
            self.assertEqual(j.conn.execute('SELECT COUNT(*) FROM native_snapshots').fetchone()[0],2)
        finally:j.close()

    def test_cli_and_dashboard_native_contract(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-m','pa_lens','fetch-robinhood','--help'],capture_output=True,text=True)
        self.assertIn('--native-indicators',result.stdout)
        html=(Path(__file__).resolve().parents[1]/'pa_lens/dashboard.html').read_text()
        self.assertIn('id="native-indicators"',html)
        self.assertIn('历史定位隐藏原生快照',html)

    def test_empty_and_raw_only_visible_and_parameter_slots_distinct(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        from dataclasses import replace
        class EmptyNative(FakeNative):
            def indicators(self,*a,**kw):
                r=super().indicators(*a,**kw)
                return replace(r,series=(),quality={'normalization_supported':False,'no_usable_symbols':['SOXL']})
        j=Journal(':memory:')
        try:
            specs=native_specs(None,[{'type':'ema','parameters':{'period':20}},{'type':'ema','parameters':{'period':50}}],'5minute','latest')
            acquire_native(EmptyNative(),j,['SOXL'],START,END,specs)
            rows=j.native_snapshot()['items']
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r['status']=='RAW_ONLY' for r in rows))
            self.assertTrue(all(r['after_bar_seq']==0 for r in rows))
        finally:j.close()

    def test_native_window_restores_from_persisted_snapshot(self):
        from pa_lens.native_runtime import native_specs,acquire_native,restore_native_start
        specs=native_specs('ema',None,'5minute','latest')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'restore.db';j=Journal(path)
            acquire_native(FakeNative(),j,['SOXL'],START,END,specs);j.close();j=Journal(path)
            try:
                self.assertEqual(restore_native_start(j,['SOXL'],specs,'regular','split'),START)
                self.assertIsNone(restore_native_start(j,['QQQ'],specs,'regular','split'))
            finally:j.close()

    def test_native_does_not_mutate_pa_events_and_persists_sequence(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        from tests.test_service import sample
        j=Journal(':memory:')
        try:
            j.ingest(sample());before=j.snapshot()['streams']
            acquire_native(FakeNative(),j,['SOXL'],START,END,native_specs('macd',None,'5minute','latest'))
            after=j.snapshot()['streams']
            self.assertEqual([(s['events'],s['state']) for s in before],[(s['events'],s['state']) for s in after])
            self.assertEqual(j.native_snapshot()['items'][0]['after_bar_seq'],1)
        finally:j.close()

    def test_all_null_is_undefined_and_snapshot_points_bounded(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        from dataclasses import replace
        class Undefined(FakeNative):
            def indicators(self,*args,**kwargs):
                r=super().indicators(*args,**kwargs);row=r.series[0]
                row['latest']['values']={'value':None};row['points']=[row['latest']]*30
                return replace(r,quality={'normalization_supported':True,'no_usable_symbols':['SOXL']})
        j=Journal(':memory:')
        try:
            acquire_native(Undefined(),j,['SOXL'],START,END,native_specs('ema',None,'5minute','series'))
            row=j.native_snapshot()['items'][0]
            self.assertEqual(row['status'],'UNDEFINED');self.assertIsNone(row['latest']['values']['value'])
            self.assertEqual(row['point_count'],30);self.assertEqual(len(row['points']),20);self.assertTrue(row['points_truncated'])
        finally:j.close()

    def test_no_native_selection_makes_no_indicator_call(self):
        from pa_lens.native_runtime import acquire_native,native_specs,validate_native
        j=Journal(':memory:');p=FakeNative()
        try:
            self.assertEqual(acquire_native(p,j,['SOXL'],START,END,native_specs()),[])
            self.assertEqual(p.calls,[])
            with self.assertRaises(ValueError):validate_native([f'S{i}' for i in range(40)],START,END,native_specs('all',None,'5minute','latest'))
        finally:j.close()

    def test_restore_conflicting_windows_requires_explicit_choice(self):
        from pa_lens.native_runtime import native_specs,acquire_native,restore_native_start
        j=Journal(':memory:')
        try:
            acquire_native(FakeNative(),j,['SOXL'],START,END,native_specs('ema',None,'5minute','latest'))
            acquire_native(FakeNative(),j,['SOXL'],'2026-11-18T15:00:00Z',END,native_specs('rsi',None,'5minute','latest'))
            with self.assertRaisesRegex(ValueError,'native-window-start'):
                restore_native_start(j,['SOXL'],native_specs('ema,rsi',None,'5minute','latest'))
        finally:j.close()

    def test_all18_ten_symbols_visible_not_global64_truncated(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        j=Journal(':memory:')
        try:
            acquire_native(FakeNative(),j,[f'S{i}' for i in range(10)],START,END,native_specs('all',None,'5minute','latest'))
            result=j.native_snapshot()
            self.assertEqual(len(result['items']),180)
            self.assertFalse(result['truncated'])
        finally:j.close()

    def test_restore_error_releases_journal_and_never_opens_transport(self):
        from pa_lens.native_runtime import native_specs,acquire_native
        from pa_lens.__main__ import main
        from unittest.mock import patch
        from contextlib import redirect_stderr
        from io import StringIO
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'closed.db';j=Journal(path)
            acquire_native(FakeNative(),j,['SOXL'],START,END,native_specs('ema',None,'5minute','latest'))
            acquire_native(FakeNative(),j,['SOXL'],'2026-11-18T15:00:00Z',END,native_specs('rsi',None,'5minute','latest'));j.close()
            argv=['pa_lens','poll-robinhood','--once','--interval','5minute','--end',END,'--native-indicators','ema,rsi','--db',str(path)]
            with patch('sys.argv',argv),patch('pa_lens.robinhood.open_robinhood') as opened,redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):main()
                opened.assert_not_called()
            Journal(path).close()
