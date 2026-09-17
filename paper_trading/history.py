"""Read quality-reviewed bars without changing their original price/quality."""
import copy
import pandas as pd
from engine import market_closed,next_bar


def frames_for(engine,views,at):
    histories=copy.deepcopy(engine.state['histories']);frames={};audit={};revoked=False
    decision_bar=int(at)//900*900-900
    all_ready=True
    for symbol,view in views.items():
        h=histories[symbol]
        if h['anchor'] is not None:
            bad=view.execute('SELECT start FROM bars WHERE start>=? AND start<=? AND clean=0',(h['anchor'],h['last'])).fetchall()
            if any(not market_closed(r[0]) for r in bad):
                revoked=True;h.update(anchor=None,last=None,count=0)
        rows=view.execute('SELECT start,clean FROM bars WHERE start>? ORDER BY start',(h['cursor'] if h['cursor'] is not None else -1,)).fetchall()
        for stamp,clean in rows:
            h['cursor']=stamp
            if market_closed(stamp):continue
            if not clean:
                h.update(anchor=None,last=None,count=0);continue
            if h['last'] is not None and next_bar(h['last'])!=stamp:h.update(anchor=None,last=None,count=0)
            if h['anchor'] is None:h['anchor']=stamp
            h['last']=stamp;h['count']+=1
        quality={'history_bars':h['count'],'anchor':h['anchor'],'last_bar':h['last'],'latest_original_clean':False}
        ready=h['count']>=engine.config['minimum_history_bars'] and h['last']==decision_bar
        if ready:
            tail=view.execute('SELECT reason FROM bars WHERE start>=? AND start<=? AND clean=1 ORDER BY start DESC LIMIT 150',(h['anchor'],decision_bar)).fetchall()
            bounded=sum(r[0]=='bounded_gap_observed_prices' for r in tail)
            original=tail[0][0]=='original_clean'
            quality.update(bounded_gap_bars=bounded,latest_original_clean=original)
            ready=original and bounded<=engine.config['max_bounded_gap_bars_per_150']
            latest=view.source.execute('SELECT MAX(event_ms) FROM ticks WHERE event_ms>=? AND event_ms<?',(decision_bar*1000,(decision_bar+900)*1000)).fetchone()[0]
            lag=decision_bar+900-latest/1000 if latest is not None else None
            quality['last_observation_lag_seconds']=lag
            ready=ready and lag is not None and 0<=lag<=30
        if ready:
            records=view.execute('SELECT start,open,high,low,close FROM bars WHERE start>=? AND start<=? AND clean=1 ORDER BY start',(h['anchor'],decision_bar)).fetchall()
            f=pd.DataFrame(records,columns=['time','open','high','low','close'])
            f.index=pd.DatetimeIndex(pd.to_datetime(f.pop('time'),unit='s',utc=True)).as_unit('us')
            frames[symbol]=f
        quality['eligible']=ready;audit[symbol]=quality;all_ready &= ready
    return decision_bar,frames,audit,all_ready,histories,revoked
