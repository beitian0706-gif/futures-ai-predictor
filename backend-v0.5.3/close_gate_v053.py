"""Conservative 60-minute candle close-evidence gate, V0.5.3.

This gate intentionally does NOT claim exchange-certified close.
Bar timestamps differ by vendor, market, day/night and session; no push.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone

CN_TZ=timezone(timedelta(hours=8))
def _aware(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value.replace("Z","+00:00"))
    if not isinstance(value,datetime):raise ValueError("Invalid time")
    if value.tzinfo is None:
        raise ValueError("Timezone information is required")
    return value.astimezone(CN_TZ)

def assess_closed_bar(*,bar_time,observed_at,prior_snapshot=None,current_snapshot=None,
                      timestamp_semantics=None,exchange_calendar_verified=False,
                      min_delay_seconds=15,max_age_minutes=180):
    """Evaluate available evidence without pretending the exchange validates it.

    Two identical snapshots require explicit recorded_at and identical OHLCV.
    Vendor-provided 60m labels alone cannot establish close time.
    """
    bar=_aware(bar_time)
    now=_aware(observed_at)
    age=(now-bar).total_seconds()/60
    result={"bar_time":bar.isoformat(),"observed_at":now.isoformat(),
            "timestamp_semantics":timestamp_semantics or "unknown",
            "exchange_calendar_verified":bool(exchange_calendar_verified),
            "bar_close_verified":False,"notification_allowed":False,
            "status":"pending","reason":"尚未取得独立交易所收盘确认"}
    if age<0:
        result.update(status="future_timestamp",reason="行情K线时间晚于扫描时间")
        return result
    if age>max_age_minutes:
        result.update(status="stale",reason="行情已过期")
        return result
    if timestamp_semantics not in ("open","close"):
        result.update(status="timestamp_semantics_unknown",reason="未核验行情源时间戳是开盘还是收盘")
        return result
    if not exchange_calendar_verified:
        result.update(status="exchange_calendar_unverified",reason="交易所各品种交易时段与特殊日期未经独立核验")
        return result
    # Even if a caller supplied both policy assertions, no complete trading
    # session calendar/official close confirmation exists in V0.5.3.
    # Stable snapshots are diagnostic only, not independent close verification.
    if prior_snapshot is None or current_snapshot is None:
        result.update(status="needs_two_snapshots",reason="缺少两次采样")
        return result
    fields=("open","high","low","close","volume")
    try:
        ptime=_aware(prior_snapshot["observed_at"])
        ctime=_aware(current_snapshot["observed_at"])
        same=all(prior_snapshot[f]==current_snapshot[f] for f in fields)
    except (KeyError,ValueError,TypeError):
        result.update(status="invalid_snapshot",reason="采样字段缺失")
        return result
    if not ptime < ctime <= now or (ctime-ptime).total_seconds()<min_delay_seconds:
        result.update(status="invalid_sampling_interval",reason="采样时间顺序或间隔不足")
        return result
    if not same:
        result.update(status="snapshot_changed",reason="K线数值仍有变化")
        return result
    result.update(status="stable_not_exchange_verified",
                  reason="两次采样稳定，但仍未获得交易所官方收盘确认")
    return result

def close_policy_summary():
    return {"exchange_calendar_verified":False,
            "provider_timestamp_semantics_verified":False,
            "closed_bar_verified":False,"notification_enabled":False,
            "status":"research_only",
            "checks":["严格时区与时间戳检查","数据新鲜度","可选双快照一致性",
                      "待实现交易所节假日/夜盘分段/正式收盘核验"],
            "warning":"不能从新浪K线时间戳和固定60分钟推断已正式收盘；不允许实盘推送"}
