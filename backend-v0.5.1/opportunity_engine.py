"""Independent, deterministic entry-opportunity research engine (NOT an order system).

Consumes historical *specific-contract* daily and 60m OHLCV bars.
A watch candidate is not a verified entry alert. This source does not know
exchange-confirmed bar closure or the real main-contract mapping.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))
from ma144_60m import is_contract, normalize_minutes, Market60mError

def _sma(vals, length):
    return sum(vals[-length:]) / length

def _atr(bars, length=14):
    if len(bars) < length + 1:
        return None
    ranges = []
    for before, bar in zip(bars[:-1], bars[1:]):
        ranges.append(max(bar["high"]-bar["low"],
                          abs(bar["high"]-before["close"]),
                          abs(bar["low"]-before["close"])))
    avg = sum(ranges[:length]) / length
    for tr in ranges[length:]:
        avg = (avg*(length-1)+tr)/length
    return avg

def _base(contract, *, message, status="watch", reasons=None):
    return {
        "contract": contract, "status": status, "status_label": {
            "watch":"观察中", "candidate":"候选机会",
            "ready":"条件满足", "invalid":"机会失效"}.get(status,"观察中"),
        "message": message, "reasons": reasons or [],
        "data_policy": "历史日线和60分钟K线研究，非交易所校验的实时信号",
        "entry_alert_enabled": False, "order_enabled": False,
        "main_contract_verified": False, "closed_bar_verified": False,
        "risk_reward_verified": False
    }

def evaluate_opportunity(contract, daily, hourly, *,
                         main_contract_verified=False,
                         closed_bar_verified=False,
                         data_fresh_verified=False,
                         now=None, max_age_hours=48,
                         cross_distance_cap_pct=1.0):
    """Independently evaluate structure/direction; ALWAYS research-only.

    hourly records include provider's most recent row which is intentionally
    excluded. Data presence or a positive score cannot authorize a real alert.
    """
    code = str(contract).strip().upper()
    if not is_contract(code):
        raise Market60mError("机会引擎只接受具体合约，不接受连续合约")
    if not isinstance(daily,list) or not isinstance(hourly,list):
        raise Market60mError("日线及60分钟K线必须为列表")
    if len(daily)<61 or len(hourly)<146:
        r=_base(code,message="数据不足：需要至少61根日线、146根来源60分钟K线",reasons=["数据不足"])
        r.update({"daily_bars":len(daily),"hourly_provider_bars":len(hourly)})
        return r

    # Caller normalizes to standard records with datetime and OHLCV.
    for label,arr in (("日线",daily),("60分钟",hourly)):
        for i,bar in enumerate(arr):
            if any(k not in bar for k in ("datetime","open","high","low","close","volume")):
                raise Market60mError(label+"缺少K线字段")
            if any(not isinstance(bar[k],(int,float)) or not math.isfinite(bar[k])
                   for k in ("open","high","low","close","volume")):
                raise Market60mError(label+"包含非数值字段")
            if min(bar["open"],bar["high"],bar["low"],bar["close"])<=0 or bar["volume"]<0:
                raise Market60mError(label+"包含非法价格/成交量")
            if bar["high"]<max(bar["open"],bar["close"]) or bar["low"]>min(bar["open"],bar["close"]):
                raise Market60mError(label+"高低价不匹配")
            if i and bar["datetime"]<=arr[i-1]["datetime"]:
                raise Market60mError(label+"时间戳重复或倒序")

    completed=hourly[:-1]
    daily_closes=[b["close"] for b in daily]
    hourly_closes=[b["close"] for b in completed]
    d20=_sma(daily_closes,20)
    d60=_sma(daily_closes,60)
    d20_prev=sum(daily_closes[-21:-1])/20
    h_ma=_sma(hourly_closes,144)
    h_prev=sum(hourly_closes[-145:-1])/144
    last_hour=completed[-1]
    prev_hour=completed[-2]
    daily_price=daily_closes[-1]
    positive=daily_price>d60 and d20>d20_prev
    negative=daily_price<d60 and d20<d20_prev
    direction="long" if positive else "short" if negative else "mixed"
    crossing_up=prev_hour["close"]<=h_prev and last_hour["close"]>h_ma
    crossing_down=prev_hour["close"]>=h_prev and last_hour["close"]<h_ma
    cross="up" if crossing_up else "down" if crossing_down else "none"
    distance=abs((last_hour["close"]-h_ma)/h_ma)*100

    now=now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now=now.replace(tzinfo=CN_TZ)
    dt=last_hour["datetime"]
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=CN_TZ)
    age=(now.astimezone(CN_TZ)-dt.astimezone(CN_TZ)).total_seconds()/3600

    direction_matches=(direction=="long" and cross=="up") or (direction=="short" and cross=="down")
    atr=_atr(completed)
    notes=[]
    if direction=="mixed":
        notes.append("日线MA20方向与MA60位置不构成一致趋势")
    else:
        notes.append("日线趋势过滤为"+("偏多" if positive else "偏空"))
    if cross=="none":
        notes.append("最近两根可用60分钟K线未发生MA144穿越")
    else:
        notes.append("最近两根可用历史K线出现"+("上穿" if cross=="up" else "下穿"))
    if not direction_matches and cross!="none":
        notes.append("60分钟穿越方向与日线过滤不一致")
    if distance>cross_distance_cap_pct and cross!="none":
        notes.append("穿越幅度超出初始阈值")
    if age<0 or age>max_age_hours:
        notes.append("可用K线时间异常或数据过旧")
    if not main_contract_verified:
        notes.append("未核实当前实际主力合约")
    if not closed_bar_verified or not data_fresh_verified:
        notes.append("尚未取得独立收盘与时效核验")
    # Structural stop needs a genuine setup pivot; never manufacture it from
    # a moving average or an uncalibrated scenario range.
    notes.append("缺少已验证的结构止损、目标位置和风险收益比")

    good=(direction_matches and distance<=cross_distance_cap_pct and 0<=age<=max_age_hours)
    status="candidate" if good else "watch"
    msg=("存在历史穿越候选；等待实时收盘、主力身份及风险收益核验"
         if good else "条件尚未齐备，继续观察")
    response=_base(code,message=msg,status=status,reasons=notes)
    response.update({
        "strategy":"A-收盘穿越", "timeframe":"daily + 60m",
        "daily_trend":direction,"historical_cross":cross,
        "ma20":round(d20,4),"ma60":round(d60,4),"ma144":round(h_ma,4),
        "latest_usable_close":last_hour["close"],
        "latest_usable_bar":dt.isoformat(),
        "bar_age_hours":round(age,2),
        "cross_distance_pct":round(distance,4),
        "atr14_60m":round(atr,4) if atr is not None else None,
        "daily_bars":len(daily), "hourly_provider_bars":len(hourly),
        "usable_hourly_bars":len(completed),
        "entry_conditions_met":False,
        "risk_reward":None,
        "source_realtime_verified":False,
        "candidate_reason_code":("CROSS_TREND_MATCH" if good else "NO_QUALIFIED_SETUP")
    })
    return response

def query_opportunity(contract, *, provider=None):
    if not is_contract(contract):
        raise Market60mError("仅支持具体合约")
    if provider is None:
        import akshare as provider
    d=provider.futures_zh_daily_sina(symbol=contract.upper())
    h=provider.futures_zh_minute_sina(symbol=contract.upper(),period="60")
    daily=normalize_daily(d)
    hourly=normalize_minutes(h)
    result=evaluate_opportunity(contract,daily,hourly)
    result["source"]="AKShare/Sina"
    result["retrieved_at"]=datetime.now(CN_TZ).isoformat(timespec="seconds")
    return result

def normalize_daily(frame):
    """AKShare daily commonly uses date/open/high/low/close/volume columns."""
    if frame is None or getattr(frame,"empty",True):
        raise Market60mError("未取得历史日线")
    cols={str(c).strip().lower():c for c in frame.columns}
    required=("date","open","high","low","close","volume")
    if any(x not in cols for x in required):
        raise Market60mError("历史日线缺少必需字段")
    # normalize_minutes expects datetime, so create a detached renamed copy
    frame=frame.rename(columns={cols["date"]:"datetime"})
    return normalize_minutes(frame)
