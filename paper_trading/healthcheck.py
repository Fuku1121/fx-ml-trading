"""Local health status only. Does not send notifications or restart halted experiments."""
import argparse
import json
from pathlib import Path
import time
from datetime import datetime
from engine import market_closed


def check(root,at=None):
    at=time.time() if at is None else at
    path=Path(root)/'status.json'
    if not path.exists():return 1,'No runtime heartbeat yet'
    status=json.loads(path.read_text(encoding='utf-8'));phase=status['state']['phase']
    if phase=='HALTED':return 2,'HALTED: '+status['state']['reason']
    if phase=='COMPLETED':return 0,'COMPLETED (not running)'
    age=at-datetime.fromisoformat(status['updated_at']).timestamp()
    if age< -10 or age>180:return 2,'Heartbeat stale or clock invalid'
    if not all(f.get('connected',False) for f in status['feeds'].values()):return 1,'Disconnected; inspect reconnect and price timestamps'
    if not market_closed(at):
        for symbol,feed in status['feeds'].items():
            latest=feed.get('last_tick')
            if latest is None or at-datetime.fromisoformat(latest).timestamp()>180:
                return 1,'No recent market observations: '+symbol
    return 0,phase+'; fresh controller heartbeat (not a guarantee of fresh market prices)'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-dir',type=Path,required=True);a=p.parse_args()
    code,message=check(a.state_dir);print(message);raise SystemExit(code)
