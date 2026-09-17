"""Read-only evaluation of separate paper accounts. Never submits orders."""
import argparse
from contextlib import closing
from collections import Counter
import json
from pathlib import Path
import sqlite3
import time
from engine import market_closed
from capital_plan import evaluate_saved


def read_snapshot(root):
    path=Path(root)/'comparison.sqlite3'
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('BEGIN')
        state=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
        trades=[(name,json.loads(data)) for name,data in db.execute('SELECT account,data FROM trades ORDER BY bar')]
        decisions=[(name,json.loads(data)) for name,data in db.execute('SELECT model,data FROM decisions ORDER BY bar')]
        events=dict(db.execute('SELECT kind,COUNT(*) FROM events GROUP BY kind'))
    return state,trades,decisions,events


def evaluate(root,at=None):
    at=time.time() if at is None else at
    state,trades,decisions,events=read_snapshot(root)
    observed_until=min(at,state['updated_at'])
    start=state['start'];end=min(observed_until,state['end']) if state['end'] is not None else observed_until
    initial=state['initial_equity']
    # Fractional 24-hour market days include intervals with zero orders.
    market_seconds=0.0
    if start is not None:
        cursor=start
        while cursor<end:
            boundary=min(end,(int(cursor)//900+1)*900)
            if not market_closed(cursor):market_seconds+=boundary-cursor
            cursor=boundary
    accounts={}
    for name,a in state['accounts'].items():
        rows=[r for n,r in trades if n==name]
        wins=sum(r['net_return']>0 for r in rows)
        # Cash PnL, rather than a sum of percentage returns, defines profit factor.
        profit=loss=0.;previous=initial
        for row in rows:
            pnl=row['equity_after']-previous;previous=row['equity_after']
            profit+=max(0.,pnl);loss+=max(0.,-pnl)
        accounts[name]={
            'closed_trades':len(rows),'win_rate':wins/len(rows) if rows else None,
            'realized_equity_jpy':a['equity'],'realized_pnl_jpy':a['equity']-initial,
            'realized_return':a['equity']/initial-1,
            'stress_realized_return':a['stress_equity']/initial-1,
            'profit_factor':profit/loss if loss else None,
            'profit_factor_note':'undefined without a losing trade' if not loss else 'cash gains / cash losses',
            'observed_mtm_max_drawdown':a['mtm_max_drawdown'],
            'trades_per_market_day':len(rows)/(market_seconds/86400) if market_seconds else None,
            'open_position':a['position'],'pending_entry':a['pending'],
            'last_observed_mtm':a.get('last_observed_mtm'),
        }
    counts={model:dict(Counter(d['reason'] for n,d in decisions if n==model)) for model in ('base','candidate')}
    return {'as_of':at,'phase':state['phase'],'reason':state['reason'],'common_start':start,'common_end':state['end'],
        'bundle':state['bundle'],'market_days_elapsed':market_seconds/86400,'accounts':accounts,
        'decision_reasons':counts,'events':events,'histories':state['histories'],
        'user_capital_plan':evaluate_saved(root,state,trades,at),
        'limitations':[
            'Accounts are alternatives: never add their PnL together.',
            'Fixed spread/slippage assumptions; fills are observed prices, not broker executable bid/ask.',
            'Open/unresolved positions are excluded from realized PnL; last observed valuation can be stale.',
            'Drawdown is based on received observations, not prices missed during outages.',
            'Prediction calibration/accuracy requires separate future-label analysis; win rate is not model accuracy.',
            '30 calendar days and few trades cannot establish future profitability.',
        ],'real_orders':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--output',type=Path);args=p.parse_args()
    result=evaluate(args.state_dir);body=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(body,encoding='utf-8')
    print(body)


if __name__=='__main__':main()
