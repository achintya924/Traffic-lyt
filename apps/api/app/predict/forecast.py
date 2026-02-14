"""Simple, explainable forecasting for violation counts (Phase 3.1)."""

from datetime import datetime, timedelta
from typing import Literal

Granularity = Literal["hour", "day"]
ForecastModel = Literal["naive", "ma", "ewm"]


def forecast_counts(
    history: list[dict[str, object]],
    granularity: Granularity,
    horizon: int,
    model: str = "ma",
    window: int = 6,
    alpha: float = 0.3,
) -> list[dict[str, object]]:
    """
    Produce a deterministic forecast of violation counts for the next horizon steps.

    - history: list of {"ts": iso_str, "count": int} (same shape as /predict/timeseries).
    - granularity: "hour" or "day" (step delta).
    - horizon: number of future buckets to predict.
    - model: "naive" (last count), "ma" (average of last `window`), "ewm" (exponential weighted mean).
    - window: used for ma (number of last points to average).
    - alpha: used for ewm (smoothing factor).

    Returns list of {"ts": iso_str, "count": int}. Side-effect free and deterministic.
    """
    if not history or horizon <= 0:
        return []

    step_delta = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)

    # Parse last timestamp (naive ISO; strip Z if present for compatibility).
    last_ts_str = str(history[-1]["ts"])
    if last_ts_str.endswith("Z"):
        last_ts_str = last_ts_str[:-1] + "+00:00"
    last_ts = datetime.fromisoformat(last_ts_str)
    if last_ts.tzinfo is not None:
        last_ts = last_ts.replace(tzinfo=None)

    counts = [int(h["count"]) for h in history]

    if model == "naive":
        pred_val = counts[-1]
    elif model == "ma":
        n = min(window, len(counts))
        pred_val = sum(counts[-n:]) / n
    elif model == "ewm":
        ewm = float(counts[0])
        for c in counts[1:]:
            ewm = alpha * float(c) + (1.0 - alpha) * ewm
        pred_val = ewm
    else:
        raise ValueError(f"Unsupported model: {model}")

    predicted_count = max(0, round(pred_val))

    out: list[dict[str, object]] = []
    for step in range(1, horizon + 1):
        next_ts = last_ts + step * step_delta
        out.append({"ts": next_ts.isoformat(), "count": predicted_count})

    return out
