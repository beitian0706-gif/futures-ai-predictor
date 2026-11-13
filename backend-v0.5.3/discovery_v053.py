"""V0.5.3 discovery of SPECIFIC future contracts from AKShare/Sina snapshots.

This is a research-only provisional main-contract selector. Never label a
source snapshot "exchange-verified"; never silently substitute continuous
contracts. A stable candidate is not a verified actual main contract.
"""
from __future__ import annotations
import json
import math
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from main_candidates_v052 import select_main_candidates
from monitor_v052 import validate_watchlist

CN_TZ=timezone(timedelta(hours=8))
CODE_RE=re.compile(r"^([A-Z]{1,3})(\d{3,4})$")
COLUMN_CHOICES={
 "contract":("symbol","代码","合约代码","contract"),
 "volume":("volume","成交量"),
 "open_interest":("position","hold","持仓量","open_interest"),
}

def _record(row, names):
    for name in names:
        if name in row:
            return row[name]
    raise ValueError("行情快照字段缺失")

def normalized_snapshot(frame, *, product):
    """Strict column mapping and product match; no fabricated zeros."""
    if frame is None or getattr(frame,"empty",True):
        raise ValueError("行情快照为空")
    rows=[]
    for rec in frame.to_dict(orient="records"):
        code=str(_record(rec,COLUMN_CHOICES["contract"])).strip().upper()
        match=CODE_RE.fullmatch(code)
        if not match or match.group(1)!=product.upper():
            continue
        # No aliases RB0 / RB888 / RB999; only genuine expiry-length formats.
        digits=match.group(2)
        if digits in ("000","888","999","0000","8888","9999"):
            continue
        try:
            volume=float(_record(rec,COLUMN_CHOICES["volume"]))
            oi=float(_record(rec,COLUMN_CHOICES["open_interest"]))
        except (TypeError,ValueError) as exc:
            raise ValueError("行情快照成交量或持仓量无法解析") from exc
        if not all(math.isfinite(v) and v>=0 for v in (volume,oi)):
            raise ValueError("成交量、持仓量不合法")
        rows.append({"contract":code,"volume":volume,"open_interest":oi})
    if not rows:
        raise ValueError("行情源未提供该品种具体合约")
    return rows

def discover_candidates(products, *, provider=None, now=None):
    """Queries product-specific snapshots. Results are never auto-verified."""
    if not isinstance(products,list) or not 1<=len(products)<=20:
        raise ValueError("需配置1至20个品种")
    if provider is None:
        import akshare as provider
    now=now or datetime.now(CN_TZ)
    out=[]
    for cfg in products:
        name=cfg.get("name") if isinstance(cfg,dict) else None
        code=cfg.get("product") if isinstance(cfg,dict) else None
        if not isinstance(name,str) or not name.strip() or not isinstance(code,str) or not re.fullmatch(r"[A-Za-z]{1,3}",code):
            raise ValueError("品种必须包含有效中文名称及英文字母代码")
        frame=provider.futures_zh_realtime(symbol=name.strip())
        records=normalized_snapshot(frame,product=code.strip().upper())
        rank=select_main_candidates(records,asof=now.isoformat(),now=now)
        if len(rank)!=1:
            raise ValueError("品种快照与期货代码对应异常")
        item=rank[0]
        item.update({"product_name":name.strip(),"source":"AKShare/Sina futures_zh_realtime",
            "snapshot_at":now.isoformat(),"snapshot_timestamp_independently_verified":False,
            "contract_count":len(records)})
        out.append(item)
    return out

def reconcile_candidates(prior, current, *, min_stable_snapshots=2):
    """Evidence from consecutive polls; switching is observed but never traded."""
    known={x["product"]:x for x in (prior or [])}
    answer=[]
    for item in current:
        old=known.get(item["product"],{})
        same=(old.get("candidate")==item.get("candidate") and
              old.get("leaders_agree") and item.get("leaders_agree") and
              item.get("snapshot_fresh"))
        count=int(old.get("stable_count",0))+1 if same else (1 if item.get("leaders_agree") else 0)
        entry={**item,"stable_count":count,
               "candidate_stable":count>=min_stable_snapshots,
               "roll_change_detected":bool(old.get("candidate") and old.get("candidate")!=item.get("candidate")),
               "main_contract_verified":False,
               "allowed_for_realtime_alert":False}
        answer.append(entry)
    return answer

def safe_write_json(path,data):
    """Write a research-only status snapshot atomically."""
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(p)

def run_discovery(config_path,status_path,*,provider=None,now=None):
    config=json.loads(Path(config_path).read_text(encoding="utf-8"))
    products=config.get("products",[]) if isinstance(config,dict) else None
    current=discover_candidates(products,provider=provider,now=now)
    try:
        prior=json.loads(Path(status_path).read_text(encoding="utf-8")).get("candidates",[])
    except (FileNotFoundError,ValueError,TypeError):
        prior=[]
    results=reconcile_candidates(prior,current)
    safe_write_json(status_path,{"candidates":results,"updated_at":datetime.now(CN_TZ).isoformat(),
         "source":"AKShare/Sina","main_contracts_verified":False,"notification_enabled":False,
         "warning":"仅为自动发现的主力候选，尚未独立核验交易所主力身份、快照时间戳与换月规则"})
    return results

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="/etc/futures-ai/v053_products.json")
    p.add_argument("--status",default="/var/lib/futures-ai/main-candidates-v053.json")
    a=p.parse_args()
    print(json.dumps(run_discovery(a.config,a.status),ensure_ascii=False))

if __name__=="__main__":
    main()
