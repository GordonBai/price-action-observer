import unittest
from datetime import datetime,timezone
from pa_lens.feed import AlpacaFeed,FeedError,normalize_alpaca,Poller

class FeedTests(unittest.TestCase):
    def test_close_time_and_not_final(self):
        row={'t':'2026-11-17T14:30:00Z','o':10,'h':11,'l':9,'c':10,'v':100}
        self.assertIsNone(normalize_alpaca('SOXL',row,'sip',datetime(2026,11,17,14,30,59,tzinfo=timezone.utc)))
        b=normalize_alpaca('SOXL',row,'sip',datetime(2026,11,17,14,31,3,tzinfo=timezone.utc))
        self.assertEqual(b.time,'2026-11-17T14:31:00+00:00')
        self.assertEqual(b.source,'alpaca:sip:raw')
    def test_rth_filter_dst(self):
        row={'t':'2026-11-17T13:30:00Z','o':10,'h':11,'l':9,'c':10,'v':100}
        self.assertIsNone(normalize_alpaca('SOXL',row,'sip',datetime(2026,11,17,14,32,tzinfo=timezone.utc)))
    def test_auth_not_logged_on_provider_failure(self):
        def bad(url,headers):raise OSError('do not expose headers'+str(headers))
        f=AlpacaFeed('test-secret-id','test-secret-value',transport=bad)
        with self.assertRaises(FeedError) as ctx:list(f.fetch('SOXL','2026-11-17T14:30:00Z','2026-11-17T14:32:00Z'))
        self.assertNotIn('test-secret',str(ctx.exception))
    def test_pagination_and_explicit_raw_feed(self):
        seen=[]
        def transport(url,headers):
            seen.append(url)
            return {'bars':{'SOXL':[{'t':'2026-11-17T14:30:00Z','o':10,'h':11,'l':9,'c':10,'v':1}]},'next_page_token':'next'} if len(seen)==1 else {'bars':{'SOXL':[]},'next_page_token':None}
        f=AlpacaFeed('id','secret',transport=transport)
        rows=list(f.fetch('SOXL','2026-11-17T14:30:00Z','2026-11-17T14:32:00Z'))
        self.assertEqual(len(rows),1);self.assertEqual(len(seen),2)
        self.assertIn('adjustment=raw',seen[0]);self.assertIn('feed=sip',seen[0]);self.assertIn('page_token=next',seen[1])
    def test_missing_credentials_and_feed_rejected(self):
        with self.assertRaises(ValueError):AlpacaFeed('','')
        with self.assertRaises(ValueError):AlpacaFeed('x','y',feed='auto')
    def test_poller_real_journal_deduplicates(self):
        from pa_lens.service import Journal
        import tempfile
        class Fake:
            feed='sip'
            def fetch(self,*args):return iter([{'t':'2026-11-17T14:30:00Z','o':10,'h':11,'l':9,'c':10,'v':1}])
        with tempfile.TemporaryDirectory() as d:
            j=Journal(d+'/db');p=Poller(Fake(),j,'SOXL')
            now=datetime(2026,11,17,14,32,tzinfo=timezone.utc)
            self.assertEqual(p.poll(now)['inserted'],1)
            self.assertEqual(p.poll(now)['duplicates'],1)
            self.assertEqual(j.snapshot()['streams'][0]['bar_count'],1)
            j.close()

class RedirectSecurityTests(unittest.TestCase):
    def test_provider_redirect_never_forwards_secret_headers(self):
        from pa_lens.feed import _transport
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from urllib.error import HTTPError
        import threading
        leaked=[]
        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                leaked.append(self.headers.get('APCA-API-SECRET-KEY'))
                self.send_response(200);self.end_headers();self.wfile.write(b'{}')
            def log_message(self,*args):pass
        target=ThreadingHTTPServer(('127.0.0.1',0),Target)
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302);self.send_header('Location',f'http://127.0.0.1:{target.server_port}/');self.end_headers()
            def log_message(self,*args):pass
        origin=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        for server in (target,origin):threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with self.assertRaises(HTTPError):_transport(f'http://127.0.0.1:{origin.server_port}/',{'APCA-API-SECRET-KEY':'synthetic-test-secret'})
            self.assertEqual(leaked,[])
        finally:
            for server in (origin,target):server.shutdown();server.server_close()
