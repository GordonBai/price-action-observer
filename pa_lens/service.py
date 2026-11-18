"""Local research dashboard and authenticated closed-bar ingress.

The listener is not a market feed. A recent submitted bar is not proof of an
independently verified live feed. No brokerage or order API is implemented.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import sqlite3
import threading
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .core import Bar, Engine, ENGINE_VERSION
from .presentation import PresentationProjector

MAX_BODY = 65536
MAX_STREAMS = 64
# Pin the engine sources loaded by this process, not unrelated documentation commits.
_code_hash = hashlib.sha256()
for _name in ('core.py', 'advanced.py', 'observations.py', 'explanations.py', 'presentation.py'):
    _path = Path(__file__).with_name(_name)
    if _path.exists():
        _code_hash.update(_name.encode() + b'\0' + _path.read_bytes())
CORE_SHA256 = _code_hash.hexdigest()


def _strict_loads(raw):
    def reject(value):
        raise ValueError('nonfinite JSON value')
    return json.loads(raw, parse_constant=reject)


def _iso(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    return value


def _datetime(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp must have a timezone')
    return dt.astimezone(timezone.utc)


def normalize(payload, webhook=False):
    if not isinstance(payload, dict):
        raise ValueError('expected a JSON object')
    if payload.get('bar_closed', True) is not True or payload.get('final', True) is not True:
        raise ValueError('only final closed bars are accepted')
    if webhook:
        if payload.get('schema') != 'ai-agent-lens/v1':
            raise ValueError('expected ai-agent-lens/v1 schema')
        candle = payload.get('candle')
        if not isinstance(candle, dict):
            raise ValueError('missing candle')
        data = {key: candle.get(key) for key in ('open','high','low','close','volume')}
        data.update({key: payload.get(key) for key in ('symbol','timeframe','time')})
        data['source'] = 'tradingview'
    else:
        data = {key: payload[key] for key in ('symbol','timeframe','time','open','high','low','close') if key in payload}
        data.update(volume=payload.get('volume', 0), source=payload.get('source', 'manual'))
    for key in ('symbol', 'timeframe', 'source'):
        value = data.get(key)
        if not isinstance(value, str) or not value or len(value) > 128 or any(ord(c) < 32 for c in value):
            raise ValueError(f'invalid {key}')
    try:
        return Bar.from_dict(data)
    except (TypeError, KeyError, OverflowError) as exc:
        raise ValueError('invalid bar fields') from exc


class Journal:
    """One transactional SQLite journal; stream engines are rebuilt on restart.

    Corrections are rejected rather than silently rewriting the historical
    signal tape. Import revised data into a separate research database.
    """
    def __init__(self, db_path, config=None, display_config=None):
        self.config = config
        self.display_config=PresentationProjector(**({'min_priority':3,**(display_config or {})})).snapshot()['config']
        self.lock = threading.RLock()
        self.conn = None
        self._file_lock = None
        try:
            if str(db_path) != ':memory:':
                # Lock the database inode itself, including symlink/hardlink aliases.
                # flock is independent of SQLite's byte-range transaction locks.
                db_path = Path(db_path).expanduser().resolve()
                self._file_lock = open(db_path, 'a+b')
                try:
                    fcntl.flock(self._file_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise RuntimeError('journal already in use by another instance or process') from exc
            self._initialize(db_path, config)
        except BaseException:
            self.close()
            raise

    def _initialize(self, db_path, config):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS bars (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, source TEXT NOT NULL,
            time TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL,
            UNIQUE(symbol,timeframe,source,time))''')
        self.conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        identity = {'config_hash': Engine(config).config_hash,
                    'engine_version': ENGINE_VERSION, 'core_sha256': CORE_SHA256,
                    'knowledge_sha256': Engine(config).snapshot()['knowledge_version'],
                    'display_config':json.dumps(self.display_config,sort_keys=True)}
        saved = dict(self.conn.execute('SELECT key,value FROM metadata'))
        if saved and any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError('journal rule/config/code identity differs or is missing; use a new database')
        if not saved and self.conn.execute('SELECT COUNT(*) FROM bars').fetchone()[0]:
            raise ValueError('legacy journal has no code identity; use a new database')
        self.conn.executemany('INSERT OR IGNORE INTO metadata(key,value) VALUES(?,?)', identity.items())
        self.identity = identity
        self.conn.commit()
        self.streams = {}
        self._rebuild()

    def _new(self):
        return {'engine': Engine(self.config), 'bars': deque(maxlen=240),
                'display':PresentationProjector(**self.display_config), 'events': deque(maxlen=200), 'bar_count': 0, 'received_at': None}

    def _apply(self, data, received_at):
        key = (data['symbol'], data['timeframe'], data['source'])
        stream = self.streams.setdefault(key, self._new())
        events = stream['engine'].update(Bar.from_dict(data))
        stream['bars'].append(data)
        stream['events'].extend(events)
        stream['display'].update(events)
        stream['bar_count'] += 1
        stream['received_at'] = received_at
        return events

    def _rebuild(self):
        self.streams = {}
        for text, received_at in self.conn.execute('SELECT payload,received_at FROM bars ORDER BY seq'):
            self._apply(json.loads(text), received_at)

    def ingest(self, payload, webhook=False):
        bar = normalize(payload, webhook)
        data = {key: _iso(getattr(bar, key)) for key in
                ('symbol','timeframe','time','open','high','low','close','volume','source')}
        # Normalize identity timestamps even if core preserves an equivalent offset.
        data['time'] = _iso(_datetime(data['time']))
        encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
        key = (data['symbol'], data['timeframe'], data['source'])
        now_dt = datetime.now(timezone.utc)
        if (_datetime(data['time']) - now_dt).total_seconds() > 5:
            raise ValueError('future close time rejected; submit only completed bars')
        now = _iso(now_dt)
        with self.lock:
            if key not in self.streams and len(self.streams) >= MAX_STREAMS:
                raise ValueError('stream limit reached (64); use a separate journal')
            existing = self.conn.execute('SELECT payload FROM bars WHERE symbol=? AND timeframe=? AND source=? AND time=?',
                                         (*key, data['time'])).fetchone()
            if existing:
                if json.loads(existing[0]) != data:
                    raise ValueError('bar revision rejected; use separate corrected-history database')
                return {'ok': True, 'duplicate': True, 'events': []}
            last = self.conn.execute('SELECT time FROM bars WHERE symbol=? AND timeframe=? AND source=? ORDER BY seq DESC LIMIT 1', key).fetchone()
            if last and _datetime(data['time']) <= _datetime(last[0]):
                raise ValueError('out-of-order bar rejected')
            try:
                events = self._apply(data, now)
                self.conn.execute('INSERT INTO bars(symbol,timeframe,source,time,payload,received_at) VALUES(?,?,?,?,?,?)',
                                  (*key, data['time'], encoded, now))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                self._rebuild()
                raise
            return {'ok': True, 'duplicate': False, 'events': events}

    def snapshot(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            result = []
            for (symbol, timeframe, source), stream in self.streams.items():
                last = stream['bars'][-1]
                age = (now - _datetime(last['time'])).total_seconds()
                seconds = int(timeframe) * 60 if timeframe.isdigit() else 86400
                state = stream['engine'].snapshot()
                freshness = 'FUTURE' if age < -5 else ('STALE' if age > max(120, seconds*2) else 'RECENT')
                warm = state.get('bars_in_segment', 0) >= stream['engine'].config.min_history
                readiness = freshness if freshness != 'RECENT' else ('READY_FOR_RESEARCH' if warm else 'WARMUP')
                result.append(dict(symbol=symbol, timeframe=timeframe, source=source,
                    bar_count=stream['bar_count'], bars=list(stream['bars']), events=list(stream['events']),
                    display=stream['display'].snapshot(), state=state, last_bar_close=last['time'], received_at=stream['received_at'],
                    age_seconds=round(age, 2), freshness=freshness, readiness=readiness, ready=readiness == 'READY_FOR_RESEARCH'))
            ready = bool(result) and all(s['ready'] for s in result)
            readiness = 'WAITING_FOR_DATA' if not result else ('READY_FOR_RESEARCH' if ready else 'NOT_READY')
            return {'mode': 'research_only', 'live_verified': False, 'ready': ready, 'readiness': readiness,
                    'rule_identity': dict(self.identity), 'streams': result,
                    'notice': '接收器不是行情供应商；RECENT仅表示提交的时间戳接近当前，不代表已验证实时报价。收市时历史bar会显示STALE。'}

    def health(self, now=None):
        result = self.snapshot(now)
        streams = [{key: stream[key] for key in ('symbol','timeframe','source','bar_count','last_bar_close','received_at','age_seconds','freshness','readiness','ready')} for stream in result['streams']]
        status = 'WAITING_FOR_DATA' if not streams else ('RECENT_INPUT' if all(s['freshness']=='RECENT' for s in streams) else 'STALE')
        return {'status': status, 'live_verified': False, 'ready': result['ready'], 'readiness': result['readiness'], 'rule_identity': result['rule_identity'], 'streams': streams, 'notice': result['notice']}

    def close(self):
        with self.lock:
            try:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
            finally:
                if self._file_lock is not None:
                    # Never unlink a sidecar lock while another process might use it;
                    # this lock lives on the database inode and closes with the fd.
                    self._file_lock.close()
                    self._file_lock = None


def make_server(journal, token, host='127.0.0.1', port=8080, tv_token=None):
    if not isinstance(token, str) or not token.strip():
        raise ValueError('set PA_LENS_TOKEN before starting authenticated ingress')
    if '\n' in token or '\r' in token:
        raise ValueError('invalid token')

    if tv_token is not None:
        if not isinstance(tv_token, str) or not tv_token.strip() or any(c in tv_token for c in ('\n','\r')):
            raise ValueError('TradingView token must be nonempty and single-line')
        if hmac.compare_digest(tv_token.encode(), token.encode()):
            raise ValueError('TradingView token must differ from the data API token')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'PriceActionLens/0.1'
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def _reply(self, status, value, content_type='application/json; charset=utf-8'):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _auth(self):
            expected = ('Bearer ' + token).encode()
            supplied = self.headers.get('Authorization', '').encode()
            if not hmac.compare_digest(expected, supplied):
                self._reply(401, {'ok': False, 'error': 'bearer token required'})
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                return self._reply(200, Path(__file__).with_name('dashboard.html').read_bytes(), 'text/html; charset=utf-8')
            if not self._auth():
                return
            if path == '/health':
                return self._reply(200, journal.health())
            if path == '/snapshot':
                return self._reply(200, journal.snapshot())
            self._reply(404, {'ok': False, 'error': 'not found'})

        def do_POST(self):
            url = urlsplit(self.path)
            path = url.path
            if path == '/tradingview':
                if tv_token is None:
                    return self._reply(404, {'ok': False, 'error': 'route disabled'})
                values = parse_qs(url.query, keep_blank_values=True).get('token', [])
                if len(values) != 1 or not hmac.compare_digest(values[0].encode(), tv_token.encode()):
                    return self._reply(401, {'ok': False, 'error': 'TradingView token required'})
            elif not self._auth():
                return
            if path not in ('/bar', '/webhook', '/tradingview'):
                return self._reply(404, {'ok': False, 'error': 'not found'})
            if self.headers.get('Transfer-Encoding'):
                return self._reply(400, {'ok': False, 'error': 'transfer encoding not supported'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self._reply(400, {'ok': False, 'error': 'invalid content length'})
            if length > MAX_BODY:
                return self._reply(413, {'ok': False, 'error': 'body too large'})
            if length <= 0:
                return self._reply(400, {'ok': False, 'error': 'empty body'})
            if self.headers.get_content_type() != 'application/json':
                return self._reply(415, {'ok': False, 'error': 'application/json required'})
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('incomplete body')
                result = journal.ingest(_strict_loads(raw), webhook=path in ('/webhook', '/tradingview'))
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                return self._reply(400, {'ok': False, 'error': str(exc)})
            except sqlite3.Error:
                return self._reply(503, {'ok': False, 'error': 'journal unavailable'})
            return self._reply(200, result)

        def log_message(self, *args):
            pass  # Do not log authorization or arbitrary query strings.

    return ThreadingHTTPServer((host, port), Handler)
