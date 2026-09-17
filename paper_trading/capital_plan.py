"""Cash-flow-aware paper replay of saved entries, with observed-price margin exits.

It does not generate new signals or change the reference accounts. An early
margin exit does not introduce extra entries before the next saved entry.
"""
from pathlib import Path
from contextlib import closing
import json
import math
import sqlite3
import pandas as pd
from engine import costs

ROOT=Path(__file__).resolve().parent


def margin_fraction(equity,confidence,plan,switched=False):
    if not switched and equity<=plan['switch_above_equity_jpy']:return 1.
    if plan['after_threshold']=='full_equity':return 1.
    edge=max(0.,min(1.,(confidence-plan['threshold'])/(1-plan['threshold'])))
    original=max(.25,min(2.,(.5+edge)*plan['sizing_scale']))
    return original/plan['max_original_size']


def anniversaries(start,end):
    anchor=pd.Timestamp(start,unit='s',tz='UTC').tz_convert('Asia/Tokyo')
    month=1
    while True:
        stamp=(anchor+pd.DateOffset(months=month)).timestamp()
        if stamp>end:return
        yield stamp
        month+=1


def replay(entries,ticks_for,start,end,plan,config,stress=False):
    cash=plan['initial_capital_jpy'];contributed=cash;closed=[];deposits=[]
    schedule=iter(anniversaries(start,end));next_deposit=next(schedule,None)
    switched=False;phase='OBSERVING';open_position=None;stopped_at=None
    def credit(until):
        nonlocal cash,contributed,next_deposit,switched
        while next_deposit is not None and next_deposit<=until:
            cash+=plan['monthly_deposit_jpy'];contributed+=plan['monthly_deposit_jpy']
            deposits.append({'at':next_deposit,'amount_jpy':plan['monthly_deposit_jpy']})
            switched |= cash>plan['switch_above_equity_jpy']
            next_deposit=next(schedule,None)
    for source in sorted(entries,key=lambda r:r['entry_time']):
        entry=source['entry_time']
        if entry>end:break
        credit(entry)
        if cash<=0:phase='INSOLVENT';stopped_at=entry;break
        switched |= cash>plan['switch_above_equity_jpy']
        fraction=margin_fraction(cash,source['confidence'],plan,switched)
        notional=cash*fraction*plan['leverage_on_allocated_margin']
        units=notional/source['entry_price'];side=source['side'];last=entry
        due=source.get('exit_time',source['due']);cutoff=min(end,due)
        open_position={'entry_time':entry,'entry_price':source['entry_price'],'units_usd':units,
            'margin_fraction':fraction,'effective_entry_leverage':fraction*plan['leverage_on_allocated_margin'],
            'side':side,'entry_equity_jpy':cash,'bar':source['bar']}
        normal,adverse=costs(config,source['entry_price']);charge=notional*(adverse if stress else normal)
        samples=[(entry,source['entry_price'])]
        samples.extend(ticks_for(entry,cutoff))
        for stamp,price in samples:
            if stamp<last:continue
            if not math.isfinite(price) or price<=0:raise ValueError('Invalid observed price')
            if stamp-last>config['max_observation_gap_seconds']:
                phase='UNRESOLVED_DATA_GAP';stopped_at=stamp;break
            credit(stamp);last=stamp
            pnl=units*side*(price-source['entry_price'])-charge
            liquidation_equity=cash+pnl
            required=units*price/plan['leverage_on_allocated_margin']
            margin_stop=liquidation_equity<=required*plan['margin_stop_ratio_assumption']
            if margin_stop or stamp>=due:
                cash=liquidation_equity
                closed.append({**open_position,'exit_time':stamp,'exit_price':price,'pnl_jpy':pnl,
                    'equity_after_jpy':cash,'cost_jpy':charge,'reason':'ASSUMED_MARGIN_STOP' if margin_stop else 'SCHEDULED_EXIT'})
                open_position=None;switched |= cash>plan['switch_above_equity_jpy']
                if cash<=0:phase='INSOLVENT';stopped_at=stamp
                break
            open_position['last_observed_equity_jpy']=liquidation_equity
            open_position['last_observed_at']=stamp
        if phase in ('INSOLVENT','UNRESOLVED_DATA_GAP'):break
        if open_position:
            if end-last>config['max_observation_gap_seconds'] or end>=due:
                phase='UNRESOLVED_EXIT';stopped_at=last
            break
    if stopped_at is None:credit(end)
    return {'phase':phase,'initial_capital_jpy':plan['initial_capital_jpy'],
        'total_contributions_jpy':contributed,'deposits':deposits,'cash_balance_jpy':cash,
        'realized_trading_pnl_jpy':sum(t['pnl_jpy'] for t in closed),
        'open_position':open_position,'trades':closed,'closed_trades':len(closed),'stopped_at':stopped_at,
        'confidence_stage_reached':switched,'cost_scenario':'stress' if stress else 'normal',
        'note':'Cash balance includes deposits. Open PnL is separate. No real orders; broker execution is not simulated exactly.'}


def evaluate_saved(root,state,trades,at):
    plan=json.loads((ROOT/'capital_plan.json').read_text());config=json.loads((ROOT/'protocol.json').read_text())
    if plan['real_orders'] is not False:raise ValueError('Paper only')
    if state['start'] is None:return {'status':'WARMUP','plan':plan,'accounts':{}}
    end=min(at,state['updated_at'],state['end'])
    path=Path(root)/'feeds/USD_JPY/observations.sqlite3'
    if not path.exists():return {'status':'MISSING_OBSERVATIONS','plan':plan,'accounts':{}}
    results={}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        def ticks_for(start,finish):
            return [(ms/1000,price) for ms,price in db.execute(
                'SELECT event_ms,price FROM ticks WHERE event_ms>? AND event_ms<=? AND id<=? AND received<=? AND received-event_ms/1000.0 BETWEEN 0 AND ? ORDER BY id',
                (start*1000,finish*1000,state['tick_id'],end,config['max_tick_age_seconds']))]
        for account in ('base_fixed','candidate_fixed'):
            entries=[r for name,r in trades if name==account]
            position=state['accounts'][account]['position']
            if position:entries.append(position)
            results[account]={label:replay(entries,ticks_for,state['start'],end,plan,config,stress)
                for label,stress in [('normal',False),('stress',True)]}
    return {'status':'PAPER_REPLAY','plan':plan,'accounts':results,
        'limitations':['Same saved entry schedule as reference account; no additional entries after an early margin stop.',
            '50% margin maintenance is an assumption, not a verified broker rule.',
            'Deposits on monthly anniversaries, not every 30 days. Taxes and cloud fees excluded.',
            'Observed prices and hypothetical spread costs; negative balances are retained, not clipped to zero.']}
