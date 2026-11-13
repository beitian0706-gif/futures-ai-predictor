"""Specific-contract 60m MA144 HISTORICAL research; not realtime or push."""
from __future__ import annotations
import math
import re
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))
CONTRACT_RE = re.compile(r"^[A-Z]{1,3}\d{3,4}$")
REQUIRED_BARS = 145

class Market60mError(ValueError):
    pass

def is_contract(contract):
    return isinstance(contract, str) and CONTRACT_RE.fullmatch(contract.strip().upper()) is not None

def _timestamp(value):
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("T", " ").replace("Z", "+00:00"))
        except ValueError as exc:
            raise Market60mError("60分钟K线时间戳无法解析") from exc
    return dt.replace(tzinfo=CN_TZ) if dt.tzinfo is None else dt.astimezone(CN_TZ)

def normalize_minutes(frame):
    """Reject missing, invalid, duplicate or unordered OHLCV; never impute bars."""
    if frame is None or getattr(frame, "empty", True):
        raise Market60mError("60分钟行情源未返回数据")
    df = frame.copy()
    columns = {str(c).strip().lower(): c for c in df.columns}
    required = ("datetime", "open", "high", "low", "close", "volume")
    if not all(k in columns for k in required):
        raise Market60mError("60分钟K线缺少时间、开高低收或成交量字段")
    result = []
    for _, rec in df.iterrows():
        t = _timestamp(rec[columns["datetime"]])
        try:
            o, h, l, c, v = (float(rec[columns[k]]) for k in required[1:])
        except (TypeError, ValueError) as exc:
            raise Market60mError("60分钟K线存在无法读取的价格或成交量") from exc
        if (not all(math.isfinite(x) for x in (o, h, l, c, v))
                or min(o, h, l, c) <= 0 or h < max(o, l, c)
                or l > min(o, h, c) or v < 0):
            raise Market60mError("60分钟K线存在无效价格或成交量")
        result.append({"datetime": t, "open": o, "high": h, "low": l,
                       "close": c, "volume": v})
    if any(result[i]["datetime"] <= result[i-1]["datetime"]
           for i in range(1, len(result))):
        raise Market60mError("60分钟K线时间重复或未按升序排列")
    if result and result[-1]["datetime"] > datetime.now(CN_TZ) + timedelta(hours=2):
        raise Market60mError("60分钟K线日期异常（未来时间）")
    return result

def evaluate_bars(contract, rows, *, max_cross_pct=3.0, now=None):
    """A signal requires BOTH previous and current 144-close moving averages.

    Provider does not give an independently verified closed-bar flag.
    To avoid interpreting an in-progress candle, the last row is ALWAYS
    excluded. Output is research-only, no realtime notification.
    """
    contract = str(contract).strip().upper()
    if not is_contract(contract):
        raise Market60mError("必须指定具体合约（例如 RB2701），禁止连续合约")
    if not 0 < max_cross_pct <= 100:
        raise Market60mError("穿越幅度阈值必须在0至100之间")
    now = now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)
    if not rows:
        return {"contract": contract, "status": "no_data", "signal": "none",
                "message": "未取得60分钟行情，不能计算MA144"}
    completed = rows[:-1]
    info = {
        "contract": contract, "timeframe": "60m", "source": "AKShare/Sina",
        "source_realtime_verified": False, "status": "insufficient_data",
        "signal": "none", "max_cross_pct": max_cross_pct,
        "provider_bars": len(rows), "usable_bars": len(completed),
        "last_provider_timestamp": rows[-1]["datetime"].isoformat(),
        "bar_policy": "始终排除最后一根K线（可能尚未收盘）；其余历史K线收盘亦未经交易所独立核验",
        "push_enabled": False,
    }
    if len(completed) < REQUIRED_BARS:
        info["message"] = f"排除最后一根后只有{len(completed)}根，MA144穿越需至少{REQUIRED_BARS}根"
        return info
    closes = [r["close"] for r in completed]
    earlier, latest = completed[-2], completed[-1]
    earlier_ma, latest_ma = sum(closes[-145:-1])/144, sum(closes[-144:])/144
    if earlier_ma <= 0 or latest_ma <= 0:
        raise Market60mError("MA144计算异常")
    prev_pct = (earlier["close"]-earlier_ma)/earlier_ma*100
    curr_pct = (latest["close"]-latest_ma)/latest_ma*100
    direction = ("up" if earlier["close"] <= earlier_ma and latest["close"] > latest_ma
                 else "down" if earlier["close"] >= earlier_ma and latest["close"] < latest_ma
                 else "none")
    filtered = direction != "none" and abs(curr_pct) > max_cross_pct
    age_hours = (now.astimezone(CN_TZ)-latest["datetime"]).total_seconds()/3600
    info.update({
        "status": "historical_only" if age_hours >= 0 else "invalid_timestamp",
        "signal": "filtered" if filtered else direction,
        "raw_cross_direction": direction,
        "previous_close": earlier["close"], "previous_ma144": round(earlier_ma, 6),
        "last_close": latest["close"], "ma144": round(latest_ma, 6),
        "previous_distance_pct": round(prev_pct, 4),
        "cross_distance_pct": round(curr_pct, 4),
        "latest_usable_timestamp": latest["datetime"].isoformat(),
        "latest_age_hours": round(age_hours, 2),
        "signal_id": f"{contract}:{latest['datetime'].isoformat()}:{direction}"
            if direction != "none" else None,
        "message": (
            "历史穿越幅度超过过滤阈值，不产生入场提醒" if filtered else
            "历史K线出现MA144上穿；数据尚未实时核验" if direction == "up" else
            "历史K线出现MA144下穿；数据尚未实时核验" if direction == "down" else
            "最近两根可用历史60分钟K线没有MA144收盘穿越"
        )
    })
    return info

def query_sina_60m(contract, *, provider=None):
    if not is_contract(contract):
        raise Market60mError("必须使用具体合约代码（禁止连续合约）")
    if provider is None:
        import akshare as provider
    data = provider.futures_zh_minute_sina(symbol=contract.upper(), period="60")
    result = evaluate_bars(contract, normalize_minutes(data))
    result["retrieved_at"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
    return result
