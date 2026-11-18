"""Local research dashboard and authenticated closed-bar ingress.

The listener is not a market feed. A recent submitted bar is not proof of an
independently verified live feed. No brokerage or order API is implemented.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from importlib.metadata import version
import sqlite3
import threading
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .core import Bar, Engine, ENGINE_VERSION
from .presentation import PresentationProjector
from .journal_lock import JournalLock

MAX_BODY = 65536
MAX_STREAMS = 64
# Pin the engine sources loaded by this process, not unrelated documentation commits.
_code_hash = hashlib.sha256()
for _name in ('core.py', 'advanced.py', 'observations.py', 'structures.py', 'explanations.py', 'presentation.py', 'service.py', 'feed.py', 'journal_lock.py', 'analytics.py', 'timeframes.py', 'robinhood.py', 'rh_runtime.py', 'provider_indicators.py', 'native_runtime.py'):
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
                db_path = Path(db_path).expanduser().resolve()
                self._file_lock = JournalLock(db_path)
            self._initialize(db_path, config)
        except BaseException:
            self.close()
            raise

    def _initialize(self, db_path, config):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        if self._file_lock is not None:
            self._file_lock.verify(db_path)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS bars (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, source TEXT NOT NULL,
            time TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL,
            UNIQUE(symbol,timeframe,source,time))''')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS observation_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, source TEXT NOT NULL,
            time TEXT NOT NULL, kind TEXT NOT NULL, original TEXT, incoming TEXT NOT NULL,
            received_at TEXT NOT NULL, last_received_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE, after_bar_seq INTEGER NOT NULL, occurrences INTEGER NOT NULL DEFAULT 1)''')
        self.conn.execute('''CREATE TABLE IF NOT EXISTS transport (
            source TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
            status TEXT NOT NULL, checked_at TEXT NOT NULL, rows INTEGER NOT NULL,
            error TEXT, PRIMARY KEY(source,symbol,timeframe))''')
        self.conn.execute('CREATE TABLE IF NOT EXISTS native_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, slot_key TEXT NOT NULL, payload TEXT NOT NULL, after_bar_seq INTEGER NOT NULL)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS native_slot_index ON native_snapshots(slot_key,id)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS acquisitions (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, payload TEXT NOT NULL, after_bar_seq INTEGER NOT NULL)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        identity = {'exchange_calendars_version': version('exchange-calendars'), 'config_hash': Engine(config).config_hash,
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
        self._acquisition_flags = {}
        self._coverage_starts = {}
        for (raw,) in self.conn.execute('SELECT payload FROM acquisitions ORDER BY id'):
            self._remember_acquisition(json.loads(raw))
        self._rebuild()

    def _new(self):
        return {'engine': Engine(self.config), 'bars': deque(maxlen=240),
                'display':PresentationProjector(**self.display_config), 'events': deque(maxlen=200), 'bar_count': 0, 'received_at': None}

    def _apply(self, data, received_at, bar_seq=None):
        key = (data['symbol'], data['timeframe'], data['source'])
        stream = self.streams.setdefault(key, self._new())
        events = stream['engine'].update(Bar.from_dict(data))
        # Do not mutate engine-owned or already published historical objects.
        if bar_seq is None:
            bar_seq = self.conn.execute('SELECT COALESCE(MAX(seq),0)+1 FROM bars').fetchone()[0]
        known_at_receipt = self.conn.execute(
            'SELECT 1 FROM observation_audit WHERE symbol=? AND timeframe=? AND source=? AND after_bar_seq<? LIMIT 1',
            (*key, bar_seq)).fetchone()
        if known_at_receipt:
            events = [{**event, 'data_quality': ('DATA_QUALITY_UNKNOWN' if event.get('data_quality')=='DATA_QUALITY_UNKNOWN' else 'known_revision_or_late_data'),
                       'data_quality_flags': sorted(set(event.get('data_quality_flags',[])+[event.get('data_quality','INTERPOLATION_UNSPECIFIED'),'known_revision_or_late_data'])),
                       'interpretation_basis': 'first_received_bars_not_recomputed'}
                      for event in events]
        stream['bars'].append(data)
        stream['events'].extend(events)
        stream['display'].update(events)
        stream['bar_count'] += 1
        stream['received_at'] = received_at
        return events

    def _rebuild(self):
        self.streams = {}
        for seq, text, received_at in self.conn.execute('SELECT seq,payload,received_at FROM bars ORDER BY seq'):
            self._apply(json.loads(text), received_at, seq)

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

    def ingest_observation(self, payload):
        """Feed ingestion: quarantine valid corrections without rewriting the tape.

        Quarantine is sticky across restarts. Review/replay corrected data in a
        separate journal; this API never automatically resolves an audit entry.
        Only the normalized bar whitelist is persisted, never transport secrets.
        """
        bar = normalize(payload)
        data = {key: _iso(getattr(bar, key)) for key in
                ('symbol','timeframe','time','open','high','low','close','volume','source')}
        data['time'] = _iso(_datetime(data['time']))
        now_dt = datetime.now(timezone.utc)
        if (_datetime(data['time']) - now_dt).total_seconds() > 5:
            raise ValueError('future close time rejected; submit only completed bars')
        key = (data['symbol'], data['timeframe'], data['source'])
        with self.lock:
            existing = self.conn.execute(
                'SELECT payload FROM bars WHERE symbol=? AND timeframe=? AND source=? AND time=?',
                (*key, data['time'])).fetchone()
            original = json.loads(existing[0]) if existing else None
            last = self.conn.execute(
                'SELECT time FROM bars WHERE symbol=? AND timeframe=? AND source=? ORDER BY seq DESC LIMIT 1',
                key).fetchone()
            kind = ('revision' if existing and original != data else
                    'late_arrival' if not existing and last and
                    _datetime(data['time']) <= _datetime(last[0]) else None)
            if kind is None:
                result = self.ingest(data)
                quality = self._data_quality(key)
                return {**result, 'quarantined': False,
                        'data_quality': quality['interpretation_status']}
            audit = dict(symbol=data['symbol'], timeframe=data['timeframe'], source=data['source'],
                         time=data['time'], kind=kind, original=original, incoming=data)
            canonical = json.dumps(audit, sort_keys=True, separators=(',', ':'), allow_nan=False)
            fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
            now = _iso(now_dt)
            prior = self.conn.execute(
                'SELECT id,received_at,occurrences FROM observation_audit WHERE fingerprint=?',
                (fingerprint,)).fetchone()
            try:
                if prior:
                    self.conn.execute(
                        'UPDATE observation_audit SET occurrences=occurrences+1,last_received_at=? WHERE fingerprint=?',
                        (now, fingerprint))
                    audit_id, received_at, count = prior
                    count += 1
                else:
                    cursor = self.conn.execute(
                        'INSERT INTO observation_audit(symbol,timeframe,source,time,kind,original,incoming,received_at,last_received_at,fingerprint,after_bar_seq) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (*key, data['time'], kind,
                         json.dumps(original, sort_keys=True) if original is not None else None,
                         json.dumps(data, sort_keys=True, allow_nan=False), now, now, fingerprint,
                         self.conn.execute('SELECT COALESCE(MAX(seq),0) FROM bars').fetchone()[0]))
                    audit_id, received_at, count = cursor.lastrowid, now, 1
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            audit.update(id=audit_id, received_at=received_at, last_received_at=now,
                         fingerprint=fingerprint, occurrences=count)
            return {'ok': True, 'quarantined': True, 'duplicate': bool(prior),
                    'events': [], 'audit': audit, 'data_quality': 'known_revision_or_late_data'}

    def record_transport(self, source, symbol, status, checked_at, rows, error=None, timeframe='1'):
        """Record response health separately from quote freshness. Never store exceptions."""
        if status not in ('success', 'empty', 'error'):
            raise ValueError('invalid transport status')
        if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
            raise ValueError('invalid transport rows')
        for value in (source, symbol, timeframe):
            if not isinstance(value, str) or not value or len(value)>128 or any(ord(c)<32 for c in value):
                raise ValueError('invalid transport stream')
        checked_at = _iso(_datetime(_iso(checked_at)))
        with self.lock:
            self.conn.execute(
                """INSERT INTO transport(source,symbol,timeframe,status,checked_at,rows,error)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,symbol,timeframe) DO UPDATE SET
                   status=excluded.status,checked_at=excluded.checked_at,rows=excluded.rows,error=excluded.error
                   WHERE excluded.checked_at>=transport.checked_at""",
                (source,symbol,timeframe,status,checked_at,rows,'transport_error' if status=='error' else None))
            self.conn.commit()

    def _transport(self):
        return [dict(source=row[0],symbol=row[1],timeframe=row[2],status=row[3],
                     checked_at=row[4],last_response_rows=row[5],error=row[6])
                for row in self.conn.execute(
                    'SELECT source,symbol,timeframe,status,checked_at,rows,error FROM transport ORDER BY source,symbol,timeframe')]

    def record_native(self, record):
        # Snapshots are separate observations, never retroactively attached to PA events.
        with self.lock:
            seq=self.conn.execute('SELECT COALESCE(MAX(seq),0) FROM bars').fetchone()[0]
            cursor=self.conn.execute('INSERT INTO native_snapshots(slot_key,payload,after_bar_seq) VALUES(?,?,?)',
                (record['slot_key'],json.dumps(record,sort_keys=True,allow_nan=False),seq))
            self.conn.commit()
            return cursor.lastrowid

    def native_snapshot(self, limit=640):
        items=[]
        count=self.conn.execute('SELECT COUNT(DISTINCT slot_key) FROM native_snapshots').fetchone()[0]
        for ident,raw,seq in self.conn.execute('SELECT id,payload,after_bar_seq FROM native_snapshots WHERE id IN (SELECT MAX(id) FROM native_snapshots GROUP BY slot_key) ORDER BY id DESC LIMIT ?', (limit,)):
            item=dict(id=ident,after_bar_seq=seq,**json.loads(raw))
            item['point_count']=len(item['points']);item['points']=item['points'][-20:]
            item['points_truncated']=item['point_count']>20
            item['batch_count']=len(item['batches']);item['batches']=item['batches'][:10]
            item['batches_truncated']=item['batch_count']>10
            items.append(item)
        return dict(items=items,slot_count=count,limit=limit,truncated=count>limit,
                    notice='Current independent provider snapshots; not historical PA inputs. Source quality/warmup unknown; latest does not mean fresh.')

    def record_acquisition(self, evidence):
        """Persist normalized request/provenance, not credentials or raw transport errors."""
        required = {'source','symbols','timeframe','received_at','cutoff','status','quality','batches','bar_provenance'}
        if not isinstance(evidence,dict) or set(evidence)!=required:
            raise ValueError('invalid acquisition evidence')
        if evidence['status'] not in ('DATA_QUALITY_UNKNOWN','NO_USABLE_BARS','PARTIAL_DATA','ELIGIBLE_OBSERVATIONS'):
            raise ValueError('invalid acquisition status')
        encoded=json.dumps(evidence,sort_keys=True,allow_nan=False)
        with self.lock:
            seq=self.conn.execute('SELECT COALESCE(MAX(seq),0) FROM bars').fetchone()[0]
            cursor=self.conn.execute('INSERT INTO acquisitions(source,payload,after_bar_seq) VALUES(?,?,?)',
                                     (evidence['source'],encoded,seq))
            self.conn.commit()
            self._remember_acquisition(evidence)
            return cursor.lastrowid

    def _remember_acquisition(self, item):
        for symbol in item['symbols']:
            key=(symbol,item['timeframe'],item['source'])
            self._acquisition_flags.setdefault(key,set()).add(item['status'])
            starts=[b['request']['start_time'] for b in item['batches']
                    if symbol in b.get('request',{}).get('symbols',[]) and 'start_time' in b['request']]
            if starts:
                self._coverage_starts.setdefault(key,min(starts,key=_datetime))

    def coverage_start(self, symbol, timeframe, source):
        return self._coverage_starts.get((symbol,timeframe,source))

    def _acquisitions(self, limit=10):
        result=[]
        for row in self.conn.execute('SELECT id,payload FROM acquisitions ORDER BY id DESC LIMIT ?', (limit,)):
            item=dict(id=row[0],**json.loads(row[1]))
            item['provenance_count']=len(item['bar_provenance'])
            item['bar_provenance']=item['bar_provenance'][:20]
            item['batches_count']=len(item['batches']);item['batches']=item['batches'][:10]
            for field in ('interpolated_opens','interpolation_unknown_opens'):
                item['quality'].pop(field,None)
            item['snapshot_truncated']=True
            result.append(item)
        return result

    def _acquisition_status(self, key=None):
        # Sticky, incrementally cached quality. Detailed evidence remains in SQLite.
        statuses=set(self._acquisition_flags.get(key,set())) if key else set().union(*self._acquisition_flags.values())
        if key and key[2].endswith(':accept_unknown'):
            statuses.add('DATA_QUALITY_UNKNOWN')
        if key is None and any(k[2].endswith(':accept_unknown') for k in self.streams):
            statuses.add('DATA_QUALITY_UNKNOWN')
        for status in ('DATA_QUALITY_UNKNOWN','PARTIAL_DATA','NO_USABLE_BARS'):
            if status in statuses:return status
        return None

    def _data_quality(self, key=None):
        where = ' WHERE symbol=? AND timeframe=? AND source=?' if key else ''
        rows = self.conn.execute(
            'SELECT kind,COUNT(*),SUM(occurrences) FROM observation_audit' + where + ' GROUP BY kind',
            key or ()).fetchall()
        counts = {kind: count for kind, count, _ in rows}
        total = sum(counts.values())
        observations = sum(count for _, _, count in rows)
        acquisition_status=self._acquisition_status(key)
        return {'acquisition_status':acquisition_status, 'interpretation_status': 'known_revision_or_late_data' if total else 'no_known_quarantine',
                'interpretation_basis': 'first_received_bars_not_recomputed',
                'status': 'DATA_REVIEW_REQUIRED' if total else (acquisition_status or 'NO_QUARANTINED_OBSERVATIONS'),
                'quarantined_count': total, 'revision_count': counts.get('revision', 0),
                'late_arrival_count': counts.get('late_arrival', 0),
                'observation_count': observations, 'duplicate_count': observations-total,
                'policy': 'preserve_original_tape; review_corrected_history_separately'}

    def snapshot(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            result = []
            transport = self._transport()
            for (symbol, timeframe, source), stream in self.streams.items():
                last = stream['bars'][-1]
                age = (now - _datetime(last['time'])).total_seconds()
                seconds = int(timeframe) * 60 if timeframe.isdigit() else 86400
                state = stream['engine'].snapshot()
                freshness = 'FUTURE' if age < -5 else ('STALE' if age > max(120, seconds*2) else 'RECENT')
                warm = state.get('bars_in_segment', 0) >= stream['engine'].config.min_history
                readiness = freshness if freshness != 'RECENT' else ('READY_FOR_RESEARCH' if warm else 'WARMUP')
                quality = self._data_quality((symbol, timeframe, source))
                if any(t['status']=='error' and (t['symbol'],t['timeframe'],t['source'])==(symbol,timeframe,source) for t in transport):
                    readiness = 'TRANSPORT_ERROR'
                if quality['acquisition_status']:
                    readiness = quality['acquisition_status']
                if quality['quarantined_count']:
                    readiness = 'DATA_REVIEW_REQUIRED'
                result.append(dict(data_quality=quality, symbol=symbol, timeframe=timeframe, source=source,
                    bar_count=stream['bar_count'], bars=list(stream['bars']), events=list(stream['events']),
                    display=stream['display'].snapshot(), state=state, last_bar_close=last['time'], received_at=stream['received_at'],
                    age_seconds=round(age, 2), freshness=freshness, readiness=readiness, ready=readiness == 'READY_FOR_RESEARCH'))
            ready = bool(result) and all(s['ready'] for s in result)
            readiness = 'WAITING_FOR_DATA' if not result else ('READY_FOR_RESEARCH' if ready else 'NOT_READY')
            quality = self._data_quality()
            if any(t['status']=='error' for t in transport):
                ready, readiness = False, 'TRANSPORT_ERROR'
            if quality['acquisition_status']:
                ready, readiness = False, quality['acquisition_status']
            if quality['quarantined_count']:
                ready, readiness = False, 'DATA_REVIEW_REQUIRED'
            return {'native_indicators':self.native_snapshot(), 'acquisitions':self._acquisitions(), 'transport': transport, 'data_quality': quality, 'mode': 'research_only', 'live_verified': False, 'ready': ready, 'readiness': readiness,
                    'rule_identity': dict(self.identity), 'streams': result,
                    'notice': 'Robinhood 主动只读获取；DATA_QUALITY_UNKNOWN 表示插值标记缺失，探索结果不可当已验证信号。本地 EMA/RSI 独立计算，不等于供应商指标。日线时间为保守的下一 UTC 午夜可用时刻。存在隔离修订或迟到数据时，解释基于首次接收版K线且未重算，须另库复核，不应依赖其结构判断。接收器不是行情供应商；RECENT仅表示提交的时间戳接近当前，不代表已验证实时报价。收市时历史bar会显示STALE。'}

    def health(self, now=None):
        result = self.snapshot(now)
        streams = [{key: stream[key] for key in ('symbol','timeframe','source','bar_count','last_bar_close','received_at','age_seconds','freshness','readiness','ready','data_quality')} for stream in result['streams']]
        status = 'WAITING_FOR_DATA' if not streams else ('RECENT_INPUT' if all(s['freshness']=='RECENT' for s in streams) else 'STALE')
        return {'native_indicators':result['native_indicators'], 'acquisitions':result['acquisitions'], 'transport': result['transport'], 'data_quality': result['data_quality'], 'status': status, 'live_verified': False, 'ready': result['ready'], 'readiness': result['readiness'], 'rule_identity': result['rule_identity'], 'streams': streams, 'notice': result['notice']}

    def close(self):
        with self.lock:
            try:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
            finally:
                if self._file_lock is not None:
                    # Sidecars persist to prevent a second lock domain.
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
