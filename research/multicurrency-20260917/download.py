"""Download public research candles. No credentials, orders, or live subscriptions."""
from pathlib import Path
import hashlib
import json
import time
import requests
import pandas as pd
import dukascopy_python as duka

HERE = Path(__file__).resolve().parent
PAIRS = ('USD/JPY', 'EUR/USD', 'GBP/USD', 'AUD/USD')


def fetch(pair, side, year):
    """Use the same installed client as the original USD/JPY dataset."""
    start=pd.Timestamp(f'{year}-01-01',tz='UTC')
    end=pd.Timestamp('2026-09-01' if year==2026 else f'{year+1}-01-01',tz='UTC')
    frame=duka.fetch(pair,duka.INTERVAL_MIN_15,side,start.to_pydatetime(),end.to_pydatetime(),
        max_retries=0,limit=30000)
    frame=frame.loc[(frame.index>=start)&(frame.index<end)]
    assert frame.index.is_unique and len(frame)>10000
    assert (frame[['open','high','low','close']]>0).all().all()
    assert (frame.high>=frame[['open','low','close']].max(axis=1)).all()
    assert (frame.low<=frame[['open','high','close']].min(axis=1)).all()
    return frame


def main():
    original_get=requests.get
    def paced_get(*args,**kwargs):
        time.sleep(.5)
        kwargs.setdefault('timeout',45)
        response=original_get(*args,**kwargs)
        if response.status_code==429:
            delay=max(60,int(response.headers.get('Retry-After','60')))
            print('RATE LIMITED; backoff',delay,flush=True)
            time.sleep(delay)
            response=original_get(*args,**kwargs)
        response.raise_for_status()
        return response
    duka.requests.get=paced_get
    folder=HERE/'data';folder.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for pair in PAIRS:
        for year in range(2021,2027):
            for side in ('B','A'):
                path=folder/f'{pair.replace("/", "")}_{year}_{side}.csv'
                if not path.exists():
                    print('FETCH',pair,year,side,flush=True)
                    frame=fetch(pair,side,year)
                    frame.to_csv(path)
                else:
                    frame=pd.read_csv(path,index_col=0)
                manifest.append(dict(pair=pair,year=year,side=side,rows=len(frame),file=path.name,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                (HERE/'data_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('DATA COMPLETE',len(manifest),flush=True)


if __name__=='__main__':main()
