import unittest
from datetime import datetime,timezone
from pa_lens.presentation import PresentationProjector

INTRADAY_PACK = {
    'ema': {'period': 20}, 'vwap': {}, 'atr': {'period': 14},
    'rsi': {'period': 14}, 'pivot_points': {'method': 'classic'},
}
DAILY_PACK = {
    'ema': {'period': 20}, 'atr': {'period': 14}, 'rsi': {'period': 14},
    'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
}
AVAILABLE = 'AVAILABLE_SOURCE_UNKNOWN'

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
        for interval, pack in (('5minute', INTRADAY_PACK), ('day', DAILY_PACK)):
            with self.subTest(interval=interval):
                specs = context_specs([], interval=interval)
                self.assertEqual(specs, [
                    dict(type=name, parameters=params, interval=interval, output='last:2')
                    for name, params in pack.items()
                ])
                explicit = native_specs('all', None, interval, 'latest')
                self.assertEqual(len(context_specs(explicit, interval=interval)), 18)
                self.assertEqual({s['type'] for s in explicit if s['output'] == 'last:2'}, set(pack))

    def test_intraday_overlays_use_positive_atr_and_accept_empty_returned_parameters(self):
        from pa_lens.native_interpretation import interpret
        bar, ema = self.fixture()
        now = datetime(2026, 11, 18, 16, 0, 20, tzinfo=timezone.utc)
        levels = dict(pivot='11.00', r1='12', r2='13', r3='14', s1='10', s2='9', s3='8')
        rows = [ema]
        for name, params, values in (
            ('vwap', {}, {'value': '11.50'}),
            ('atr', {'period': 14}, {'value': '2'}),
            ('rsi', {'period': 14}, {'value': '50'}),
            ('pivot_points', {}, levels),
        ):
            rows.append(dict(
                ema, id=len(rows) + 1, indicator_type=name,
                requested=dict(ema['requested'], parameters=INTRADAY_PACK[name]),
                returned_params=params, latest=dict(time=bar['time'], values=values),
            ))
        context = interpret(bar, rows, now, 5)
        self.assertEqual(context['status'], AVAILABLE)
        self.assertEqual(context['pivot_points']['values'], levels)
        self.assertEqual(context['atr14']['value'], '2')
        for key, expected in {
            'ema20': ('10', 'above', '1', '0.50'),
            'vwap': ('11.50', 'below', '-0.50', '-0.25'),
            'pivot_points': ('11.00', 'equal', '0.00', '0.00'),
        }.items():
            self.assertEqual(tuple(context[key][field] for field in
                                   ('value', 'relation', 'distance', 'atr_multiple')), expected)
        rows[2]['status'] = 'UNDEFINED'
        context = interpret(bar, rows, now, 5)
        self.assertEqual(context['status'], 'PARTIAL_NATIVE_CONTEXT')
        for key in ('ema20', 'vwap', 'pivot_points'):
            self.assertEqual(context[key]['status'], AVAILABLE)
            self.assertIsNone(context[key]['atr_multiple'])
        rows[2].update(status=AVAILABLE, latest=dict(time=bar['time'], values={'value': '0'}))
        self.assertIsNone(interpret(bar, rows, now, 5)['vwap']['atr_multiple'])
        rows[-1]['requested']['parameters'] = {'method': 'fibonacci'}
        self.assertEqual(interpret(bar, rows, now, 5)['pivot_points']['status'], 'UNAVAILABLE')

    def test_friday_daily_pack_remains_fresh_on_sunday_with_optional_macd_delta(self):
        from pa_lens.native_interpretation import interpret
        bar, template = self.fixture()
        bar.update(timeframe='D', source='robinhood:day:regular:split', time='2026-11-20T21:00:00+00:00')
        macd_values = dict(macd='0.8', signal='0.5', histogram='0.3')
        rows = [
            dict(template, id=index, indicator_type=name,
                 requested=dict(template['requested'], interval='day', parameters=params),
                 returned_params=params, received_at='2026-11-20T21:00:10Z',
                 latest=dict(time=bar['time'], values=macd_values if name == 'macd' else {'value': '10'}))
            for index, (name, params) in enumerate(DAILY_PACK.items(), start=1)
        ]
        macd = rows[-1]
        macd['requested']['parameters'] = {}
        macd['points'] = [dict(time='2026-11-19T21:00:00+00:00', values={'histogram': '-0.2'}),
                          macd['latest']]
        sunday = datetime(2026, 11, 23, 1, tzinfo=timezone.utc)
        context = interpret(bar, rows, sunday, 5)
        self.assertEqual(context['status'], AVAILABLE)
        for key in ('ema20', 'atr14', 'rsi14', 'macd'):
            self.assertEqual(context[key]['status'], AVAILABLE)
        self.assertEqual(context['macd']['values'], macd_values)
        self.assertEqual(context['macd']['value'], '0.3')
        self.assertEqual(context['macd']['histogram_delta'], '0.5')
        macd['points'] = [macd['latest']]
        self.assertIsNone(interpret(bar, rows, sunday, 5)['macd']['histogram_delta'])
        macd['returned_params'] = {'fast_period': 9, 'slow_period': 26, 'signal_period': 9}
        self.assertEqual(interpret(bar, rows, sunday, 5)['status'], 'PARTIAL_NATIVE_CONTEXT')
        monday = datetime(2026, 11, 23, 23, tzinfo=timezone.utc)
        self.assertEqual(interpret(bar, rows, monday, 5)['status'], 'UNAVAILABLE')
        bar['time'] = '2026-11-21T00:00:00Z'
        for row in rows:
            row.update(received_at='2026-11-21T00:00:10Z')
            row['latest']['time'] = bar['time']
        self.assertEqual(interpret(bar, rows, sunday, 5)['ema20']['status'], AVAILABLE)

    def test_unsupported_streams_keep_legacy_keys_unavailable(self):
        from pa_lens.native_interpretation import interpret
        bar, row = self.fixture()
        now = datetime(2026, 11, 18, 16, 0, 20, tzinfo=timezone.utc)
        for overrides in (dict(source='manual'), dict(timeframe='15', source='robinhood:15minute:regular:split')):
            context = interpret(dict(bar, **overrides), [row], now, 5)
            self.assertEqual(context['ema20']['status'], 'UNAVAILABLE')
            self.assertEqual(context['rsi14']['status'], 'UNAVAILABLE')
            self.assertNotIn('vwap', context)
    def test_revision_quality_blocks_original_close_comparison(self):
        from pa_lens.native_interpretation import interpret
        bar,row=self.fixture()
        result=interpret(bar,[row],datetime(2026,11,18,16,0,20,tzinfo=timezone.utc),5,
                         bar_quality={'quarantined_count':1,'status':'DATA_REVIEW_REQUIRED'})
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertIn('修订',result['reason'])
    def test_cli_default_requests_native_pack_and_optout_does_not(self):
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
                        self.assertEqual({s['type']: s['parameters'] for s in specs}, INTRADAY_PACK)
                        self.assertTrue(all(s['output'] == 'last:2' for s in specs))
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
