"""V0.5.2 conservative monitoring foundation.

Records research observations, NEVER emits real-time trade/entry notifications.
Provider bar timestamps are NOT exchange-verified close timestamps.
The watchlist is NOT an independently verified main-contract universe.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ma144_60m import is_contract, normalize_minutes, evaluate_bars, Market60mError

CN_TZ = timezone(timedelta(hours=8))
SCHEMA = """CREATE TABLE IF NOT EXISTS observations(
 event_id TEXT PRIMARY KEY, contract TEXT NOT NULL, bar_time TEXT NOT NULL,
 direction TEXT NOT NULL, classification TEXT NOT NULL, observed_at TEXT NOT NULL,
 data_source TEXT NOT NULL, details TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS scans(
 scan_id INTEGER PRIMARY KEY AUTOINCREMENT, contract TEXT NOT NULL,
 observed_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
 last_bar TEXT, main_verified INTEGER NOT NULL DEFAULT 0,
 close_verified INTEGER NOT NULL DEFAULT 0);
 CREATE INDEX IF NOT EXISTS scans_contract_time ON scans(contract,observed_at);
 """

def utcnow():
    return datetime.now(timezone.utc)

def validate_watchlist(value):
    """Explicit list is a test universe, not proof of the active main contract."""
    if not isinstance(value, list) or len(value)>100:
        raise ValueError("监测列表应为不超过100个具体合约的数组")
    normalized=[]
    for item in value:
        if not isinstance(item, str) or not is_contract(item) or item.strip().upper().endswith(("888","999","000")):
            raise ValueError("监测列表只接受具体期货合约")
        code=item.strip().upper()
        if code not in normalized:
            normalized.append(code)
    return normalized

def init_db(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def observation_id(contract,bar_time,direction):
    material=f"v052|{contract}|{bar_time}|{direction}".encode()
    return hashlib.sha256(material).hexdigest()[:32]

def classify_observation(result, *, observed_at=None, max_age_minutes=120):
    """Never call a third-party historical candle 'exchange confirmed'.

    Always excludes provider's last bar as in the V0.5.0 engine. A timestamp
    alone cannot prove candle is closed; independent exchange/calendar checks
    must be implemented before notifications can be enabled.
    """
    observed_at=observed_at or datetime.now(CN_TZ)
    if observed_at.tzinfo is None:
        observed_at=observed_at.replace(tzinfo=CN_TZ)
    bar_time=result.get("latest_usable_timestamp")
    if not bar_time:
        return {"status":"insufficient_data","age_minutes":None,
                "main_contract_verified":False,"closed_bar_verified":False,
                "notification_allowed":False}
    ts=datetime.fromisoformat(bar_time)
    if ts.tzinfo is None:
        ts=ts.replace(tzinfo=CN_TZ)
    age=(observed_at-ts).total_seconds()/60
    if age<0:
        status="future_timestamp"
    elif age>max_age_minutes:
        status="stale"
    elif result.get("signal")=="filtered":
        status="filtered"
    elif result.get("raw_cross_direction") in ("up","down"):
        status="historical_cross"
    else:
        status="no_cross"
    return {"status":status,"age_minutes":round(age,1),
            "main_contract_verified":False, "closed_bar_verified":False,
            "provider_time_semantics_verified":False,
            "notification_allowed":False,
            "reason":"行情源的K线标记与收盘真实性未经交易所独立核验"}

def record_scan(conn,contract,result,*,observed_at=None):
    observed_at=observed_at or datetime.now(CN_TZ)
    if observed_at.tzinfo is None:
        observed_at=observed_at.replace(tzinfo=CN_TZ)
    cls=classify_observation(result,observed_at=observed_at)
    with conn:
        conn.execute("""INSERT INTO scans(contract,observed_at,status,error,last_bar,
            main_verified,close_verified) VALUES(?,?,?,?,?,?,?)""",
            (contract,observed_at.isoformat(),cls["status"],None,
             result.get("latest_usable_timestamp"),0,0))
        raw=result.get("raw_cross_direction")
        if raw in ("up","down") and result.get("latest_usable_timestamp"):
            key=observation_id(contract,result["latest_usable_timestamp"],raw)
            cur=conn.execute("""INSERT OR IGNORE INTO observations(event_id,contract,bar_time,
                direction,classification,observed_at,data_source,details)
                VALUES(?,?,?,?,?,?,?,?)""",
                (key,contract,result["latest_usable_timestamp"],raw,cls["status"],
                 observed_at.isoformat(),result.get("source","AKShare/Sina"),
                 json.dumps({"close":result.get("last_close"),
                   "ma144":result.get("ma144"),
                   "cross_distance_pct":result.get("cross_distance_pct"),
                   "notification_allowed":False},ensure_ascii=False)))
            is_new=cur.rowcount>0
        else:
            is_new=False
    return {"contract":contract,"new_record":is_new,**cls}

def record_error(conn,contract,exc,*,observed_at=None):
    observed_at=observed_at or datetime.now(CN_TZ)
    # Avoid inserting full external exception text containing tokens or secrets.
    with conn:
        conn.execute("""INSERT INTO scans(contract,observed_at,status,error)
            VALUES(?,?,?,?)""",
            (contract,observed_at.isoformat(),"provider_error",type(exc).__name__))

def scan_once(watchlist,db_path,*,provider=None,clock=None):
    watchlist=validate_watchlist(watchlist)
    clock=clock or (lambda:datetime.now(CN_TZ))
    if provider is None:
        import akshare as provider
    conn=init_db(db_path)
    output=[]
    try:
        for contract in watchlist:
            try:
                frame=provider.futures_zh_minute_sina(symbol=contract,period="60")
                rows=normalize_minutes(frame)
                result=evaluate_bars(contract,rows,now=clock())
                output.append(record_scan(conn,contract,result,observed_at=clock()))
            except Exception as exc:
                record_error(conn,contract,exc,observed_at=clock())
                output.append({"contract":contract,"status":"provider_error",
                               "error_type":type(exc).__name__,
                               "notification_allowed":False})
    finally:
        conn.close()
    return output

def read_latest(db_path,limit=30):
    limit=max(1,min(int(limit),100))
    if not os.path.isfile(db_path):
        return {"observations":[],"latest_scans":[],"notification_enabled":False}
    conn=sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    try:
        observations=[dict(row) for row in conn.execute(
            "SELECT event_id,contract,bar_time,direction,classification,observed_at,details "
            "FROM observations ORDER BY observed_at DESC LIMIT ?",(limit,))]
        scans=[dict(row) for row in conn.execute(
            "SELECT contract,observed_at,status,error,last_bar,main_verified,close_verified "
            "FROM scans ORDER BY scan_id DESC LIMIT ?",(limit,))]
        return {"observations":observations,"latest_scans":scans,
                "notification_enabled":False,
                "main_contracts_verified":False,
                "warning":"测试监测池，仅保存历史观测，不构成实时交易所核验或通知"}
    finally:
        conn.close()

def main():
    import argparse
    p=argparse.ArgumentParser(description="V0.5.2 historical research poller")
    p.add_argument("--watchlist",required=True,help="JSON file with list of specific contracts")
    p.add_argument("--database",default="/var/lib/futures-ai/monitor-v052.sqlite3")
    p.add_argument("--once",action="store_true")
    p.add_argument("--interval",type=int,default=60)
    a=p.parse_args()
    if a.interval<30 or a.interval>3600:
        p.error("interval should be 30-3600 seconds")
    with open(a.watchlist,encoding="utf-8") as fh:
        watchlist=validate_watchlist(json.load(fh))
    if not watchlist:
        p.error("watchlist is empty")
    while True:
        print(json.dumps(scan_once(watchlist,a.database),ensure_ascii=False),flush=True)
        if a.once:
            break
        time.sleep(a.interval)

if __name__=="__main__":
    main()
