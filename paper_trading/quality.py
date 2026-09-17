"""Experimental observed-price eligibility, preserving original quality flags.

No invented ticks or filled OHLC. A bounded observation gap is uncertainty,
not proof of complete candles or suitability for real execution.
"""
import json
import re
import sqlite3

MAX_INTERVAL_GAP = 60.0
MAX_BOUNDARY_GAP = 30.0
MIN_OBSERVATIONS = 30


def assess(row, points, created, spans):
    start,o,h,l,c,n,clean,reason = row
    if clean:
        return True,'original_clean',None
    if reason != 'partial_or_disconnected' or start < created or len(points)<MIN_OBSERVATIONS:
        return False,reason,None
    times=[t/1000 for t,p in points]
    prices=[p for t,p in points]
    gap=max([b-a for a,b in zip(times,times[1:])]+[0])
    lead,tail=times[0]-start,start+900-times[-1]
    stats=dict(first_delay=lead,last_delay=tail,max_gap=gap,observations=len(points))
    if (prices[0],max(prices),min(prices),prices[-1]) != (o,h,l,c) or len(points)!=n:
        return False,'raw_bar_mismatch',stats
    covered=any(a<=start and b>=start+900 for a,b in spans)
    if covered:
        return True,'connection_covered_before_grace_disconnect',stats
    if lead<=MAX_BOUNDARY_GAP and tail<=MAX_BOUNDARY_GAP and gap<=MAX_INTERVAL_GAP:
        return True,'bounded_gap_observed_prices',stats
    return False,'observation_gap_too_large',stats


class View:
    """Paper reads evaluated bars; collector keeps writing its original tables."""
    def __init__(self, session):
        self.session=session
        self.directory=session.directory
        self.db=self
        self.source=session.db
        self.source.execute('''CREATE TABLE IF NOT EXISTS candidate_bars(
            start INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,
            ticks INTEGER,clean INTEGER,reason TEXT,source_clean INTEGER,
            source_reason TEXT,evidence TEXT)''')

    def execute(self, sql, args=()):
        sql=re.sub(r'\bFROM bars\b','FROM candidate_bars',sql)
        return self.source.execute(sql,args)

    def refresh(self, at):
        events=self.source.execute("SELECT at,kind FROM events WHERE kind IN ('CONNECTED','DISCONNECTED') ORDER BY id").fetchall()
        spans=[]
        connected=None
        for stamp,kind in events:
            if kind=='CONNECTED': connected=stamp
            elif connected is not None:
                spans.append((connected,stamp));connected=None
        if connected is not None:
            spans.append((connected,min(at,self.session.observed_until)))
        rows=self.source.execute('''SELECT b.start,b.open,b.high,b.low,b.close,b.ticks,b.clean,b.reason
            FROM bars b LEFT JOIN candidate_bars q ON q.start=b.start
            WHERE q.start IS NULL OR q.source_clean!=b.clean OR q.source_reason!=b.reason OR q.ticks!=b.ticks''').fetchall()
        with self.source:
            for row in rows:
                points=[]
                if not row[6] and row[7]=='partial_or_disconnected':
                    points=self.source.execute('SELECT event_ms,price FROM ticks WHERE event_ms>=? AND event_ms<? ORDER BY event_ms,id',(row[0]*1000,(row[0]+900)*1000)).fetchall()
                usable,label,evidence=assess(row,points,self.session.started,spans)
                self.source.execute('INSERT OR REPLACE INTO candidate_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (*row[:6],int(usable),label,row[6],row[7],json.dumps(evidence)))

    def summary(self, anchor, end):
        rows=self.source.execute('SELECT reason,count(*) FROM candidate_bars WHERE start>=? AND start<=? AND clean=1 GROUP BY reason',(anchor,end)).fetchall()
        return dict(rows)


def backup_db(source, target):
    source=source.resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    dst=sqlite3.connect(target)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Snapshot integrity check failed')
    finally:
        src.close();dst.close()
