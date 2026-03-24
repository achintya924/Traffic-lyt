"""
Phase 5.9C: Forecast-based policy baseline helpers.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.predict.forecast import forecast_counts


def _ts_iso(val: Any) -> str:
    if isinstance(val, date) and not isinstance(val, datetime):
        val = datetime.combine(val, datetime.min.time())
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.replace(tzinfo=None)
        return val.isoformat()
    return str(val)


def get_zone_baseline(conn: Connection, zone_id: str, horizon: str, anchor_ts: datetime) -> dict[str, Any]:
    """
    Build forecast-based baseline for one zone.
    horizon=24h -> hourly forecast horizon 24
    horizon=30d -> daily forecast horizon 30
    """
    granularity = "hour" if horizon == "24h" else "day"
    horizon_steps = 24 if horizon == "24h" else 30
    trunc = "hour" if horizon == "24h" else "day"

    sql = text(
        f"""
        WITH buckets AS (
            SELECT date_trunc('{trunc}', v.occurred_at) AS ts, COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE (CAST(z.id AS TEXT) = :zone_id OR z.name = :zone_id)
              AND v.occurred_at <= :anchor_ts
            GROUP BY ts
            ORDER BY ts DESC
            LIMIT 500
        )
        SELECT ts, cnt FROM buckets ORDER BY ts ASC
        """
    )
    rows = conn.execute(sql, {"zone_id": zone_id, "anchor_ts": anchor_ts}).fetchall()
    history = [{"ts": _ts_iso(r[0]), "count": int(r[1])} for r in rows]
    forecast = forecast_counts(
        history=history,
        granularity=granularity,  # type: ignore[arg-type]
        horizon=horizon_steps,
        model="ma",
        window=6,
        alpha=0.3,
    )
    total = float(sum(int(p.get("count", 0)) for p in forecast))
    return {"zone_id": zone_id, "total": total}


def get_multi_zone_baseline(
    conn: Connection, zones: list[str], horizon: str, anchor_ts: datetime
) -> dict[str, Any]:
    zone_totals = [get_zone_baseline(conn, z, horizon, anchor_ts) for z in zones]
    overall_total = float(sum(float(z["total"]) for z in zone_totals))
    return {"zones": zone_totals, "overall_total": overall_total}
