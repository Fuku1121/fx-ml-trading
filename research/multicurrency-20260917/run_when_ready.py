"""Run each pair once its download manifest is complete."""
from pathlib import Path
import json
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
for pair in ('USDJPY','EURUSD','GBPUSD','AUDUSD'):
    deadline=time.monotonic()+3600
    while True:
        try:
            manifest=json.loads((root/'data_manifest.json').read_text())
            count=sum(r['pair'].replace('/','')==pair for r in manifest)
        except (FileNotFoundError,json.JSONDecodeError):count=0
        if count==12:break
        if time.monotonic()>deadline:raise TimeoutError(f'Download incomplete: {pair}')
        time.sleep(5)
    subprocess.run([sys.executable,str(root/'research.py'),'--pair',pair],check=True)
print('ALL PAIRS TRAINED',flush=True)
