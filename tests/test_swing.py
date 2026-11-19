from contextlib import nullcontext, redirect_stderr, redirect_stdout
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pa_lens.__main__ import main
from pa_lens.robinhood import HISTORICALS, INDICATORS, RobinhoodProvider
from pa_lens.service import Journal
from pa_lens.timeframes import calendar, daily_close


class SwingTests(unittest.TestCase):
    def fixture(self, *, legacy=False):
        path = Path(__file__).resolve().parents[1] / 'examples/pa/synthetic_double_bottom.jsonl'
        pattern = [json.loads(line) for line in path.read_text().splitlines()][:10]
        dates = calendar().sessions_in_range('2025-08-01', '2025-11-03')[-40:]
        rows = []
        for date, row in zip(dates, [pattern[0]] * 30 + pattern):
            close = daily_close(str(date.date()))
            if legacy:
                close = datetime.combine(date.date() + timedelta(days=1), datetime.min.time(), timezone.utc)
            rows.extend(dict(row, symbol=symbol, timeframe='D', time=close.isoformat())
                        for symbol in ('NVDA', 'QQQ'))
        return rows

    def run_cli(self, argv, *, tty=False):
        out = io.StringIO()
        with patch.object(out, 'isatty', return_value=tty), redirect_stdout(out):
            self.assertEqual(main(['swing', *argv]), 0)
        return out.getvalue()

    def test_offline_jsonl_warms_all_bars_then_focuses_and_formats(self):
        rows = self.fixture(legacy=True)
        rows += [dict(rows[-1], source='alternate_fixture')]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bars.jsonl'
            path.write_text('\n'.join(map(json.dumps, reversed(rows))))
            args = ['--input', str(path), '--focus-bars', '15']
            text = self.run_cli([*args, '--output', 'text'])
            for value in ('NVDA', 'QQQ', 'warmup=40 bars', 'focus=15 bars',
                          '2025-11-03 16:00:00 EST', 'range_or_transition', 'double_bottom / confirmed',
                          'Neckline 13', 'Trig 14.01', 'Stop 9.99', 'MM 16',
                          'PrevDayHi', 'PrevDayLo', 'Research only', 'probability=None'):
                self.assertIn(value, text)
            records = [json.loads(line) for line in self.run_cli(args).splitlines()]
            self.assertEqual({(r['symbol'], r['source']) for r in records}, {
                ('NVDA', 'synthetic_fixture'), ('QQQ', 'synthetic_fixture'), ('QQQ', 'alternate_fixture')})
            for record in (r for r in records if r['source'] == 'synthetic_fixture'):
                regime = record['summary']['regime']
                self.assertEqual((regime['bars_total'], regime['focus_window_bars']), (40, 15))
                self.assertIn('double_bottom', {r['family'] for r in record['summary']['active_structures']['live_setups']})
                self.assertIsNone(record['probability'])
            self.assertIn('probability=None', self.run_cli(args, tty=True))

    def test_csv_symbol_filter_and_reused_database_isolation(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bars.csv'
            db = Path(tmp) / 'scan.db'
            rows = self.fixture()
            with path.open('w', newline='') as fp:
                writer = csv.DictWriter(fp, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            args = ['--input', str(path), '--db', str(db)]
            self.run_cli(args)
            record, = map(json.loads, self.run_cli([*args, '--symbols', 'QQQ']).splitlines())
            self.assertEqual(record['symbol'], 'QQQ')
            self.assertEqual(record['summary']['regime']['bars_total'], 40)
            other = Path(tmp) / 'other.jsonl'
            other.write_text(json.dumps(dict(rows[-1], source='other')))
            report, = map(json.loads, self.run_cli(['--input', str(other), '--db', str(db)]).splitlines())
            self.assertEqual((report['symbol'], report['source']), ('QQQ', 'other'))

            other.write_text(json.dumps(rows[-3]))
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit):
                main(['swing', '--input', str(other), '--db', str(db)])
            self.assertIn('already contains bars after this input', err.getvalue())

    def test_offline_input_validation(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bars.jsonl'
            base = ['swing', '--input', str(path)]
            good = self.fixture()[-1]
            cases = [
                ('', [], 'no daily bars'),
                (json.dumps(dict(good, timeframe='1')), [], 'timeframe D'),
                (json.dumps(good), ['--symbols', 'SPY'], 'SPY'),
                (json.dumps(good), ['--symbols', 'QQQ', 'SPY'], 'SPY'),
                (json.dumps(good), ['--symbols', *(f'S{i}' for i in range(11))], '1..10'),
                (json.dumps(good), ['--focus-bars', '4'], '5..120'),
            ]
            for flag, value in (('--warmup-days', '250'), ('--infra-root', '/not/used'),
                                ('--codex-binary', 'codex'), ('--timeout', '30'),
                                ('--adjustment', 'split'), ('--capture-dir', tmp),
                                ('--strict-interpolation', None), ('--no-native-context', None)):
                cases.append((json.dumps(good), [flag] if value is None else [flag, value], flag))
            for raw, flags, message in cases:
                with self.subTest(flags=flags, raw=raw):
                    path.write_text(raw)
                    err = io.StringIO()
                    with redirect_stderr(err), self.assertRaises(SystemExit):
                        main([*base, *flags])
                    self.assertIn(message, err.getvalue())

    def test_live_uses_day_regular_daily_pack_and_memory_journal(self):
        calls = []
        names = ['NVDA', 'QQQ']
        now = datetime.now(timezone.utc)
        sessions = calendar().sessions_in_range((now - timedelta(days=10)).date(), now.date())
        session = next(str(day.date()) for day in reversed(sessions) if daily_close(str(day.date())) <= now)
        begins_at = f'{session}T00:00:00Z'

        def transport(tool, args):
            calls.append((tool, args))
            self.assertEqual((args['symbols'], args['interval'], args['bounds'], args['adjustment_type']),
                             (names, 'day', 'regular', 'split'))
            if tool == HISTORICALS:
                row = dict(begins_at=begins_at, open_price='10', high_price='11', low_price='9',
                           close_price='10.5', volume=100, session='reg')
                return {'data': {'results': [
                    dict(symbol='NVDA', interval='day', bounds='regular', bars=[row]),
                    dict(symbol='QQQ', interval='day', bounds='regular', bars=[dict(row, interpolated=False)]),
                ]}}
            indicator = args['type']
            params = ({key: args[key] for key in ('fast_period', 'slow_period', 'signal_period')}
                      if indicator == 'macd' else {'period': args['period']})
            values = (dict(macd='1.2', signal='1', histogram='0.2') if indicator == 'macd'
                      else dict(value={'ema': 10, 'atr': 2, 'rsi': 55}[indicator]))
            return {'data': {'results': [
                dict(symbol=name, interval='day', bounds='regular', indicators=[
                    dict(type=indicator, params=params, series=[dict(begins_at=begins_at, **values)])])
                for name in names]}}

        with TemporaryDirectory() as tmp, \
             patch('pa_lens.robinhood.open_robinhood', return_value=nullcontext(RobinhoodProvider(transport))), \
             patch('pa_lens.service.Journal', wraps=Journal) as journal:
            flags = ['--symbols', *names, '--warmup-days', '250', '--focus-bars', '25']
            report = self.run_cli([*flags, '--output', 'text'])
            self.assertIn('Interp marker: omitted by provider', report.split('QQQ')[0])
            self.assertNotIn('Interp marker: omitted by provider', report.split('QQQ')[1])
            self.assertEqual(journal.call_args.args[0], ':memory:')
            records = [json.loads(row) for row in self.run_cli(flags).splitlines()]
            self.assertEqual([(row['symbol'], row['omitted_emitted']) for row in records],
                             [('NVDA', 1), ('QQQ', 0)])
            self.assertIn('EMA20 10 | close above +0.5 (+0.25 ATR)', report)
            self.assertIn('MACD 1.2 / Sig 1 / Hist 0.2', report)
            persisted_flags = [*flags, '--db', str(Path(tmp) / 'live.db')]
            self.run_cli(persisted_flags)
            previous_calls = len(calls)
            optout = self.run_cli([*persisted_flags, '--no-native-context'])
            self.assertEqual([tool for tool, _ in calls[previous_calls:]], [HISTORICALS])
            self.assertTrue(all(json.loads(line)['summary']['native_summary']['status'] == 'NOT_REQUESTED'
                                for line in optout.splitlines()))
        self.assertIn('warmup=1 bars', report)
        self.assertIn('250 calendar days', report)
        self.assertEqual({(args['type'], args['output']) for tool, args in calls if tool == INDICATORS},
                         {(name, 'last:2') for name in ('ema', 'atr', 'rsi', 'macd')})
