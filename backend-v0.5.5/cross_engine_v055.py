"""V0.5.5: independent, fail-closed 60m MA144 crossing event engine.

The signal depends ONLY on consecutive *verified CLOSED* 60m bars, not
daily technical filters, risk/return, sentiment or entry opportunity scores.
An event can be saved for audit; notifying users remains disabled until
main-contract / official-close evidence and a mobile push transport exist.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import sqlite3
from pathlib import Path

CONTRACT=re.compile(r"^[A-Z]{1,3}\d{3,4}$")

def parse_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z","+00:00")) if isinstance(value,str) else value
        if dt.tzinfo is None: raise ValueError("naive datetime")
        return dt.astimezone(timezone.utc)
    except (AttributeError,TypeError) as e:
        raise ValueError("invalid timestamp") from e

def _price(value):
    if isinstance(value,bool):raise ValueError("bool price")
    x=float(value)
    if not math.isfinite(x) or x<=0:raise ValueError("invalid price")
    return x

def analyse_cross(contract, bars, *, main_contract_verified=False,
                  exchange_calendar_verified=False, provider_close_verified=False,
                  timestamp_semantics_verified=False, max_close_delay_s=60,
                  observed_at=None):
    """Return research crossing and eligibility separately; do not enqueue push.

    bars: ascending 145+ completed 60m candles, with close and end_time,
    independently verified state in each bar: close_verified must be True.
    Unknown vendor timing never gets treated as verified.
    """
    if not isinstance(contract,str) or not CONTRACT.fullmatch(contract.upper()):
        raise ValueError("requires concrete dated futures contract")
    r={"version":"0.5.5","contract":contract.upper(),"timeframe":"60m",
       "cross":"none","research_cross":"none","signal_id":None,
       "main_contract_verified":bool(main_contract_verified),
       "official_close_verified":False,"notification_allowed":False,
       "notification_sent":False,"entry_signal":False,"blockers":[]}
    if not isinstance(bars,list) or len(bars)<145:
        r["blockers"].append("至少需要145根连续60分钟K线")
        return r
    times=[]; closes=[]
    for bar in bars:
        if not isinstance(bar,dict):raise ValueError("invalid bar")
        times.append(parse_time(bar["end_time"]))
        closes.append(_price(bar["close"]))
    if any(b<=a for a,b in zip(times,times[1:])):
        r["blockers"].append("K线时间非严格递增或存在重复")
        return r
    # Consecutive *trading* 60-minute segments need a verified exchange session
    # calendar; one wall-clock hour gap is not reliable across breaks/night sessions.
    previous_ma=sum(closes[-145:-1])/144
    latest_ma=sum(closes[-144:])/144
    previous_diff=closes[-2]-previous_ma
    latest_diff=closes[-1]-latest_ma
    if previous_diff<=0 and latest_diff>0:cross="up"
    elif previous_diff>=0 and latest_diff<0:cross="down"
    else:cross="none"
    r.update(research_cross=cross,previous_close=closes[-2],
             previous_ma144=round(previous_ma,8),
             close=closes[-1],ma144=round(latest_ma,8),
             bar_end=times[-1].isoformat())
    if cross!="none":
        r["signal_id"]=sha256(
            f"v055|{r['contract']}|{times[-1].isoformat()}|{cross}".encode()
        ).hexdigest()[:32]
    if not main_contract_verified:r["blockers"].append("真实主力合约身份未核验")
    if not exchange_calendar_verified:r["blockers"].append("交易所分段交易日历未核验")
    if not provider_close_verified:r["blockers"].append("行情源最终收盘状态未独立确认")
    if not timestamp_semantics_verified:r["blockers"].append("行情源时间戳语义未校准")
    if not all(b.get("close_verified") is True for b in bars[-2:]):
        r["blockers"].append("最近两根K线收盘凭据不足")
    obs=parse_time(observed_at or datetime.now(timezone.utc))
    delay=(obs-times[-1]).total_seconds()
    r["delay_seconds"]=round(delay,1)
    if delay<0:r["blockers"].append("K线结束时间晚于观测时刻")
    elif delay>max_close_delay_s:r["blockers"].append("超出收盘后一分钟实时通知时效")
    # Deliberate hard gate: research results are never real-time eligible in v055.
    # Official exchange verification and push transport not yet implemented.
    r["blockers"].append("V0.5.5仅供研究，未接入权威收盘核验和手机推送通道")
    return r

def save_research(path,result,*,observed_at=None):
    """Idempotent audit store; never persists an actionable notification job."""
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(p),timeout=15)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS cross_research(
            signal_id TEXT PRIMARY KEY, contract TEXT NOT NULL,
            bar_end TEXT NOT NULL,direction TEXT NOT NULL,
            observed_at TEXT NOT NULL,details TEXT NOT NULL)""")
        if result.get("research_cross") not in ("up","down") or not result.get("signal_id"):
            return False
        with con:
            cur=con.execute("INSERT OR IGNORE INTO cross_research VALUES (?,?,?,?,?,?)",
                (result["signal_id"],result["contract"],result["bar_end"],
                 result["research_cross"],
                 parse_time(observed_at or datetime.now(timezone.utc)).isoformat(),
                 json.dumps(result,ensure_ascii=False)))
        return cur.rowcount==1
    finally:con.close()

def read_status(path,limit=20):
    p=Path(path)
    if not p.is_file():
        return {"version":"0.5.5","research_events":[],"notification_enabled":False,
                "main_contracts_verified":False,"official_close_verified":False}
    con=sqlite3.connect(f"file:{p.resolve()}?mode=ro",uri=True)
    try:
        rows=con.execute("SELECT signal_id,contract,bar_end,direction,observed_at FROM cross_research ORDER BY observed_at DESC LIMIT ?",(min(max(int(limit),1),100),)).fetchall()
        return {"version":"0.5.5","research_events":[dict(zip(
           ("signal_id","contract","bar_end","direction","observed_at"),x)) for x in rows],
           "notification_enabled":False,"main_contracts_verified":False,
           "official_close_verified":False}
    finally:con.close()
