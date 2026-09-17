"""One Finnhub WebSocket, four symbols, isolated paper accounts. No order API."""
from pathlib import Path
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
import signal
import time
from urllib.parse import urlencode
from threadpoolctl import threadpool_limits
import collector
import quality
from engine import Engine
from history import frames_for
from predictors import Predictors

ROOT=Path(__file__).resolve().parent


def fingerprint():
    expected=json.loads((ROOT/'bundle_hashes.json').read_text())
    for name,digest in expected.items():
        p=ROOT/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Bundle file changed: '+name)
    return hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest()


def load_config():
    c=json.loads((ROOT/'protocol.json').read_text())
    if c['real_orders'] is not False or c['threshold']!=.58 or c['comparison_days']!=30:
        raise RuntimeError('Unexpected experiment configuration')
    return c


def symbol_module(symbol):
    spec=importlib.util.spec_from_file_location('collector_'+symbol.replace(':','_'),ROOT/'collector.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.SYMBOL=symbol
    return module


def read_key():
    directory=os.getenv('CREDENTIALS_DIRECTORY')
    if directory:
        path=Path(directory)/'finnhub_api_key'
        if path.exists():key=path.read_text().strip()
        else:key=''
    else:key=os.getenv('FINNHUB_API_KEY','').strip()
    if not key:raise RuntimeError('No Finnhub credential configured; never put keys in command arguments')
    return key


def initialize(root,c,bundle):
    root=Path(root).resolve()
    with collector.single_instance(root):
        if (root/'comparison.sqlite3').exists():raise RuntimeError('Existing experiment is preserved; init refuses overwrite')
        at=time.time()
        engine=Engine(root,c,bundle,created=at)
        try:
            for symbol in c['symbols']:
                module=symbol_module(symbol)
                session=module.Session(root/'feeds'/symbol.split(':')[1],created=at,hours=(c['comparison_days']+c['warmup_max_days']+1)*24)
                session.close()
        finally:engine.close()
    print('Initialized new paper comparison. No connection or orders started.')


def status(root):
    import sqlite3
    path=Path(root)/'comparison.sqlite3'
    if not path.exists():raise RuntimeError('Initialize experiment first')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        state=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
    print(json.dumps(state,ensure_ascii=False,indent=2))


def run(root,c,bundle):
    import websocket
    root=Path(root).resolve()
    if not (root/'comparison.sqlite3').exists():raise RuntimeError('Explicit init is required; no automatic new experiment')
    if (root/'STOP').exists():raise RuntimeError('STOP marker exists; review before restart')
    stop=[False]
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.__setitem__(0,True))
    with collector.single_instance(root):
        engine=Engine(root,c,bundle,clock=time.time)
        if engine.state['phase'] in ('COMPLETED','HALTED'):
            print('Saved experiment phase:',engine.state['phase'])
            code=42 if engine.state['phase']=='HALTED' else 0;engine.close();return code
        key=read_key();predict=Predictors(c);sessions={};views={};ws=None
        last_health=last_ping=last_export=0.;next_connect=0.;attempt=0
        for symbol in c['symbols']:
            module=symbol_module(symbol);session=module.Session(root/'feeds'/symbol.split(':')[1])
            sessions[symbol]=session;views[symbol]=quality.View(session)
        def export(at):
            collector.atomic_json(root/'status.json',{'updated_at':collector.iso(at),'paper_only':True,'real_orders':False,
                'state':engine.state,'feeds':{s:session.report('COLLECTING' if session.connected else 'DISCONNECTED') for s,session in sessions.items()}})
            engine.sample_equity(at)
        try:
            while not stop[0] and not (root/'STOP').exists():
                at=time.time()
                if at>=next_connect and ws is None:
                    try:
                        ws=websocket.create_connection('wss://ws.finnhub.io?'+urlencode({'token':key}),timeout=10)
                        ws.settimeout(2)
                        for symbol in c['symbols']:ws.send(json.dumps({'type':'subscribe','symbol':symbol}))
                        at=time.time()
                        for session in sessions.values():session.connect(at)
                        last_health=at;last_ping=0
                        print(collector.iso(at),'CONNECTED; waiting for observations from all four symbols',flush=True)
                    except (OSError,websocket.WebSocketException) as exc:
                        if ws is not None:
                            try:ws.close(timeout=1)
                            except Exception:pass
                        ws=None
                        if getattr(exc,'status_code',None) in (401,403):raise PermissionError('Provider rejected connection') from None
                        attempt+=1;next_connect=time.time()+collector.retry_delay(attempt,True)
                        engine.event(at,'CONNECT_RETRY',type(exc).__name__);engine.db.commit()
                if ws is not None:
                    try:
                        if time.time()-last_ping>=20:ws.ping('health');last_ping=time.time()
                        try:opcode,data=ws.recv_data(control_frame=True)
                        except websocket.WebSocketTimeoutException:
                            opcode,data=None,None
                            if time.time()-last_health>60:raise ConnectionError('No websocket heartbeat')
                        received=time.time()
                        if opcode==websocket.ABNF.OPCODE_CLOSE:raise ConnectionError('Peer closed')
                        if opcode in (websocket.ABNF.OPCODE_PING,websocket.ABNF.OPCODE_PONG):
                            last_health=received
                            for session in sessions.values():session.observed_until=received
                        elif opcode in (websocket.ABNF.OPCODE_TEXT,websocket.ABNF.OPCODE_BINARY):
                            try:payload=json.loads(data)
                            except (ValueError,UnicodeError):raise ConnectionError('Malformed frame') from None
                            if payload.get('type')=='error':
                                kind,detail=collector.provider_error(payload,key)
                                if kind in ('AUTH','UNKNOWN'):raise PermissionError('Provider rejected subscription')
                                raise collector.RetryableProviderError(detail,kind)
                            last_health=received
                            for session in sessions.values():session.receive(payload,received,key)
                            if payload.get('type')=='trade':attempt=0
                    except (OSError,websocket.WebSocketException) as exc:
                        if isinstance(exc,PermissionError):raise
                        at=time.time()
                        for session in sessions.values():session.disconnect(at,type(exc).__name__)
                        engine.disconnected(at)
                        try:ws.close(timeout=1)
                        except Exception:pass
                        ws=None;attempt+=1;next_connect=at+collector.retry_delay(attempt,isinstance(exc,collector.RetryableProviderError))
                        print(collector.iso(at),'DISCONNECTED; retry scheduled; state retained',flush=True)
                else:time.sleep(.25)
                at=time.time()
                for symbol,session in sessions.items():session.finalize(at);views[symbol].refresh(at)
                bar,frames,audit,ready,histories,revoked=frames_for(engine,views,at)
                ticks=sessions[c['symbols'][0]].db.execute('SELECT id,event_ms,received,price FROM ticks WHERE id>? ORDER BY id',(engine.state['tick_id'],)).fetchall()
                engine.atomic_step(ticks,bar,frames,audit,ready,predict,at,histories,revoked)
                if at-last_export>=15:
                    export(at);last_export=at
                if engine.state['phase'] in ('COMPLETED','HALTED'):break
            export(time.time())
            return 42 if engine.state['phase']=='HALTED' else 0
        except BaseException:
            with engine.db:engine.halt(time.time(),'Runner stopped with an error; review required');engine.save()
            export(time.time());raise
        finally:
            if ws is not None:
                try:ws.close(timeout=1)
                except Exception:pass
            for session in sessions.values():session.disconnect(time.time(),'RUNNER_STOPPED')
            engine.disconnected(time.time())
            export(time.time())
            for session in sessions.values():session.close()
            engine.close()


def main():
    parser=argparse.ArgumentParser(description='Preparation defaults to offline checks. No broker orders.')
    parser.add_argument('command',choices=('preflight','init','run','status'),nargs='?',default='preflight')
    parser.add_argument('--state-dir',type=Path)
    args=parser.parse_args();bundle=fingerprint();c=load_config()
    with threadpool_limits(limits=2):
        if args.command=='preflight':
            Predictors(c);print('PASS: code/model hashes and model loading. Live four-symbol entitlement NOT tested.');return 0
        if args.state_dir is None:parser.error('--state-dir is required')
        if args.command=='init':initialize(args.state_dir,c,bundle);return 0
        if args.command=='status':status(args.state_dir);return 0
        return run(args.state_dir,c,bundle)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # Provider exceptions can embed token URLs. Never print them or traceback.
        print('Stopped:',type(exc).__name__,'Review status/events; state was not reset.',flush=True)
        raise SystemExit(42) from None
