import io
import tempfile
import unittest
from pathlib import Path

class TTY(io.StringIO):
    def isatty(self):return True

class WizardTests(unittest.TestCase):
    def inputs(self,infra,db,*,confirm='yes',quality='strict'):
        return TTY('\n'.join(['NVDA, SOXL','5m','regular','fixed','30','2',quality,'120',str(infra),str(db),confirm])+'\n')
    def infra(self,tmp):
        path=Path(tmp)/'infra';(path/'src/trading_execution').mkdir(parents=True)
        (path/'src/trading_execution/transport.py').touch();return path
    def test_confirmed_launch_uses_structured_arguments_only(self):
        from pa_lens.wizard import run_wizard
        with tempfile.TemporaryDirectory() as tmp:
            infra=self.infra(tmp);calls=[];out=TTY()
            self.assertTrue(run_wizard(calls.append,input_stream=self.inputs(infra,Path(tmp)/'new.db'),output_stream=out))
            argv=calls[0]
            self.assertEqual(argv[0],'poll-robinhood');self.assertIn('NVDA',argv);self.assertIn('SOXL',argv)
            self.assertEqual(argv[argv.index('--output')+1],'tui');self.assertNotIn('--accept-unknown',argv)
            self.assertEqual(argv[argv.index('--count')+1],'2')
    def test_cancel_and_eof_never_launch(self):
        from pa_lens.wizard import run_wizard
        with tempfile.TemporaryDirectory() as tmp:
            infra=self.infra(tmp)
            for stream in (self.inputs(infra,Path(tmp)/'new.db',confirm='no'),TTY('')):
                calls=[];self.assertFalse(run_wizard(calls.append,input_stream=stream,output_stream=TTY()));self.assertEqual(calls,[])
    def test_non_tty_fails_without_reading(self):
        from pa_lens.wizard import run_wizard
        class Pipe(io.StringIO):
            def readline(self,*args):raise AssertionError('must not prompt on pipe')
        with self.assertRaisesRegex(ValueError,'TTY'):run_wizard(lambda _:None,input_stream=Pipe(),output_stream=TTY())
    def test_exploration_requires_explicit_selection(self):
        from pa_lens.wizard import run_wizard
        with tempfile.TemporaryDirectory() as tmp:
            infra=self.infra(tmp);calls=[]
            run_wizard(calls.append,input_stream=self.inputs(infra,Path(tmp)/'new.db',quality='explore'),output_stream=TTY())
            self.assertIn('--accept-unknown',calls[0])
    def test_daily_and_derived15_force_regular_close_mode_infinite(self):
        from pa_lens.wizard import run_wizard
        with tempfile.TemporaryDirectory() as tmp:
            infra=self.infra(tmp)
            for period in ('15m','1d'):
                data=['NVDA',period,'close','10','infinite','y']+(['120'] if period=='15m' else [])+[str(infra),str(Path(tmp)/(period+'.db')),'yes']
                calls=[];run_wizard(calls.append,input_stream=TTY('\n'.join(data)+'\n'),output_stream=TTY())
                args=calls[0];self.assertEqual(args[args.index('--bounds')+1],'regular');self.assertIn('--align-close',args);self.assertNotIn('--count',args)
                self.assertIn('--accept-unknown',args)
    def test_invalid_inputs_reprompt_and_existing_db_not_overwritten(self):
        from pa_lens.wizard import run_wizard
        with tempfile.TemporaryDirectory() as tmp:
            infra=self.infra(tmp);old=Path(tmp)/'old.db';old.write_text('untouched')
            data=['NVDA;echo x','NVDA','2m','1m','bogus','extended','fixed','0','60','10001','1','n','0','120','/missing/path',str(infra),str(old),str(Path(tmp)/'new.db'),'yes']
            calls=[];out=TTY();run_wizard(calls.append,input_stream=TTY('\n'.join(data)+'\n'),output_stream=out)
            self.assertEqual(len(calls),1);self.assertEqual(old.read_text(),'untouched');self.assertIn('输入无效',out.getvalue())
    def test_ctrl_c_during_prompt_never_launches(self):
        from pa_lens.wizard import run_wizard
        class Interrupt(TTY):
            def readline(self,*args):raise KeyboardInterrupt()
        calls=[];self.assertFalse(run_wizard(calls.append,input_stream=Interrupt(),output_stream=TTY()));self.assertEqual(calls,[])
    def test_cli_pipe_rejected_promptly(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-m','pa_lens','wizard'],input='NVDA\n',capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('TTY',result.stderr)
