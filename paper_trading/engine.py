"""Atomic paper accounts; no broker integration and no network calls."""
from pathlib import Path
import copy
import json
import math
import sqlite3
import pandas as pd


def market_closed(stamp):
    t=pd.Timestamp(stamp,unit='s',tz='UTC').tz_convert('America/New_York')
    return t.dayofweek==5 or (t.dayofweek==4 and t.hour>=17) or (t.dayofweek==6 and t.hour<17)


def next_bar(stamp):
    stamp+=900
    while market_closed(stamp):stamp+=900
    return stamp


def crosses_rollover(start,end):
    def day(t):return (pd.Timestamp(t,unit='s',tz='UTC').tz_convert('America/New_York')+pd.Timedelta(hours=7)).date()
    return day(start)!=day(end)


def costs(config,entry):
    pip=.01
    usual=config['commission_return_roundtrip']+(config['assumed_spread_pips']+config['slippage_pips_roundtrip'])*pip/entry
    stress=config['commission_return_roundtrip']+(config['assumed_spread_pips']*config['stress_spread_multiplier']+config['stress_slippage_pips_roundtrip'])*pip/entry
    return usual,stress


class Engine:
    def __init__(self,root,config,bundle,created=None,clock=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.config=config;self.clock=clock;self.db=sqlite3.connect(self.root/'comparison.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS decisions(model TEXT,bar INTEGER,data TEXT NOT NULL,PRIMARY KEY(model,bar));
          CREATE TABLE IF NOT EXISTS trades(account TEXT,bar INTEGER,data TEXT NOT NULL,PRIMARY KEY(account,bar));
          CREATE TABLE IF NOT EXISTS equity(at REAL,account TEXT,data TEXT NOT NULL,PRIMARY KEY(at,account));
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,detail TEXT);
        ''')
        row=self.db.execute('SELECT data FROM state WHERE id=1').fetchone()
        if row:
            self.state=json.loads(row[0])
            if self.state['bundle']!=bundle:
                self.db.close();raise RuntimeError('Bundle changed; existing experiment cannot resume')
        else:
            if created is None:raise ValueError('New experiment needs an explicit creation time')
            accounts={}
            for name in ('base_fixed','candidate_fixed','base_legacy'):
                accounts[name]={'equity':config['initial_equity'],'stress_equity':config['initial_equity'],
                    'position':None,'pending':None,'trades':0,'mtm_peak':config['initial_equity'],'mtm_max_drawdown':0.0}
            self.state={'bundle':bundle,'created':created,'updated_at':created,'initial_equity':config['initial_equity'],'phase':'WARMUP','start':None,'end':None,
                'last_bar':None,'tick_id':0,'last_tick':None,'accounts':accounts,'reason':'Waiting for four eligible histories',
                'histories':{symbol:{'anchor':None,'last':None,'count':0,'cursor':None} for symbol in config['symbols']}}
            with self.db:self.save()

    def save(self):
        self.db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(json.dumps(self.state,allow_nan=False),))

    def event(self,at,kind,detail):
        self.db.execute('INSERT INTO events(at,kind,detail) VALUES(?,?,?)',(at,kind,detail))

    def halt(self,at,reason):
        self.state.update(phase='HALTED',reason=reason,updated_at=at)
        for account in self.state['accounts'].values():account['pending']=None
        self.event(at,'HALTED',reason)

    def disconnected(self,at):
        with self.db:
            for account in self.state['accounts'].values():account['pending']=None
            self.event(at,'DISCONNECTED','Pending entries cancelled; positions retained')
            self.save()

    def atomic_step(self,ticks,bar,frames,quality,ready,predict,at,histories=None,revoked=False):
        before=copy.deepcopy(self.state)
        try:
            with self.db:
                if histories is not None:self.state['histories']=histories
                if revoked and any(a['position'] for a in self.state['accounts'].values()):
                    self.halt(at,'Historical quality revoked while holding; review required')
                else:self._step(ticks,bar,frames,quality,ready,predict,at)
                if before['phase'] not in ('HALTED','COMPLETED'):self.state['updated_at']=at
                self.save()
        except BaseException:
            self.state=before
            raise

    def _step(self,ticks,bar,frames,quality,ready,predict,at):
        s=self.state;c=self.config
        if s['phase'] in ('HALTED','COMPLETED'):return
        if at<s['created']-10 or (s['last_tick'] is not None and at<s['last_tick']-10):
            self.halt(at,'Clock moved backwards');return
        for ident,ms,received,price in ticks:
            if ident<=s['tick_id']:continue
            s['tick_id']=ident;stamp=ms/1000
            if stamp>at:continue  # future-dated observations never fill a paper order
            if s['last_tick'] is not None and stamp<s['last_tick']:continue
            holding=any(a['position'] for a in s['accounts'].values())
            if holding and s['last_tick'] is not None and stamp-s['last_tick']>c['max_observation_gap_seconds']:
                self.halt(at,'USDJPY observation gap while holding; PnL unresolved');return
            s['last_tick']=stamp
            fresh=0<=at-stamp<=c['max_tick_age_seconds'] and 0<=at-received<=c['max_tick_age_seconds']
            for name,a in s['accounts'].items():
                position=a['position']
                if position and stamp>=position['due']:
                    if not fresh or stamp-position['due']>c['max_observation_gap_seconds']:
                        self.halt(at,'Exit observation unavailable on time; position retained');return
                    normal,stress=costs(c,position['entry_price'])
                    if name=='base_legacy':normal=stress=c['legacy_cost_return']
                    gross=position['side']*(price/position['entry_price']-1)
                    net=position['size']*(gross-normal);stress_net=position['size']*(gross-stress)
                    a['equity']*=1+net;a['stress_equity']*=1+stress_net;a['trades']+=1
                    record={**position,'exit_time':stamp,'exit_received':received,'exit_price':price,
                        'gross_return':gross,'net_return':net,'stress_net_return':stress_net,
                        'equity_after':a['equity'],'stress_equity_after':a['stress_equity'],
                        'cost_return':normal,'stress_cost_return':stress,'fill_model':'received_observation_not_bid_ask'}
                    self.db.execute('INSERT INTO trades VALUES(?,?,?)',(name,position['bar'],json.dumps(record)))
                    a['position']=None;self.event(at,'EXIT',name)
                pending=a['pending']
                if pending:
                    if at>pending['expires']:
                        a['pending']=None;self.event(at,'ENTRY_EXPIRED',name)
                    elif fresh and received>pending['decision_at'] and stamp>=pending['decision_at'] and not market_closed(stamp):
                        a['position']={**pending,'entry_time':stamp,'entry_received':received,'entry_price':price,'due':stamp+pending['hold']}
                        a['pending']=None;self.event(at,'ENTRY',name)
                if fresh:
                    position=a['position'];mtm=a['equity']
                    if position:
                        normal,_=costs(c,position['entry_price'])
                        if name=='base_legacy':normal=c['legacy_cost_return']
                        mtm*=1+position['size']*(position['side']*(price/position['entry_price']-1)-normal)
                    a['mtm_peak']=max(a['mtm_peak'],mtm)
                    a['mtm_max_drawdown']=min(a['mtm_max_drawdown'],mtm/a['mtm_peak']-1)
                    a['last_observed_mtm']=mtm
        for name,a in s['accounts'].items():
            if a['position'] and at-(s['last_tick'] or at)>c['max_observation_gap_seconds']:
                self.halt(at,'No USDJPY observations for 120 seconds while holding');return
            if a['pending'] and at>a['pending']['expires']:
                a['pending']=None;self.event(at,'ENTRY_EXPIRED',name)
        if s['end'] is not None and at>=s['end']:
            if any(a['position'] for a in s['accounts'].values()):self.halt(at,'End reached with unresolved position')
            else:
                for a in s['accounts'].values():a['pending']=None
                s.update(phase='COMPLETED',reason='Common 30-day comparison completed')
            return
        if s['start'] is None and at-s['created']>=c['warmup_max_days']*86400:
            self.halt(at,'Warmup exceeded configured limit; check all four subscriptions');return
        if bar is None or (s['last_bar'] is not None and bar<=s['last_bar']):return
        if not bar+900<=at<=bar+900+c['entry_window_seconds']:return
        if market_closed(bar):return
        if not ready:
            # Collector waits five seconds to finalize a bar. Give all feeds
            # time to finalize before persisting one irreversible no-trade decision.
            if at<bar+900+c['entry_window_seconds']-5:return
            if s['start'] is not None:
                for model in ('base','candidate'):
                    self.decision(model,bar,{'action':'NO_TRADE','reason':'SHARED_DATA_QUALITY','quality':quality,'at':at})
                s['last_bar']=bar
            s['reason']='Waiting for four aligned clean decision bars and eligible histories'
            return
        predictions=predict(frames,at)
        decision_at=self.clock() if self.clock is not None else at
        for p in predictions.values():
            if not math.isfinite(p['confidence']) or not 0<=p['confidence']<=1:raise ValueError('Invalid model probability')
        if s['start'] is None:
            if decision_at>bar+900+c['entry_window_seconds']:return
            s.update(phase='RUNNING',start=decision_at,end=decision_at+c['comparison_days']*86400)
            self.event(at,'COMPARISON_STARTED','Both predictors ready; one common deadline')
        for model,p in predictions.items():
            account='base_fixed' if model=='base' else 'candidate_fixed'
            targets=[account,'base_legacy'] if model=='base' else [account]
            hold=c['base_hold_seconds'] if model=='base' else c['candidate_hold_seconds']
            reason=p.get('reason','LOW_CONFIDENCE');allowed=bool(p['allowed'])
            if decision_at>bar+900+c['entry_window_seconds']:allowed=False;reason='INFERENCE_TOO_LATE'
            if any(s['accounts'][n]['position'] or s['accounts'][n]['pending'] for n in targets):allowed=False;reason='POSITION_OPEN'
            if decision_at+c['entry_window_seconds']+hold+c['max_observation_gap_seconds']>=s['end']:allowed=False;reason='END_WINDOW'
            if crosses_rollover(decision_at,decision_at+c['entry_window_seconds']+hold):allowed=False;reason='ROLLOVER_WINDOW'
            self.decision(model,bar,{**p,'action':'SIGNAL' if allowed else 'NO_TRADE','reason':'SIGNAL' if allowed else reason,'quality':quality,'at':decision_at})
            if allowed:
                for name in targets:
                    size=p.get('legacy_size',1.) if name=='base_legacy' else 1.
                    if not math.isfinite(size) or size<=0:raise ValueError('Invalid size')
                    s['accounts'][name]['pending']={'bar':bar,'side':p['side'],'size':size,'hold':hold,
                        'decision_at':decision_at,'expires':bar+900+c['entry_window_seconds'],'confidence':p['confidence'],'quality':quality}
        s['last_bar']=bar;s['reason']='Comparison running'

    def decision(self,model,bar,data):
        self.db.execute('INSERT INTO decisions VALUES(?,?,?)',(model,bar,json.dumps(data,allow_nan=False)))

    def sample_equity(self,at):
        with self.db:
            for name,a in self.state['accounts'].items():
                self.db.execute('INSERT OR REPLACE INTO equity VALUES(?,?,?)',(int(at),name,json.dumps(a)))

    def close(self):self.db.close()
