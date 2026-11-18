import json, subprocess,sys,tempfile,unittest
from pathlib import Path
class CLITests(unittest.TestCase):
    def test_mm(self):
        r=subprocess.run([sys.executable,'-m','pa_lens','mm','--a','100','--b','110','--c','105'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['target'],115)
    def test_help(self):
        r=subprocess.run([sys.executable,'-m','pa_lens','--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('replay',r.stdout)
    def test_serve_without_token_rejected(self):
        import os
        env=dict(os.environ);env.pop('PA_LENS_TOKEN',None)
        r=subprocess.run([sys.executable,'-m','pa_lens','serve'],capture_output=True,text=True,env=env,timeout=5)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('PA_LENS_TOKEN',r.stderr)

    def test_replay_open_time_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.csv'
            path.write_text('symbol,timestamp,open,high,low,close,volume,source,feed,adjustment\nSOXL,2026-11-17T14:30:00Z,10,11,9,10,100,alpaca,sip,unverified\n')
            out=Path(tmp)/'output'
            r=subprocess.run([sys.executable,'-m','pa_lens','replay',str(path),'--open-time-minutes','1','--out',str(out)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            result=json.loads((out/'result.json').read_text())
            self.assertEqual(result['summary']['first_bar'],'2026-11-17T14:31:00+00:00')
            self.assertNotIn('evaluation',result)
    def test_evaluate_command_outputs_chronological_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=subprocess.run([sys.executable,'-m','pa_lens','evaluate','examples/pa/synthetic_double_bottom.jsonl','--out',tmp],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            result=json.loads((Path(tmp)/'evaluation.json').read_text())
            self.assertEqual(result['splits']['development']['status'],'no_data')
            self.assertEqual(result['splits']['known_case_2026_11_17']['bars'],14)
    def test_poll_fails_clearly_without_credentials(self):
        import os
        env=dict(os.environ);env.pop('APCA_API_KEY_ID',None);env.pop('APCA_API_SECRET_KEY',None)
        r=subprocess.run([sys.executable,'-m','pa_lens','poll-alpaca','--once'],capture_output=True,text=True,env=env)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('APCA_API_KEY_ID',r.stderr)
    def test_tv_ingress_explicit_opt_in_requires_separate_secret(self):
        import os
        env=dict(os.environ);env['PA_LENS_TOKEN']='test-only-main-secret-123';env.pop('PA_LENS_TV_TOKEN',None)
        r=subprocess.run([sys.executable,'-m','pa_lens','serve','--enable-tradingview'],capture_output=True,text=True,env=env,timeout=5)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('PA_LENS_TV_TOKEN',r.stderr)
