"""Main-contract *candidate* ranking from explicit snapshot metadata.

No automatic source is implicitly authoritative. Do NOT label as "verified"
until exchange-specific requirements, roll calendar and timestamp are audited.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from ma144_60m import is_contract

CN_TZ=timezone(timedelta(hours=8))

def select_main_candidates(rows, *, asof, now=None, max_age_minutes=60):
    if not isinstance(rows,list):
        raise ValueError("snapshots must be a list")
    now=now or datetime.now(CN_TZ)
    if now.tzinfo is None:now=now.replace(tzinfo=CN_TZ)
    try:
        stamp=datetime.fromisoformat(asof)
    except (TypeError,ValueError) as exc:
        raise ValueError("invalid snapshot time") from exc
    if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=CN_TZ)
    age=(now-stamp).total_seconds()/60
    fresh=0<=age<=max_age_minutes
    groups={}
    for row in rows:
        if not isinstance(row,dict):raise ValueError("snapshot item must be an object")
        code=str(row.get("contract","")).strip().upper()
        if not is_contract(code):raise ValueError("only specific contracts allowed")
        volume=row.get("volume")
        oi=row.get("open_interest")
        if (not isinstance(volume,(int,float)) or not isinstance(oi,(int,float))
                or not 0<=volume<1e15 or not 0<=oi<1e15):
            raise ValueError("invalid volume or open interest")
        # Derive commodity prefix from concrete contract.
        product=code.rstrip("0123456789")
        groups.setdefault(product,[]).append((code,float(volume),float(oi)))
    result=[]
    for product,items in sorted(groups.items()):
        if len({a[0] for a in items})!=len(items):
            raise ValueError("duplicate contracts in snapshot")
        # Many Chinese products switch main contract according to OI,
        # but no universal official rule: give candidates rather than proof.
        by_volume=sorted(items,key=lambda x:(-x[1],x[0]))[0][0]
        by_oi=sorted(items,key=lambda x:(-x[2],x[0]))[0][0]
        aligned=by_volume==by_oi
        result.append({"product":product,"candidate":by_oi,"volume_leader":by_volume,
          "open_interest_leader":by_oi,"leaders_agree":aligned,
          "snapshot_fresh":fresh,"snapshot_age_minutes":round(age,1),
          "main_contract_verified":False,
          "status":"候选一致，待交易所及换月规则核验" if aligned and fresh else
                   "候选分歧或数据过期，不可认定主力",
          "warning":"仅按照导入快照排名，不能自动视为交易所确认主力"})
    return result
