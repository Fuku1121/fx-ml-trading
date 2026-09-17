"""Explicit short subscription probe. No historical API or paper decisions."""
import argparse
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode
import websocket
import collector
from runner import fingerprint,load_config,read_key


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=90);args=parser.parse_args()
    if not 30<=args.seconds<=300:raise ValueError('Probe duration must be 30..300 seconds')
    bundle=fingerprint();c=load_config();key=read_key();counts={s:0 for s in c['symbols']}
    with collector.single_instance(args.state_dir):
        ws=websocket.create_connection('wss://ws.finnhub.io?'+urlencode({'token':key}),timeout=10)
        try:
            ws.settimeout(3)
            for symbol in counts:ws.send(json.dumps({'type':'subscribe','symbol':symbol}))
            end=time.monotonic()+args.seconds
            while time.monotonic()<end and not all(counts.values()):
                try:payload=json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:ws.ping('probe');continue
                if payload.get('type')=='error':raise PermissionError('Subscription rejected; check account entitlement')
                for row in payload.get('data',[]):
                    if row.get('s') in counts:
                        stamp=float(row.get('t',0))/1000;price=float(row.get('p',0))
                        if math.isfinite(price) and price>0 and time.time()-15<=stamp<=time.time():counts[row['s']]+=1
            result={'updated_at':collector.iso(time.time()),'bundle':bundle,'all_symbols_observed':all(counts.values()),'counts':counts,'real_orders':False}
            collector.atomic_json(args.state_dir/'subscription_probe.json',result)
            print(json.dumps(result,indent=2))
            if not all(counts.values()):raise RuntimeError('Not all four symbols observed; probe during open market')
        finally:ws.close(timeout=1)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Probe stopped:',type(exc).__name__,'No orders sent. No key printed.')
        raise SystemExit(42) from None
