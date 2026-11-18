import unittest
from datetime import datetime,timezone
from pa_lens.feed import connector_bars as _connector_bars
def connector_bars(payload,symbol,feed,now):return _connector_bars(payload,symbol,feed,now,retrieved_at=now)

def payload(feed='iex'):
 return {'tool':'get_stock_bars','request':{'symbols':['SOXL'],'timeframe':'1Min','feed':feed},'bars':{'SOXL':[{'symbol':'SOXL','timestamp':'2026-11-17T14:30:00Z','open':10,'high':11,'low':9,'close':10.5,'volume':100}]}}
class ConnectorFeedTests(unittest.TestCase):
 def test_feed_identity_adjustment_and_close(self):
  b=connector_bars(payload(),'SOXL','iex',datetime(2026,11,17,14,32,tzinfo=timezone.utc))[0]
  self.assertEqual(b.time,'2026-11-17T14:31:00+00:00')
  self.assertEqual(b.source,'alpaca-connector:iex:adjustment_unverified')
 def test_wrong_feed_not_silent_fallback(self):
  with self.assertRaises(ValueError):connector_bars(payload('sip'),'SOXL','iex',datetime.now(timezone.utc))
 def test_unfinished_bar_not_imported(self):
  self.assertEqual(connector_bars(payload(),'SOXL','iex',datetime(2026,11,17,14,31,2,tzinfo=timezone.utc)),[])
 def test_error_and_missing_provenance_rejected(self):
  for p in ({'error':{}},{'bars':payload()['bars']}):
   with self.assertRaises(ValueError):connector_bars(p,'SOXL','iex',datetime.now(timezone.utc))
 def test_nonminute_and_mixed_symbol_rejected(self):
  for change in ('timeframe','symbol'):
   p=payload()
   if change=='timeframe':p['request']['timeframe']='5Min'
   else:p['bars']['SOXL'][0]['symbol']='AAPL'
   with self.assertRaises(ValueError):connector_bars(p,'SOXL','iex',datetime.now(timezone.utc))
 def test_order_revisions_rejected_before_return(self):
  p=payload();p['bars']['SOXL'].append(dict(p['bars']['SOXL'][0],close=10.7))
  with self.assertRaises(ValueError):connector_bars(p,'SOXL','iex',datetime.now(timezone.utc))

 def test_old_partial_snapshot_never_becomes_closed_by_waiting(self):
  rows=_connector_bars(payload(),'SOXL','iex',datetime(2026,11,17,15,tzinfo=timezone.utc),retrieved_at=datetime(2026,11,17,14,30,50,tzinfo=timezone.utc))
  self.assertEqual(rows,[])
 def test_import_cli_is_one_shot_and_never_claims_live(self):
  import tempfile,pathlib,json,subprocess,sys
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'result.json';p.write_text(json.dumps(payload()))
   args=[sys.executable,'-m','pa_lens.feed',str(p),'--feed','iex','--captured-at','2026-11-17T14:32:00Z','--db',str(pathlib.Path(d)/'db')]
   first=subprocess.run(args,capture_output=True,text=True)
   self.assertEqual(first.returncode,0,first.stderr)
   j=json.loads(first.stdout);self.assertEqual(j['inserted'],1);self.assertFalse(j['health']['live_verified'])
   again=json.loads(subprocess.run(args,capture_output=True,text=True,check=True).stdout)
   self.assertEqual(again['duplicates'],1)

class ConnectorContinuityTests(unittest.TestCase):
 def test_feed_switch_is_separate_stream_and_missing_minute_resets(self):
  from pa_lens.service import Journal
  from dataclasses import asdict
  import copy
  p=payload();second=copy.deepcopy(p['bars']['SOXL'][0]);second['timestamp']='2026-11-17T14:32:00Z';p['bars']['SOXL'].append(second)
  journal=Journal(':memory:')
  try:
   for bar in connector_bars(p,'SOXL','iex',datetime(2026,11,17,14,35,tzinfo=timezone.utc)):journal.ingest(asdict(bar))
   iex=journal.streams[('SOXL','1','alpaca-connector:iex:adjustment_unverified')]
   self.assertEqual(iex['engine'].gap_count,1)
   self.assertTrue(any(e['family']=='data_gap' for e in iex['events']))
   p['request']['feed']='sip'
   for bar in connector_bars(p,'SOXL','sip',datetime(2026,11,17,14,35,tzinfo=timezone.utc)):journal.ingest(asdict(bar))
   self.assertEqual(len(journal.streams),2)
   self.assertEqual(iex['bar_count'],2)
  finally:journal.close()
