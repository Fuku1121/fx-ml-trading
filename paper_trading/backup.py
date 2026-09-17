"""SQLite online backups. Each DB is consistent; multi-DB snapshots are sequential."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


def backup(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    sources=[root/'comparison.sqlite3']+sorted((root/'feeds').glob('*/*.sqlite3'))
    if not sources[0].is_file():raise FileNotFoundError('Experiment database missing')
    folder=destination/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False);records=[]
    for source in sources:
        relative=source.relative_to(root);target=folder/relative;target.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed')
        records.append({'file':relative.as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size})
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'files':records,
        'consistency':'Per-database consistent; sequential across databases. Reconciliation required before restore.',
        'restore':'Stop service; retain current state; review positions and feed cursors. No automatic restore or replay fills.'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return folder


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
    print(backup(a.state_dir,a.destination))
