"""Explainable trend detection for violation counts (Phase 3.2). Uses standard library only."""

import statistics
from typing import Any

def compute_trends(
    history: list[dict[str, object]],
    window: int = 14,
    anomaly_lookback: int | None = None,
    anomaly_z: float = 2.5,
    flat_slope_threshold: float = 0.05,
) -> dict[str, Any]:
    """
    Compute explainable trend metrics from a time-series of counts.

    - history: list of {"ts": iso_str, "count": int} (same shape as /predict/timeseries).
    - Uses only the last (2*window) points for WoW/period-over-period.
    - If history has < window points, returns insufficient_data=True and safe defaults.
    """
    lookback = anomaly_lookback if anomaly_lookback is not None else window
    n = len(history)
    points_used = min(n, 2 * window) if n >= window else n

    if n < window:
        return {
            "window": window,
            "recent_mean": 0.0,
            "prev_mean": 0.0,
            "pct_change": 0.0,
            "slope": 0.0,
            "trend_direction": "flat",
            "volatility": 0.0,
            "anomalies": [],
            "insufficient_data": True,
            "points_used": n,
        }

    counts = [int(h["count"]) for h in history]
    # Work on last 2*window points
    use = counts[-(2 * window) :] if n >= 2 * window else counts
    n_use = len(use)
    # Last window (recent), previous window (prev)
    recent = use[-window:] if n_use >= window else use
    prev = use[-2 * window : -window] if n_use >= 2 * window else (use[: -window] if len(use) > len(recent) else [])

    recent_mean = statistics.mean(recent) if recent else 0.0
    prev_mean = statistics.mean(prev) if prev else 0.0

    # pct_change
    denom = max(prev_mean, 1e-9)
    prev_mean_zero = prev_mean == 0 and recent_mean > 0
    if prev_mean_zero:
        pct_change = 100.0
    else:
        pct_change = ((recent_mean - prev_mean) / denom) * 100.0

    # Slope: simple linear regression on last window points (x=0..n-1, y=counts)
    # slope = cov(x,y)/var(x)
    x = list(range(len(recent)))
    y = recent
    n_pt = len(x)
    if n_pt < 2:
        slope = 0.0
    else:
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n_pt)) / n_pt
        var_x = statistics.pvariance(x) if n_pt >= 2 else 0.0
        slope = cov / var_x if var_x != 0 else 0.0

    if slope > flat_slope_threshold:
        trend_direction = "up"
    elif slope < -flat_slope_threshold:
        trend_direction = "down"
    else:
        trend_direction = "flat"

    # Volatility: std dev of last window counts
    if len(recent) < 2:
        volatility = 0.0
    else:
        try:
            volatility = statistics.pstdev(recent)
        except statistics.StatisticsError:
            volatility = 0.0

    # Anomalies: mean/std on last anomaly_lookback counts; z for last min(window, 10) points
    ref = use[-lookback:] if len(use) >= lookback else use
    if len(ref) < 2:
        anomalies_list: list[dict[str, Any]] = []
    else:
        try:
            ref_mean = statistics.mean(ref)
            ref_std = statistics.pstdev(ref)
        except statistics.StatisticsError:
            ref_std = 0.0
            ref_mean = 0.0
        if ref_std == 0:
            anomalies_list = []
        else:
            num_tail = min(window, 10)
            anomalies_list = []
            for j in range(num_tail):
                idx = n - num_tail + j
                if idx < 0:
                    continue
                c = counts[idx]
                z = (c - ref_mean) / ref_std
                if abs(z) >= anomaly_z:
                    ts_str = str(history[idx]["ts"])
                    anomalies_list.append({"ts": ts_str, "count": c, "z": round(z, 4)})

    result: dict[str, Any] = {
        "window": window,
        "recent_mean": round(recent_mean, 4),
        "prev_mean": round(prev_mean, 4),
        "pct_change": round(pct_change, 4),
        "slope": round(slope, 6),
        "trend_direction": trend_direction,
        "volatility": round(volatility, 4),
        "anomalies": anomalies_list,
        "insufficient_data": False,
        "points_used": points_used,
    }
    if prev_mean_zero:
        result["prev_mean_zero"] = True
    return result
