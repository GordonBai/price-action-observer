import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from pa_lens.core import Bar
from pa_lens.replay import load_bars, run_replay, evaluate, evaluate_splits


def bar(t, o=10, h=11, l=9.5, c=10.5):
    return Bar('SOXL','1',f'2026-11-17T{t}:00Z',o,h,l,c,100,'test')


def setup(b, **kwargs):
    return {'id':'a','family':'double_bottom','status':'confirmed','direction':'long',
            'observed_at':b.time,'trigger':11.1,'stop':9,'target':13,**kwargs}


class ReplayTests(unittest.TestCase):
    def test_load_jsonl_and_csv(self):
        b=bar('14:31')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bars.jsonl';p.write_text(json.dumps(asdict(b))+'\n')
            self.assertEqual(load_bars(p),[b])
            p=Path(d)/'bars.csv';p.write_text('symbol,timeframe,time,open,high,low,close,volume,source\nSOXL,1,2026-11-17T14:31:00Z,10,11,9.5,10.5,100,test\n')
            self.assertEqual(load_bars(p),[b])
    def test_raw_open_time_requires_explicit_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.jsonl'
            raw={'symbol':'SOXL','timestamp':'2026-08-17T13:30:00Z','open':10,'high':11,'low':9,'close':10,'volume':100,'source':'alpaca','feed':'sip','adjustment':'connector_default_unverified'}
            p.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):load_bars(p)
            b=load_bars(p,open_time_minutes=1)[0]
            self.assertEqual(b.time,'2026-08-17T13:31:00+00:00')
            self.assertEqual(b.timeframe,'1')
            self.assertEqual(b.source,'alpaca:sip:connector_default_unverified')
            with self.assertRaises(ValueError):load_bars(p,open_time_minutes=0)
    def test_load_rejects_bad_order_missing_and_revision(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bars.jsonl'
            for records in ([asdict(bar('14:32')),asdict(bar('14:31'))], [{'symbol':'SOXL'}],
                            [asdict(bar('14:31')),asdict(bar('14:31',c=10.7))]):
                p.write_text('\n'.join(json.dumps(r) for r in records))
                with self.assertRaises(ValueError):load_bars(p)
    def test_replay_is_causal_and_counts(self):
        bs=[bar('14:31'),bar('14:32',h=10.9,l=9.6)]
        result=run_replay(bs)
        self.assertEqual(result['summary']['bars'],2)
        self.assertEqual(result['events'][0]['family'],'inside_bar')
        self.assertEqual(result['events'][0]['observed_at'],bs[1].time)
    def test_no_signal_bar_fill(self):
        b=bar('14:31',h=14)
        result=evaluate([b],[setup(b)])
        self.assertEqual(result['trades'],[])
    def test_gap_entry_and_stop_conservative(self):
        bs=[bar('14:31'),bar('14:32',o=12,h=12.2,l=8,c=9)]
        result=evaluate(bs,[setup(bs[0])],cost_bps=0)
        trade=result['trades'][0]
        self.assertEqual(trade['entry_price'],12)
        self.assertEqual(trade['exit_price'],9)
        self.assertEqual(trade['exit_reason'],'stop')
        self.assertEqual(result['summary']['ambiguous_bars'],1)
    def test_open_below_stop_cancels_before_later_trigger(self):
        bs=[bar('14:31'),bar('14:32',o=8,h=12,l=7,c=11)]
        result=evaluate(bs,[setup(bs[0])],cost_bps=0)
        self.assertEqual(result['trades'],[])
        self.assertEqual(result['summary']['cancelled_before_trigger'],1)
    def test_both_stop_target_conservative(self):
        bs=[bar('14:31'),bar('14:32',o=11.2,h=14,l=8,c=12)]
        trade=evaluate(bs,[setup(bs[0])],cost_bps=0)['trades'][0]
        self.assertEqual(trade['exit_reason'],'stop')
        self.assertTrue(trade['ambiguous'])
    def test_gap_beyond_target_skips(self):
        bs=[bar('14:31'),bar('14:32',o=14,h=15,l=13.5,c=14)]
        result=evaluate(bs,[setup(bs[0])])
        self.assertFalse(result['trades'])
        self.assertEqual(result['summary']['skipped_no_reward'],1)
    def test_costs_reduce_returns(self):
        bs=[bar('14:31'),bar('14:32',o=11.1,h=13.5,l=11,c=13)]
        a=evaluate(bs,[setup(bs[0])],cost_bps=0)
        b=evaluate(bs,[setup(bs[0])],cost_bps=5)
        self.assertGreater(a['summary']['net_return'],b['summary']['net_return'])
        self.assertEqual(b['summary']['turnover_sides'],2)
    def test_expiry_and_invalid_cost(self):
        bs=[bar('14:31'),bar('14:32'),bar('14:33',o=12,h=14,l=11,c=13)]
        self.assertFalse(evaluate(bs,[setup(bs[0])],expiry_bars=1)['trades'])
        with self.assertRaises(ValueError):evaluate(bs,[],cost_bps=-1)
    def test_short_not_traded_and_no_positive_reward(self):
        bs=[bar('14:31'),bar('14:32',h=14)]
        self.assertFalse(evaluate(bs,[setup(bs[0],direction='short')])['trades'])
        self.assertFalse(evaluate(bs,[setup(bs[0],target=10)])['trades'])
    def test_missing_bar_exits_at_next_observed_open(self):
        bs=[bar('14:31'),bar('14:32',o=11.2,h=12,l=11,c=11.8),bar('14:35',o=8,h=9,l=7,c=8)]
        result=evaluate(bs,[setup(bs[0])],cost_bps=0)
        trade=result['trades'][0]
        self.assertEqual(trade['exit_price'],8)
        self.assertEqual(trade['exit_reason'],'data_gap_exit')
    def test_eod_exit_not_overnight(self):
        bs=[bar('20:58'),bar('20:59',o=11.2,h=12,l=11,c=11.5),bar('21:00',o=11.5,h=12,l=11,c=11.6)]
        trade=evaluate(bs,[setup(bs[0])],cost_bps=0)['trades'][0]
        self.assertEqual(trade['exit_reason'],'scheduled_rth_close')
    def test_bad_event_time_rejected(self):
        bs=[bar('14:31')]
        with self.assertRaises(ValueError):evaluate(bs,[setup(bs[0],observed_at='2026-11-17T14:30:00Z')])
    def test_split_labels_and_missing_coverage(self):
        result=evaluate_splits([bar('14:31')],cost_grid=(0,3))
        self.assertEqual(result['splits']['known_case_2026_11_17']['bars'],1)
        self.assertEqual(result['splits']['development']['status'],'no_data')
        self.assertIn('not_blind',result['splits']['known_case_2026_11_17']['label'])

if __name__=='__main__':unittest.main()
