"""V0.5.4 60m data closing / session evidence diagnostics (research only).

Actual exchange calendars, special trading days, vendor timestamp semantics, and
official settled/finalised bars are NOT obtained by this module. It never
authorises push alerts. The contract-specific schedule is an explicit
*operator-supplied research hypothesis*, not exchange truth.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone, time
import json
import re
from zoneinfo import ZoneInfo

SH=ZoneInfo("Asia/Shanghai")
CONTRACT=re.compile(r"^[A-Z]{1,3}\d{3,4}$")

def sh_time(s):
    if isinstance(s,str):s=datetime.fromisoformat(s.replace("Z","+00:00"))
    if not isinstance(s,datetime) or s.tzinfo is None:raise ValueError("时间戳必须带时区")
    return s.astimezone(SH)

def inspect_bar(*,contract,bar_time,observed_at,prior_bar=None,
                last_bar=None,timestamp_semantics="unknown",expected_end=None,
                exchange_calendar_evidence=False,source_final_evidence=False):
    """Classify observed K-line conservatively; never assert certified closure."""
    if not isinstance(contract,str) or not CONTRACT.fullmatch(contract.upper()):
        raise ValueError("必须为具体到期合约，不接受连续主力合约别名")
    observed=sh_time(observed_at)
    stamp=sh_time(bar_time)
    r={"contract":contract.upper(),"bar_timestamp":stamp.isoformat(),
       "observed_at":observed.isoformat(),"timestamp_semantics":timestamp_semantics,
       "class":"unknown","official_close_verified":False,
       "alert_eligible":False,"evidence":[],"reason":""}
    if stamp>observed:
        r.update(class_="future")
        r["class"]="invalid_future_timestamp";r["reason"]="行情时间戳超前";return r
    if timestamp_semantics not in ("open","close"):
        r["class"]="timestamp_semantics_unknown";r["reason"]="行情源K线时间戳含义未校准";return r
    if expected_end is None:
        r["class"]="session_unmapped";r["reason"]="该合约的交易所分段收盘时刻未建立经核准映射";return r
    end=sh_time(expected_end)
    if end<=stamp and timestamp_semantics=="open":
        r["class"]="invalid_bar_interval";r["reason"]="推测结束时间不晚于开盘标签";return r
    if timestamp_semantics=="close" and end!=stamp:
        r["class"]="bar_end_mismatch";r["reason"]="结束时间与收盘标签不一致";return r
    if observed<end:
        r["class"]="forming";r["reason"]="按研究日历推测尚未结束";return r
    age=(observed-end).total_seconds()
    if age>3*3600:
        r["class"]="stale";r["reason"]="距推测结束时刻超过3小时";return r
    r["evidence"].append("研究日历推测K线时间窗口结束")
    if not exchange_calendar_evidence:
        r["class"]="calendar_unverified";r["reason"]="研究日历非交易所独立确认";return r
    if last_bar is None or prior_bar is None:
        r["class"]="insufficient_snapshots";r["reason"]="缺少同一根K线两次快照";return r
    keys=("open","high","low","close","volume")
    try:
        t1=sh_time(prior_bar["observed_at"]);t2=sh_time(last_bar["observed_at"])
        if t1>=t2 or t2>observed:raise ValueError("快照时间不合法")
        consistent=all(prior_bar[k]==last_bar[k] for k in keys)
    except (KeyError,TypeError,ValueError):
        r["class"]="invalid_snapshots";r["reason"]="快照内容或时间不合法";return r
    if not consistent:
        r["class"]="changing";r["reason"]="K线OHLCV还在改变";return r
    r["evidence"].append("两次独立快照OHLCV不变")
    if not source_final_evidence:
        r["class"]="stable_unverified";r["reason"]="快照稳定不代表行情商或交易所已确认收盘";return r
    r["class"]="candidate_final_not_official"
    r["reason"]="研究证据满足，仍缺交易所正式收盘独立核验"
    return r

def monitor_audit(*,data,now=None):
    """Audit V0.5.3 discovery and V0.5.2 scanning provenance."""
    now=sh_time(now or datetime.now(SH))
    candidates=data.get("main_candidates",[]) if isinstance(data,dict) else []
    scans=data.get("latest_scans",[]) if isinstance(data,dict) else []
    output=[]
    for item in candidates:
        candidate=item.get("candidate")
        stable=bool(item.get("candidate_stable"))
        age=item.get("snapshot_age_minutes")
        try:age=float(age)
        except (TypeError,ValueError):age=None
        problems=[]
        if not stable:problems.append("候选稳定性不足")
        if not item.get("leaders_agree"):problems.append("成交量与持仓量领先合约不同")
        if item.get("roll_change_detected"):problems.append("观察到候选换月，需重新核验")
        if age is None or age<0 or age>20:problems.append("行情快照时间真实性或新鲜度待核查")
        if not item.get("snapshot_timestamp_independently_verified"):
            problems.append("行情快照时间戳未独立核验")
        if not item.get("main_contract_verified"):
            problems.append("交易所主力身份未独立核验")
        related=[x for x in scans if x.get("contract")==candidate]
        if not related:problems.append("没有该候选合约的60分钟历史扫描记录")
        elif not related[0].get("close_verified"):
            problems.append("60分钟K线收盘未独立核验")
        output.append({"product":item.get("product"),"candidate":candidate,
           "stable":stable,"roll_change_detected":bool(item.get("roll_change_detected")),
           "research_checks_pass":len(problems)==0,
           "allowed_for_realtime_alert":False,
           "blockers":problems})
    return {"version":"0.5.4","updated_at":now.isoformat(),
      "main_contract_candidates":output,
      "candidate_count":len(output),
      "official_close_verified":False,
      "notification_enabled":False,"trading_enabled":False,
      "source":"V0.5.2+V0.5.3 research snapshots",
      "warning":"本版本仅诊断行情/候选合约/换月与收盘证据，不具备权威交易所确认或一分钟实时推送"}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--v053",default="/var/lib/futures-ai/main-candidates-v053.json")
    p.add_argument("--output",default="/var/lib/futures-ai/audit-v054.json")
    args=p.parse_args()
    from pathlib import Path
    from monitor_v052 import read_latest
    try:
        c=json.loads(Path(args.v053).read_text(encoding="utf-8")).get("candidates",[])
    except (FileNotFoundError,ValueError,PermissionError):
        c=[]
    # This audit deliberately does not scrape market feeds, trigger signals,
    # modify monitoring watchlist, or claim an official close.
    try:
        scan=read_latest('/var/lib/futures-ai/monitor-v052.sqlite3').get('latest_scans',[])
    except Exception:
        scan=[]
    result=monitor_audit(data={"main_candidates":c,"latest_scans":scan})
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(dest)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()
