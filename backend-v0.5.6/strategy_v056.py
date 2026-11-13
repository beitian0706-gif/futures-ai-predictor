"""V0.5.6 historical A/B/C opportunity and exit research (NOT trading).

Research assumes complete historical OHLC 60m rows supplied in chronological
order. Does not verify vendor bars, authentic main contracts, holiday session
boundaries, fees, slippage or live closed-bar evidence. Never generates orders,
notifications or real-time entries. Strategy decisions at bar i close execute
at next bar open, with stop-first intrabar ambiguity handling.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import floor, isfinite
import re

SYMBOL = re.compile(r"^[A-Z]{1,3}\d{3,4}$")
@dataclass(frozen=True)
class Settings:
    initial_equity: float = 100000.0
    risk_percent: float = 0.5
    contract_multiplier: float = 10.0
    tick_size: float = 1.0
    fee_per_lot_side: float = 3.0
    slippage_ticks_side: float = 1.0
    atr_stop_multiple: float = 2.0
    trail_atr_multiple: float = 3.0
    reward_multiple: float = 2.0
    partial_fraction: float = 0.5
    margin_per_lot: float = 12000.0
    daily_filter: bool = True
    max_lots: int = 100
    def validate(self):
        for key in ("initial_equity","contract_multiplier","tick_size","atr_stop_multiple",
                    "trail_atr_multiple","reward_multiple","margin_per_lot"):
            val=getattr(self,key)
            if not isfinite(val) or val<=0:raise ValueError("invalid "+key)
        for key in ("fee_per_lot_side","slippage_ticks_side"):
            val=getattr(self,key)
            if not isfinite(val) or val<0:raise ValueError("invalid "+key)
        if not (0<self.risk_percent<=2):raise ValueError("risk_percent must be between 0 and 2")
        if not (0<=self.partial_fraction<=1):raise ValueError("invalid partial_fraction")
        if not (1<=self.max_lots<=100000):raise ValueError("invalid max_lots")

def validate_bars(rows):
    if not isinstance(rows,list) or len(rows)<170 or len(rows)>20000:
        raise ValueError("requires 170-20000 historical 60m OHLC bars")
    parsed=[];prior=None
    for r in rows:
        if not isinstance(r,dict):raise ValueError("bar must be object")
        ts=datetime.fromisoformat(str(r["end_time"]).replace("Z","+00:00"))
        if ts.tzinfo is None or (prior is not None and ts<=prior):
            raise ValueError("timestamps must be zoned and strictly increasing")
        prior=ts
        o,h,l,c=(float(r[k]) for k in ("open","high","low","close"))
        if not all(isfinite(x) and x>0 for x in (o,h,l,c)) or l>min(o,c) or h<max(o,c):
            raise ValueError("invalid OHLC")
        trend=r.get("daily_trend")
        if trend is not None and trend not in ("up","down","neutral"):
            raise ValueError("invalid daily trend")
        parsed.append({"end_time":ts.isoformat(),"open":o,"high":h,"low":l,"close":c,
                       "daily_trend":trend})
    return parsed

def indicators(b):
    close=[x["close"] for x in b]
    tr=[b[0]["high"]-b[0]["low"]]
    for i in range(1,len(b)):
        x=b[i];pc=close[i-1]
        tr.append(max(x["high"]-x["low"],abs(x["high"]-pc),abs(x["low"]-pc)))
    atr=[None]*len(b)
    ma144=[None]*len(b)
    for i in range(13,len(b)):
        atr[i]=sum(tr[i-13:i+1])/14
    for i in range(143,len(b)):
        ma144[i]=sum(close[i-143:i+1])/144
    return atr,ma144

def classify(b,atr,ma,i):
    """Research A first MA144 crossing; B pullback; C prior-ten-bar breakout.

    A/B/C are mutually exclusive with B/C checked first; each is only a
    candidate, not verified trade recommendation.
    """
    if i<154:return None
    prev=b[i-1]["close"]-ma[i-1]
    curr=b[i]["close"]-ma[i]
    if prev<=0 and curr>0:return ("A","long")
    if prev>=0 and curr<0:return ("A","short")
    for side in ("long","short"):
        sign=1 if side=="long" else -1
        # B: MA144 cross happened in prior 6 bars; close on correct side,
        # prior candle touched MA within half ATR, now confirms away.
        recent=False
        for j in range(i-6,i):
            if j<144:continue
            x=b[j-1]["close"]-ma[j-1]
            y=b[j]["close"]-ma[j]
            if sign*x<=0 and sign*y>0:recent=True
        if recent and sign*curr>0:
            p=b[i-1]
            if (abs(p["low"]-ma[i-1])<=.5*atr[i-1] if sign==1
                else abs(p["high"]-ma[i-1])<=.5*atr[i-1]):
                if sign*(b[i]["close"]-b[i-1]["close"])>0:
                    return ("B",side)
        # C breakout with MA orientation and MA slope confirmation
        if sign*curr>0 and sign*(ma[i]-ma[i-5])>0:
            level=(max(x["high"] for x in b[i-10:i]) if sign==1
                   else min(x["low"] for x in b[i-10:i]))
            if sign*(b[i]["close"]-level)>0:return ("C",side)
    return None

def compatible(side,trend):
    return trend == ("up" if side=="long" else "down")

def run_research(contract,raw,settings=None,*,entry_type="B",exit_style="partial_trail"):
    """One contract; one method. No retrospective continuous main stitching."""
    if not isinstance(contract,str) or not SYMBOL.fullmatch(contract.upper()):
        raise ValueError("concrete futures contract required")
    if entry_type not in ("A","B","C"):raise ValueError("invalid entry type")
    if exit_style not in ("partial_trail","full_trail","fixed_2r"):
        raise ValueError("invalid exit style")
    p=settings or Settings()
    p.validate()
    b=validate_bars(raw)
    atr,ma=indicators(b)
    equity=p.initial_equity
    peak=equity;drawdown=0.0
    trades=[];position=None;pending=None
    blocked={"trend_or_missing":0,"zero_lot":0,"insufficient_margin":0,"unclear_stop":0}
    point=p.contract_multiplier
    def fill_price(price,side,is_entry):
        # adversarial slippage always worsens fill
        sign=1 if side=="long" else -1
        return price+sign*p.slippage_ticks_side*p.tick_size*(1 if is_entry else -1)
    def exit_lots(pos,lot_count,price,reason,time):
        nonlocal equity,peak,drawdown
        if lot_count<=0:return
        px=fill_price(price,pos["side"],False)
        sign=1 if pos["side"]=="long" else -1
        pnl=(px-pos["entry"])*sign*point*lot_count-p.fee_per_lot_side*lot_count
        equity+=pnl
        pos["remaining"]-=lot_count
        pos["pnl"]+=pnl
        pos["exits"].append({"time":time,"price":round(px,6),
                             "lots":lot_count,"reason":reason})
        peak=max(peak,equity)
        drawdown=max(drawdown,(peak-equity)/peak)
    for i in range(154,len(b)):
        x=b[i]; prior=b[i-1]
        if pending and position is None:
            typ,side,decision_i=pending
            # Fill NEXT bar open; no peeking at this bar to size trade.
            entry=fill_price(x["open"],side,True)
            stop_gap=max(p.atr_stop_multiple*atr[decision_i],
                         abs(b[decision_i]["close"]-ma[decision_i]))
            # Stop distance measured from actual (slipped) fill.
            risk_per_lot=stop_gap*point+2*p.fee_per_lot_side+2*p.slippage_ticks_side*p.tick_size*point
            lots=min(p.max_lots,floor((equity*p.risk_percent/100)/risk_per_lot))
            lots=min(lots,floor(equity/p.margin_per_lot))
            if lots<=0:
                blocked["zero_lot"]+=1
            else:
                sign=1 if side=="long" else -1
                position={"entry_time":x["end_time"],"entry_index":i,"decision_bar":b[decision_i]["end_time"],
                          "type":typ,"side":side,"entry":entry,
                          "initial_stop":entry-sign*stop_gap,"stop":entry-sign*stop_gap,
                          "target":entry+sign*p.reward_multiple*stop_gap,
                          "risk_per_lot":risk_per_lot,"lots":lots,"remaining":lots,
                          "partial_done":False,"pnl":-p.fee_per_lot_side*lots,
                          "exits":[]}
                equity-=p.fee_per_lot_side*lots
            pending=None
        if position:
            pos=position
            sign=1 if pos["side"]=="long" else -1
            # Conservative ambiguity handling: stop-first, even if target touched.
            stopped=(x["low"]<=pos["stop"] if sign==1 else x["high"]>=pos["stop"])
            if stopped:
                gap_stop=(min(x["open"],pos["stop"]) if sign==1
                          else max(x["open"],pos["stop"]))
                exit_lots(pos,pos["remaining"],gap_stop,"stop",x["end_time"])
            else:
                target_hit=(x["high"]>=pos["target"] if sign==1 else x["low"]<=pos["target"])
                if target_hit and not pos["partial_done"]:
                    if exit_style=="fixed_2r":
                        exit_lots(pos,pos["remaining"],pos["target"],"2r_fixed",x["end_time"])
                    elif exit_style=="partial_trail":
                        cut=min(pos["remaining"],max(1,floor(pos["lots"]*p.partial_fraction))) if p.partial_fraction>0 else 0
                        exit_lots(pos,cut,pos["target"],"2r_partial",x["end_time"])
                    pos["partial_done"]=True
                if pos["remaining"] and exit_style in ("partial_trail","full_trail"):
                    # trailing based only on closed-bar data, effective NEXT bar
                    pos["stop"]=max(pos["stop"],x["close"]-p.trail_atr_multiple*atr[i]) if sign==1 else min(pos["stop"],x["close"]+p.trail_atr_multiple*atr[i])
            if pos["remaining"]==0:
                pos["r_net"]=pos["pnl"]/(pos["lots"]*pos["risk_per_lot"])
                trades.append(pos);position=None
        if position is None and pending is None and i<len(b)-1:
            signal=classify(b,atr,ma,i)
            if signal and signal[0]==entry_type:
                typ,side=signal
                if p.daily_filter and not compatible(side,x["daily_trend"]):
                    blocked["trend_or_missing"]+=1
                else:pending=(typ,side,i)
    if position:
        # research evaluation marks open trade to last historical close,
        # explicitly not a real fill; excluded from trade metrics.
        position["mark_to_market"]=b[-1]["close"]
    completed=len(trades)
    wins=sum(t["pnl"]>0 for t in trades)
    profits=sum(max(0,t["pnl"]) for t in trades)
    losses=-sum(min(0,t["pnl"]) for t in trades)
    return {"version":"0.5.6","contract":contract.upper(),
       "entry_type":entry_type,"exit_style":exit_style,"timeframe":"60m",
       "bars":len(b),"trades":completed,"wins":wins,
       "win_rate":round(wins/completed,5) if completed else None,
       "net_pnl":round(sum(t["pnl"] for t in trades),2),
       "ending_cash":round(equity,2),
       "max_realized_drawdown_pct":round(100*drawdown,3),
       "avg_r":round(sum(t["r_net"] for t in trades)/completed,4) if completed else None,
       "profit_factor":round(profits/losses,4) if losses else (None if not profits else "unbounded"),
       "blocked":blocked,"open_position":position is not None,
       "trade_log":trades[-100:],
       "provenance":"user-supplied historical OHLC; futures roll and exchange sessions not verified",
       "research_only":True,"live_signal":False,
       "push_enabled":False,"order_enabled":False,
       "limitations":["单合约独立回测，未验证跨合约主力换月连续性",
        "日线方向必须由信号当时已知数据提供；不能使用未来日线收盘",
        "成交假定次根开盘；跳空采取不利成交，止盈止损同根先算止损",
        "最大回撤仅按已实现权益估计，未纳入持仓浮动回撤",
        "手续费、滑点、保证金与合约乘数为研究参数，必须逐品种核实",
        "尚未接入实盘行情、权威收盘确认或可靠手机通知"]}

def compare_strategies(contract,bars,p=None):
    return {"version":"0.5.6","contract":contract.upper(),"research_only":True,
      "comparisons":[{k:v for k,v in run_research(contract,bars,p,entry_type=a,exit_style=e).items()
                      if k not in ("trade_log","limitations")}
                    for a in ("A","B","C")
                    for e in ("fixed_2r","partial_trail","full_trail")],
      "warning":"九组原型参数同历史样本的比较，可能过拟合；需要滚动样本外验证。"}
