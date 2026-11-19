import json
from contextlib import closing
import tempfile
import shutil
import subprocess
import threading
import sqlite3
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pa_lens.service import Journal, make_server
from pa_lens.core import Config


def sample(minute=1, source='test'):
    return dict(symbol='SOXL', timeframe='1', time=f'2026-11-17T14:{minute:02d}:00Z', open=10.0,
                high=11.0, low=9.0, close=10.5, volume=100, source=source)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'bars.sqlite'
        self.journal = Journal(self.path)

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def test_duplicate_is_idempotent_and_restart_rebuilds(self):
        a = self.journal.ingest(sample())
        self.assertFalse(a['duplicate'])
        self.assertTrue(self.journal.ingest(sample())['duplicate'])
        before = self.journal.snapshot()['streams'][0]
        self.assertEqual(before['bar_count'], 1)
        self.journal.close()
        self.journal = Journal(self.path)
        after = self.journal.snapshot()['streams'][0]
        self.assertEqual(before['state'], after['state'])
        self.assertEqual(after['bar_count'], 1)

    def test_restart_with_changed_rules_is_rejected(self):
        self.journal.ingest(sample())
        self.journal.close()
        with self.assertRaises(ValueError):
            Journal(self.path, Config(pivot_left=3))
        # A failed constructor must release its file lock.
        self.journal = Journal(self.path)

    def test_code_and_version_metadata_match_on_restart(self):
        self.journal.ingest(sample())
        for key in ('engine_version', 'core_sha256'):
            rows = dict(self.journal.conn.execute('SELECT key,value FROM metadata'))
            self.assertIn(key, rows)
            original = rows[key]
            self.journal.conn.execute('UPDATE metadata SET value=? WHERE key=?', ('changed', key))
            self.journal.conn.commit()
            self.journal.close()
            with self.assertRaisesRegex(ValueError, 'new database'):
                Journal(self.path)
            with closing(sqlite3.connect(str(self.path))) as conn:
                with conn:
                    conn.execute('UPDATE metadata SET value=? WHERE key=?', (original, key))
            self.journal = Journal(self.path)

    def test_legacy_journal_without_code_identity_fails_closed(self):
        self.journal.ingest(sample())
        self.journal.conn.execute("DELETE FROM metadata WHERE key != 'config_hash'")
        self.journal.conn.commit()
        self.journal.close()
        with self.assertRaisesRegex(ValueError, 'new database'):
            Journal(self.path)

    def test_second_instance_cannot_diverge_and_close_allows_reopen(self):
        self.journal.ingest(sample())
        with self.assertRaisesRegex(RuntimeError, 'already in use'):
            Journal(self.path)
        self.journal.close()
        self.journal = Journal(self.path)
        self.journal.ingest(sample(2))
        self.assertEqual(self.journal.snapshot()['streams'][0]['bar_count'], 2)

    def test_another_process_cannot_open_active_journal(self):
        code = "from pa_lens.service import Journal; import sys; Journal(sys.argv[1])"
        result = subprocess.run([sys.executable, '-c', code, str(self.path)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already in use', result.stderr)

    def test_memory_journals_are_independent_and_close_idempotent(self):
        a, b = Journal(':memory:'), Journal(':memory:')
        try:
            a.ingest(sample())
            self.assertEqual(b.snapshot()['streams'], [])
        finally:
            a.close()
            a.close()
            b.close()

    def test_snapshot_readiness_separates_warmup_stale_and_ready(self):
        self.assertFalse(self.journal.snapshot()['ready'])
        self.assertEqual(self.journal.snapshot()['readiness'], 'WAITING_FOR_DATA')
        self.journal.ingest(sample())
        now = datetime(2026,11,17,14,1,tzinfo=timezone.utc)
        self.assertEqual(self.journal.snapshot(now)['streams'][0]['readiness'], 'WARMUP')
        for minute in range(2, 7):
            self.journal.ingest(sample(minute))
        ready = self.journal.snapshot(datetime(2026,11,17,14,6,tzinfo=timezone.utc))
        self.assertTrue(ready['ready'])
        self.assertEqual(ready['readiness'], 'READY_FOR_RESEARCH')
        self.assertFalse(self.journal.snapshot(datetime(2026,11,18,14,6,tzinfo=timezone.utc))['ready'])
        self.assertFalse(ready['live_verified'])

    def test_revision_and_out_of_order_do_not_corrupt_journal(self):
        self.journal.ingest(sample(2))
        changed = sample(2)
        changed['close'] = 10.7
        with self.assertRaises(ValueError):
            self.journal.ingest(changed)
        with self.assertRaises(ValueError):
            self.journal.ingest(sample(1))
        self.assertEqual(self.journal.snapshot()['streams'][0]['bar_count'], 1)

    def test_invalid_or_nonfinal_bar_rejected(self):
        for key, value in [('high', 8), ('close', float('nan')), ('bar_closed', False), ('final', False)]:
            bar = sample()
            bar[key] = value
            with self.assertRaises(ValueError):
                self.journal.ingest(bar)
        self.assertEqual(self.journal.snapshot()['streams'], [])

    def test_future_bar_rejected_without_state_mutation(self):
        bar = sample()
        bar['time'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):
            self.journal.ingest(bar)
        self.assertEqual(self.journal.snapshot()['streams'], [])

    def test_streams_are_separate(self):
        self.journal.ingest(sample(source='one'))
        self.journal.ingest(sample(source='two'))
        self.assertEqual(len(self.journal.snapshot()['streams']), 2)

    def test_stream_limit_rejects_new_symbols_but_accepts_existing(self):
        for i in range(64):
            self.journal.ingest(sample(source=f'feed-{i}'))
        with self.assertRaisesRegex(ValueError, 'stream limit'):
            self.journal.ingest(sample(source='feed-65'))
        self.assertTrue(self.journal.ingest(sample(source='feed-0'))['duplicate'])

    def test_webhook_maps_candle_and_close_time(self):
        bar = sample()
        packet = dict(schema='ai-agent-lens/v1', symbol='SOXL', timeframe='1', time=bar['time'],
                      candle={k: bar[k] for k in ('open','high','low','close','volume')})
        self.journal.ingest(packet, webhook=True)
        row = self.journal.snapshot()['streams'][0]
        self.assertEqual(row['bars'][0]['time'], bar['time'])
        self.assertEqual(row['source'], 'tradingview')
        with self.assertRaises(ValueError):
            self.journal.ingest(dict(packet, schema='other'), webhook=True)

    def test_stale_is_visible_without_calling_service_live(self):
        self.journal.ingest(sample())
        health = self.journal.health(datetime(2026,11,18,14,0,tzinfo=timezone.utc))
        self.assertEqual(health['status'], 'STALE')
        self.assertGreater(health['streams'][0]['age_seconds'], 3600)
        self.assertFalse(health['live_verified'])

    def test_daily_snapshot_uses_calendar_freshness_and_retains_300_bars(self):
        from pa_lens.timeframes import daily_close
        for d in ('2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13'):
            self.journal.ingest(dict(symbol='SOXL', timeframe='D', time=daily_close(d).isoformat(),
                                     open=10.0, high=11.0, low=9.0, close=10.5, volume=100, source='test'))
        sunday = self.journal.snapshot(datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc))
        self.assertEqual(sunday['streams'][0]['freshness'], 'RECENT')
        self.assertTrue(sunday['ready'])
        monday_late = self.journal.snapshot(datetime(2026, 11, 16, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(monday_late['streams'][0]['freshness'], 'STALE')
        self.assertFalse(monday_late['ready'])
        self.assertEqual(self.journal.streams[('SOXL', 'D', 'test')]['bars'].maxlen, 300)
        self.assertEqual(self.journal.streams[('SOXL', 'D', 'test')]['events'].maxlen, 500)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.tmp.name) / 'bars.sqlite')
        self.server = make_server(self.journal, 'unit-test-secret', port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.journal.close()
        self.tmp.cleanup()

    def req(self, path, data=None, token='unit-test-secret'):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=data, headers=headers)
        try:
            with urlopen(request, timeout=3) as resp:
                return resp.status, resp.read(), resp.headers
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_auth_required_for_data_and_write(self):
        self.assertEqual(self.req('/health', token='')[0], 401)
        self.assertEqual(self.req('/snapshot', token='bad')[0], 401)
        self.assertEqual(self.req('/bar', json.dumps(sample()).encode(), token='bad')[0], 401)
        self.assertEqual(self.req('/bar', json.dumps(sample()).encode())[0], 200)
        self.assertEqual(self.req('/snapshot')[0], 200)
        self.assertEqual(self.req('/health?token=unit-test-secret', token='')[0], 401)

    def test_malformed_and_large_body_are_rejected(self):
        self.assertEqual(self.req('/bar', b'{')[0], 400)
        self.assertEqual(self.req('/bar', b'x' * (65536 + 1))[0], 413)
        self.assertEqual(self.req('/bar', b'[]')[0], 400)
        self.assertEqual(self.req('/bar', b'{"close":NaN}')[0], 400)

    def test_dashboard_safe_shell_has_no_private_data_or_html_injection_sink(self):
        code, body, headers = self.req('/', token='')
        self.assertEqual(code, 200)
        self.assertNotIn(b'unit-test-secret', body)
        self.assertNotIn(b'innerHTML', body)
        self.assertIn(b'textContent', body)
        self.assertIn('Content-Security-Policy', headers)

    def test_tv_route_disabled_by_default(self):
        if type(self) is HttpTests:
            self.assertEqual(self.req('/tradingview?token=unit-test-secret', b'{}', token='')[0], 404)

    def test_empty_token_fails_closed(self):
        with self.assertRaises(ValueError):
            make_server(self.journal, '')


class TradingViewHttpTests(HttpTests):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Journal(Path(self.tmp.name) / 'bars.sqlite')
        self.server = make_server(self.journal, 'unit-test-secret', port=0, tv_token='separate-tv-secret')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def packet(self):
        bar = sample()
        return json.dumps(dict(schema='ai-agent-lens/v1', symbol='SOXL', timeframe='1', time=bar['time'],
                       candle={k: bar[k] for k in ('open','high','low','close','volume')})).encode()

    def test_tv_token_scope_and_duplicate(self):
        body = self.packet()
        self.assertEqual(self.req('/tradingview?token=wrong', body, token='')[0], 401)
        self.assertEqual(self.req('/tradingview?token=unit-test-secret', body, token='')[0], 401)
        self.assertEqual(self.req('/tradingview', body)[0], 401)
        self.assertEqual(self.req('/bar?token=separate-tv-secret', json.dumps(sample()).encode(), token='')[0], 401)
        self.assertEqual(self.req('/tradingview?token=separate-tv-secret&token=wrong', body, token='')[0], 401)
        code, first, _ = self.req('/tradingview?token=separate-tv-secret', body, token='')
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(first)['duplicate'])
        self.assertTrue(json.loads(self.req('/tradingview?token=separate-tv-secret', body, token='')[1])['duplicate'])
        self.assertEqual(self.req('/tradingview?token=separate-tv-secret', b'x' * 65537, token='')[0], 413)
        self.assertNotIn(b'separate-tv-secret', self.req('/snapshot')[1])

    def test_tv_future_rejected(self):
        packet = json.loads(self.packet())
        packet['time'] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.assertEqual(self.req('/tradingview?token=separate-tv-secret', json.dumps(packet).encode(), token='')[0], 400)

    def test_tv_must_have_a_distinct_nonempty_token(self):
        for value in ('', 'unit-test-secret', 'bad\ntoken'):
            with self.assertRaises(ValueError):
                make_server(self.journal, 'unit-test-secret', tv_token=value)


class DashboardDomTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required for isolated DOM behavior test')
    def test_context_is_bounded_and_event_levels_are_rendered(self):
        html = Path(__file__).resolve().parents[1] / 'pa_lens' / 'dashboard.html'
        script = html.read_text().split('<script>')[1].split('</script>')[0]
        harness = r"""
const vm = require('vm');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.textContent='';this.value='0';this.checked=false;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 setAttribute(){}
 addEventListener(){}
}
const elements={};
const document={getElementById(id){return elements[id]||(elements[id]=new Element());},createElement(tag){return new Element(tag)},createElementNS(ns,tag){return new Element(tag)}};
const ctx={document,setInterval(){}};vm.createContext(ctx);
vm.runInContext(SCRIPT,ctx);
vm.runInContext(`snapshot={streams:[{symbol:'SOXL',timeframe:'1',source:'test',bar_count:1,bars:[],events:[{family:'double_bottom',status:'armed',direction:'long',observed_at:'now',explanation:'text',trigger:11,stop:9,target:13,anchors:{neckline:10}}],state:{context:'range',bars_in_segment:10,gap_count:0,config_hash:'abc',mode:'research_only',coverage:'partial',recent_bars:[{private_large_marker:'SHOULD_NOT_RENDER'}],events:[{secret_marker:'SHOULD_NOT_RENDER'}]}}]};render();`,ctx);
function allText(el){return el.textContent+el.children.map(allText).join('\n')}
console.log(JSON.stringify({context:elements.context.textContent,events:allText(elements.events)}));
"""
        result = subprocess.run(['node', '-e', harness.replace('SCRIPT', json.dumps(script))], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertNotIn('SHOULD_NOT_RENDER', data['context'])
        self.assertIn('range', data['context'])
        for value in ('trigger', '11', 'stop', '9', 'target', '13', 'anchors', 'neckline'):
            self.assertIn(value, data['events'])


if __name__ == '__main__':
    unittest.main()

class DisplayProjectionTests(unittest.TestCase):
    def test_display_is_separate_and_restores_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'display.sqlite'
            j=Journal(path)
            j.ingest(sample())
            before=j.snapshot()['streams'][0]
            self.assertIn('display',before)
            self.assertEqual(before['display']['stats']['raw_events'],len(before['events']))
            j.close();j=Journal(path)
            self.assertEqual(before['display'],j.snapshot()['streams'][0]['display'])
            j.close()
    def test_display_config_mismatch_requires_new_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'display.sqlite'
            j=Journal(path,display_config={'min_priority':2,'cooldown_minutes':15});j.close()
            with self.assertRaisesRegex(ValueError,'new database'):
                Journal(path,display_config={'min_priority':1,'cooldown_minutes':0})
