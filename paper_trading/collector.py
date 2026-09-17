"""Finnhub-only forward data collection. No REST history, model, or orders.

Raw observations commit to SQLite before bars are finalized. Gaps are visible,
never filled with invented prices. Interrupted sessions resume to their original
deadline; finished sessions stay on disk and a new run starts a new session.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import getpass
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlencode
import uuid

SYMBOL = 'OANDA:USD_JPY'
BAR_SECONDS = 900
GRACE = 5
SCHEMA = 1


class RetryableProviderError(ConnectionError):
    def __init__(self, message, category):
        super().__init__(message)
        self.category = category


def provider_error(payload, secret=''):
    """Retain a sanitized explanation, never log the complete server payload."""
    raw = ' '.join(str(payload[k]) for k in ('msg','message','error') if k in payload)
    low = raw.lower()
    safe = raw.replace(secret,'[REDACTED]') if secret else raw
    safe = re.sub(r'(?:https?|wss?)://\S+','[URL REDACTED]',safe)
    safe = re.sub(r'(?i)((?:api[_ -]?key|token|secret|authorization)\s*[=:]\s*)\S+',r'\1[REDACTED]',safe)
    safe = re.sub(r'[A-Za-z0-9_-]{20,}','[LONG VALUE REDACTED]',safe)
    safe = ' '.join(safe.split())[:400] or 'No error explanation supplied'
    if any(s in low for s in ('invalid api key','invalid token','unauthorized','not authorized','permission denied','access denied','invalid credentials')):
        return 'AUTH',safe
    if any(s in low for s in ('limit','too many','already connected','one connection','1 connection','maximum connections')):
        return 'LIMIT',safe
    if any(s in low for s in ('temporar','try again','busy','timeout','unavailable','internal error')):
        return 'TEMPORARY',safe
    return 'UNKNOWN',safe


def retry_delay(attempt, provider=False):
    # Give the provider time to release a disconnected key's old connection.
    return min(300 if provider else 120,(60 if provider else 15)*2**min(attempt-1,5))


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def single_instance(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root/'collector.lock').open('a+b') as f:
        if os.fstat(f.fileno()).st_size == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Another collector is running. Stop the previous cell first.') from None
        yield


class Session:
    def __init__(self, directory, created=None, hours=24):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory/'observations.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS session(id INTEGER PRIMARY KEY CHECK(id=1),schema_version INTEGER,symbol TEXT,started REAL,deadline REAL);
          CREATE TABLE IF NOT EXISTS ticks(id INTEGER PRIMARY KEY,event_ms INTEGER NOT NULL,received REAL NOT NULL,price REAL NOT NULL,connection INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS ticks_time ON ticks(event_ms);
          CREATE TABLE IF NOT EXISTS bars(start INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,ticks INTEGER NOT NULL,clean INTEGER NOT NULL,reason TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);
        ''')
        meta = self.db.execute('SELECT schema_version,symbol,started,deadline FROM session WHERE id=1').fetchone()
        if meta is None:
            if created is None:
                raise RuntimeError('Session metadata missing. No state was reset.')
            self.db.execute('INSERT INTO session VALUES(1,?,?,?,?)',(SCHEMA,SYMBOL,created,created+hours*3600))
            self.db.commit()
            meta = (SCHEMA,SYMBOL,created,created+hours*3600)
        if meta[:2] != (SCHEMA,SYMBOL):
            raise RuntimeError('Session schema/symbol mismatch. No state was reset.')
        _,_,self.started,self.deadline = meta
        self.connected = False
        self.clean_from = None
        self.observed_until = 0.
        self.connection = int(self.db.execute("SELECT COUNT(*) FROM events WHERE kind='CONNECTED'").fetchone()[0])
        # After a restart there is no evidence of uninterrupted observation.
        self.event('RESUMED', 'Partial and offline intervals remain invalid')

    def event(self, kind, detail='', at=None):
        with self.db:
            self.db.execute('INSERT INTO events(at,kind,detail) VALUES(?,?,?)',(time.time() if at is None else at,kind,detail))

    def connect(self, at):
        self.connected = True
        self.connection += 1
        self.clean_from = (int(at)//BAR_SECONDS+1)*BAR_SECONDS
        self.observed_until = at
        self.event('CONNECTED','New complete-interval boundary='+iso(self.clean_from),at)

    def disconnect(self, at, reason):
        self.connected = False
        self.clean_from = None
        self.event('DISCONNECTED',reason,at)

    def receive(self, payload, at, secret=''):
        """Persist one received batch atomically. No token or whole payload logged."""
        if not isinstance(payload,dict):
            self.event('BAD_PAYLOAD','Expected an object',at)
            self.clean_from = (int(at)//BAR_SECONDS+1)*BAR_SECONDS
            return
        if payload.get('type') == 'error':
            category,explanation = provider_error(payload,secret)
            self.event('PROVIDER_ERROR',f'{category}: {explanation}',at)
            if category == 'AUTH':
                raise PermissionError('Finnhub authentication/permission error: '+explanation)
            raise RetryableProviderError(explanation,category)
        self.observed_until = at
        if payload.get('type') != 'trade':
            return
        data = payload.get('data')
        if not isinstance(data,list):
            self.event('BAD_PAYLOAD','Trade data must be a list',at)
            self.clean_from = (int(at)//BAR_SECONDS+1)*BAR_SECONDS
            return
        accepted = 0
        with self.db:
            for row in data:
                if not isinstance(row,dict) or row.get('s') != SYMBOL:
                    continue
                try:
                    event_ms = int(row['t'])
                    price = float(row['p'])
                    valid = math.isfinite(price) and price > 0 and at-120 <= event_ms/1000 <= at+10
                except (KeyError,ValueError,TypeError,OverflowError):
                    valid = False
                if not valid:
                    self.db.execute('INSERT INTO events(at,kind,detail) VALUES(?,?,?)',(at,'REJECTED_TICK','Invalid price/time'))
                    self.clean_from = (int(at)//BAR_SECONDS+1)*BAR_SECONDS
                    continue
                self.db.execute('INSERT INTO ticks(event_ms,received,price,connection) VALUES(?,?,?,?)',(event_ms,at,price,self.connection))
                accepted += 1
                start = (event_ms//1000)//BAR_SECONDS*BAR_SECONDS
                # Late observations remain in the raw table. Previously exported
                # bars lose eligibility rather than being silently revised.
                self.db.execute("UPDATE bars SET clean=0,reason='late_tick_after_finalization' WHERE start=?",(start,))
        return accepted

    def finalize(self, at):
        first = int(self.started)//BAR_SECONDS*BAR_SECONDS
        last = self.db.execute('SELECT MAX(start) FROM bars').fetchone()[0]
        start = first if last is None else last+BAR_SECONDS
        limit = min(at,self.deadline)
        with self.db:
            while start+BAR_SECONDS+GRACE <= limit:
                end = start+BAR_SECONDS
                rows = self.db.execute('SELECT price FROM ticks WHERE event_ms>=? AND event_ms<? ORDER BY event_ms,id',(start*1000,end*1000)).fetchall()
                # Wait for a subsequent frame to confirm connection health. If
                # no frame arrives, the network timeout invalidates the interval.
                if self.connected and self.clean_from is not None and start >= self.clean_from and self.observed_until < end+GRACE:
                    break
                clean = bool(rows and self.connected and self.clean_from is not None and start >= self.clean_from and start >= self.started and self.observed_until >= end+GRACE)
                reason = 'complete_observed_interval' if clean else 'no_ticks' if not rows else 'partial_or_disconnected'
                prices = [r[0] for r in rows]
                values = (prices[0],max(prices),min(prices),prices[-1]) if prices else (None,None,None,None)
                self.db.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',(start,*values,len(prices),int(clean),reason))
                start += BAR_SECONDS

    def report(self, status):
        ticks,last_tick = self.db.execute('SELECT COUNT(*),MAX(event_ms) FROM ticks').fetchone()
        count,clean = self.db.execute('SELECT COUNT(*),COALESCE(SUM(clean),0) FROM bars').fetchone()
        latest = self.db.execute('SELECT MAX(start) FROM bars').fetchone()[0]
        errors = self.db.execute("SELECT COUNT(*) FROM events WHERE kind IN ('NETWORK_RETRY','REJECTED_TICK','BAD_PAYLOAD')").fetchone()[0]
        last_error = self.db.execute("SELECT kind,detail FROM events WHERE kind IN ('PROVIDER_ERROR','NETWORK_RETRY') ORDER BY id DESC LIMIT 1").fetchone()
        return {'mode':'DATA_COLLECTION_ONLY','status':status,'updated_at':iso(time.time()),'started_at':iso(self.started),'scheduled_end':iso(self.deadline),
                'symbol':SYMBOL,'connected':self.connected,'connections':self.connection,'raw_observations':ticks,
                'last_tick':iso(last_tick/1000) if last_tick is not None else None,'bars':count,'clean_bars':clean,'incomplete_or_empty_bars':count-clean,
                'last_bar':iso(latest) if latest is not None else None,'retry_or_input_events':errors,'last_error':': '.join(last_error) if last_error else None,'real_orders':False,'model_inference':False,'directory':str(self.directory)}

    def export(self):
        for name,query in [('bars_15m.csv','SELECT * FROM bars ORDER BY start'),('clean_bars_15m.csv','SELECT * FROM bars WHERE clean=1 ORDER BY start')]:
            path = self.directory/name
            temp = path.with_suffix('.tmp')
            with temp.open('w',newline='',encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp','open','high','low','close','observations','clean','quality_reason'])
                for row in self.db.execute(query):
                    writer.writerow([iso(row[0]),*row[1:]])
                f.flush();os.fsync(f.fileno())
            os.replace(temp,path)

    def close(self):
        self.db.close()


def open_session(root,hours,at):
    active = root/'active.json'
    if active.exists():
        value = json.loads(active.read_text(encoding='utf-8'))
        directory = (root/value['session']).resolve()
        if not directory.is_relative_to(root.resolve()):
            raise RuntimeError('Invalid active session path')
        session = Session(directory)
        if at < session.deadline:
            return session
        session.finalize(session.deadline)
        session.export()
        session.close()
    name = datetime.fromtimestamp(at,timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    session = Session(root/name,created=at,hours=hours)
    atomic_json(active,{'session':name})
    return session


def collect(root,hours=24,stop_file=None,cycle_hook=None):
    import websocket
    root = Path(root).resolve()
    stop_file = Path(stop_file) if stop_file else root/'STOP'
    with single_instance(root):
        if stop_file.exists():
            raise RuntimeError('STOP file is present; review the previous stop before restarting.')
        key = os.getenv('FINNHUB_API_KEY','').strip() or getpass.getpass('Finnhub API key: ').strip()
        if not key:
            raise ValueError('Finnhub API key is empty')
        session = open_session(root,hours,time.time())
        status = 'CONNECTING'
        ws = None
        retry = 0
        unknown_errors = 0
        next_connect = 0.
        last_heartbeat = last_console = last_ping = 0.
        heartbeat_path = session.directory/'heartbeat.json'
        clock_deadline = time.monotonic()+max(0,session.deadline-time.time())
        print('NEW FORWARD DATA COLLECTION / FINNHUB WEBSOCKET ONLY / NO ORDERS',flush=True)
        print('Session:',session.directory,flush=True)
        print('Deadline UTC:',iso(session.deadline),flush=True)
        if os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        try:
            while time.time() < session.deadline and time.monotonic() < clock_deadline and not stop_file.exists():
                at = time.time()
                try:
                    if ws is None and time.monotonic() >= next_connect:
                        print('Connecting to Finnhub...',flush=True)
                        ws = websocket.create_connection('wss://ws.finnhub.io?'+urlencode({'token':key}),timeout=10)
                        ws.settimeout(3)
                        ws.send(json.dumps({'type':'subscribe','symbol':SYMBOL}))
                        session.connect(time.time())
                        status = 'CONNECTED_WAITING_FOR_TICKS'
                        print('Connected. Waiting for price observations.',flush=True)
                    if ws is not None:
                        if time.monotonic()-last_ping >= 20:
                            ws.ping('health')
                            last_ping = time.monotonic()
                        try:
                            opcode,data = ws.recv_data(control_frame=True)
                            received = time.time()
                            if opcode == websocket.ABNF.OPCODE_CLOSE:
                                raise ConnectionError('Peer closed connection')
                            if opcode in (websocket.ABNF.OPCODE_PONG,websocket.ABNF.OPCODE_PING):
                                session.observed_until = received
                            elif opcode in (websocket.ABNF.OPCODE_TEXT,websocket.ABNF.OPCODE_BINARY):
                                try:payload = json.loads(data)
                                except (ValueError,UnicodeError):
                                    session.event('BAD_PAYLOAD','Invalid JSON')
                                    raise ConnectionError('Invalid JSON') from None
                                accepted = session.receive(payload,received,key)
                                if accepted:
                                    status = 'COLLECTING'
                                    retry = 0
                                    unknown_errors = 0
                        except websocket.WebSocketTimeoutException:
                            if time.time()-session.observed_until > 60:
                                raise ConnectionError('No websocket health response for 60 seconds')
                    else:
                        time.sleep(.25)
                except PermissionError:
                    status = 'AUTH_OR_SUBSCRIPTION_REJECTED'
                    raise
                except (OSError,websocket.WebSocketException) as exc:
                    if getattr(exc,'status_code',None) in (401,403):
                        status = 'AUTH_OR_SUBSCRIPTION_REJECTED'
                        raise PermissionError('Finnhub WebSocket rejected authentication/permission. Check the Finnhub key.') from None
                    session.disconnect(time.time(),type(exc).__name__)
                    retry += 1
                    if ws is not None:
                        try:ws.close(timeout=1)
                        except Exception:pass
                    ws = None
                    if isinstance(exc,RetryableProviderError):
                        print(f'Finnhub server reply ({exc.category}): {exc}',flush=True)
                        if exc.category == 'UNKNOWN':
                            unknown_errors += 1
                            if unknown_errors > 3:
                                raise RuntimeError('Repeated unclassified Finnhub errors: '+str(exc)) from None
                    delay = retry_delay(retry,isinstance(exc,RetryableProviderError))
                    next_connect = time.monotonic()+delay
                    session.event('NETWORK_RETRY',f'{type(exc).__name__}; retry in {delay}s')
                    print(f'Connection interrupted; retrying in {delay} seconds. Saved data retained.',flush=True)
                    status = 'RECONNECTING'
                session.finalize(time.time())
                if cycle_hook is not None and cycle_hook(session, time.time()) is False:
                    status = 'PAPER_CONTROLLER_FINISHED'
                    break
                if time.monotonic()-last_heartbeat >= 15:
                    report = session.report(status)
                    atomic_json(heartbeat_path,report)
                    atomic_json(root/'latest_status.json',report)
                    session.export()
                    last_heartbeat = time.monotonic()
                    if time.monotonic()-last_console >= 60:
                        print(f'{report["updated_at"]} {status} observations={report["raw_observations"]} clean_15m={report["clean_bars"]} incomplete_or_empty={report["incomplete_or_empty_bars"]}',flush=True)
                        last_console = time.monotonic()
            if status != 'PAPER_CONTROLLER_FINISHED':
                status = 'STOPPED_BY_USER' if stop_file.exists() else 'COMPLETED_COLLECTION_WINDOW'
        except KeyboardInterrupt:
            status = 'STOPPED_BY_USER'
        except Exception:
            if status != 'AUTH_OR_SUBSCRIPTION_REJECTED':status = 'STOPPED_WITH_ERROR'
            raise
        finally:
            if ws is not None:
                try:ws.close(timeout=1)
                except Exception:pass
            session.disconnect(time.time(),status)
            session.finalize(time.time())
            session.export()
            report = session.report(status)
            atomic_json(heartbeat_path,report)
            atomic_json(root/'latest_status.json',report)
            session.close()
            if os.name == 'nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent/'sessions')
    parser.add_argument('--hours',type=float,default=24)
    parser.add_argument('--stop-file',type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.hours) or args.hours <= 0:parser.error('--hours must be positive and finite')
    try:
        collect(args.root,args.hours,args.stop_file)
    except (PermissionError,ValueError,RuntimeError,sqlite3.Error,OSError) as exc:
        print('COLLECTOR STOPPED:',str(exc),flush=True)
        raise SystemExit(1) from None
