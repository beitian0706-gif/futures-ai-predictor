"""Offline CLI: evaluate operator-supplied historical 60m OHLCV CSV.

Never downloads speculative contract bars or starts trades/push.
Requires explicit, instrument-specific multiplier, tick, margin and fees.
"""
import argparse
import csv
import json
import os
from pathlib import Path
from strategy_v056 import Settings, compare_strategies

def main():
    p=argparse.ArgumentParser(description="V0.5.6 historical research only")
    p.add_argument("--csv",required=True)
    p.add_argument("--contract",required=True)
    p.add_argument("--multiplier",type=float,required=True)
    p.add_argument("--tick",type=float,required=True)
    p.add_argument("--margin",type=float,required=True)
    p.add_argument("--fee",type=float,required=True,help="one-way fee per lot in CNY")
    p.add_argument("--capital",type=float,default=100000)
    p.add_argument("--risk-percent",type=float,default=.5)
    p.add_argument("--slippage-ticks",type=float,default=1)
    p.add_argument("--atr-stop",type=float,default=2)
    p.add_argument("--trail-atr",type=float,default=3)
    p.add_argument("--partial-fraction",type=float,default=.5)
    p.add_argument("--disable-daily-filter",action="store_true",
                   help="research without daily-trend confirmation; not a trade recommendation")
    p.add_argument("--out",default="/var/lib/futures-ai/strategy-v056.json")
    args=p.parse_args()
    with open(args.csv,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        required={"end_time","open","high","low","close"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            p.error("CSV must include end_time,open,high,low,close; optional daily_trend")
        rows=[]
        for row in reader:
            rows.append({**{k:row[k] for k in required},
                "daily_trend":row.get("daily_trend") or None})
            if len(rows)>20000:p.error("CSV exceeds 20000 bars")
    settings=Settings(initial_equity=args.capital,risk_percent=args.risk_percent,
      contract_multiplier=args.multiplier,tick_size=args.tick,
      fee_per_lot_side=args.fee,margin_per_lot=args.margin,
      slippage_ticks_side=args.slippage_ticks,atr_stop_multiple=args.atr_stop,
      trail_atr_multiple=args.trail_atr,partial_fraction=args.partial_fraction,
      daily_filter=not args.disable_daily_filter)
    comparison=compare_strategies(args.contract,rows,settings)
    comparison["parameters"]={k:getattr(settings,k) for k in settings.__dataclass_fields__}
    comparison["csv_record_count"]=len(rows)
    comparison["data_source"]="operator_supplied_csv_unverified"
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".new")
    tmp.write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,dest)
    print(json.dumps({"version":"0.5.6","contract":comparison["contract"],
         "comparisons":len(comparison["comparisons"]),
         "training_bars":comparison["train_bars"],"holdout_bars":comparison["test_bars"],
         "report":str(dest),"research_only":True},ensure_ascii=False))
if __name__=="__main__":main()
