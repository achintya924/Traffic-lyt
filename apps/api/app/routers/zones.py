"""
Phase 5.1: Zone system — named areas (polygon, optional bbox).
Endpoints: POST /api/zones, GET /api/zones, GET /api/zones/{id}, DELETE /api/zones/{id}
"""
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/zones", tags=["zones"])


# --- Pydantic models ---

class ZoneCreatePolygon(BaseModel):
    """GeoJSON Polygon coordinates: [[[lon,lat],[lon,lat],...]] (closed ring)."""
    type: str = Field(..., pattern="^Polygon$")
    coordinates: list[list[list[float]]] = Field(..., min_length=1)

    def to_wkt(self) -> str:
        """Convert to WKT for ST_GeomFromText."""
        ring = self.coordinates[0]
        if len(ring) < 4:
            raise ValueError("Polygon ring must have at least 4 points (closed)")
        pts = []
        for i, pt in enumerate(ring):
            if len(pt) < 2:
                raise ValueError("Each point must have [lon, lat]")
            lon, lat = float(pt[0]), float(pt[1])
            pts.append(f"{lon} {lat}")
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        return f"POLYGON(({','.join(pts)}))"


class ZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    zone_type: str = Field(default="custom", pattern="^(custom|borough|district|other)$")
    polygon: ZoneCreatePolygon
    bbox: list[float] | None = Field(None, min_length=4, max_length=4)
    tags: dict[str, Any] | None = None


# --- Helpers ---

def _zone_meta(request: Request) -> dict:
    """Phase 4 meta: request_id when available."""
    meta: dict[str, Any] = {}
    if hasattr(request.state, "request_id"):
        meta["request_id"] = getattr(request.state, "request_id", None)
    return meta


def _bbox_from_geom(geom_wkt: str) -> tuple[float, float, float, float] | None:
    """Compute bbox from geometry via SQL. Returns (minx, miny, maxx, maxy) or None."""
    engine = get_engine()
    if not engine:
        return None
    with get_connection() as conn:
        if not conn:
            return None
        row = conn.execute(
            text("""
                SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g)
                FROM ST_GeomFromText(:wkt, 4326) AS g
            """),
            {"wkt": geom_wkt},
        ).fetchone()
        if row and all(v is not None for v in row):
            return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
    return None


# --- Endpoints ---

@router.post("", status_code=201, dependencies=[Depends(rate_limit("stats"))])
def create_zone(request: Request, body: ZoneCreate) -> dict[str, Any]:
    """Create a zone. Validates polygon (min 4 points, closed). Uses ST_IsValid."""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        wkt = body.polygon.to_wkt()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        # Validate with ST_IsValid
        valid_row = conn.execute(
            text("SELECT ST_IsValid(ST_GeomFromText(:wkt, 4326))"),
            {"wkt": wkt},
        ).fetchone()
        if not valid_row or not valid_row[0]:
            validity = conn.execute(
                text("SELECT ST_IsValidReason(ST_GeomFromText(:wkt, 4326))"),
                {"wkt": wkt},
            ).fetchone()
            reason = validity[0] if validity else "Invalid geometry"
            raise HTTPException(status_code=422, detail=f"Invalid polygon: {reason}")

        bbox = body.bbox
        if not bbox:
            computed = _bbox_from_geom(wkt)
            if computed:
                bbox = list(computed)

        bbox_minx = bbox[0] if bbox and len(bbox) >= 4 else None
        bbox_miny = bbox[1] if bbox and len(bbox) >= 4 else None
        bbox_maxx = bbox[2] if bbox and len(bbox) >= 4 else None
        bbox_maxy = bbox[3] if bbox and len(bbox) >= 4 else None

        tags_json = json.dumps(body.tags) if body.tags else None

        row = conn.execute(
            text("""
                INSERT INTO zones (name, zone_type, geom, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, tags)
                VALUES (
                    :name,
                    :zone_type,
                    ST_GeomFromText(:wkt, 4326),
                    :bbox_minx,
                    :bbox_miny,
                    :bbox_maxx,
                    :bbox_maxy,
                    CAST(:tags AS JSONB)
                )
                RETURNING id, name, zone_type, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, created_at
            """),
            {
                "name": body.name.strip(),
                "zone_type": body.zone_type,
                "wkt": wkt,
                "bbox_minx": bbox_minx,
                "bbox_miny": bbox_miny,
                "bbox_maxx": bbox_maxx,
                "bbox_maxy": bbox_maxy,
                "tags": tags_json,
            },
        ).fetchone()

        conn.commit()

        return {
            "id": row[0],
            "name": row[1],
            "zone_type": row[2],
            "bbox": {
                "minx": row[3],
                "miny": row[4],
                "maxx": row[5],
                "maxy": row[6],
            } if row[3] is not None else None,
            "created_at": row[7].isoformat() if row[7] else None,
            "meta": _zone_meta(request),
        }


@router.get("", dependencies=[Depends(rate_limit("stats"))])
def list_zones(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    zone_type: str | None = Query(None, description="Filter by zone_type"),
    search: str | None = Query(None, description="Search by name (ILIKE)"),
    include_geom: bool = Query(False, alias="includeGeom"),
) -> dict[str, Any]:
    """List zones. By default excludes geometry; use includeGeom=true to include."""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if zone_type:
            conditions.append("zone_type = :zone_type")
            params["zone_type"] = zone_type
        if search and search.strip():
            conditions.append("name ILIKE :search")
            params["search"] = f"%{search.strip()}%"

        where = (" AND " + " AND ".join(conditions)) if conditions else ""

        if include_geom:
            geom_col = "ST_AsGeoJSON(geom)::json AS geom"
        else:
            geom_col = "NULL::json AS geom"

        rows = conn.execute(
            text(f"""
                SELECT id, name, zone_type, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy,
                       created_at, updated_at, tags, {geom_col}
                FROM zones
                {where}
                ORDER BY name
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        count_params = {k: v for k, v in params.items() if k in ("zone_type", "search")}
        total = conn.execute(
            text(f"SELECT COUNT(*)::int FROM zones {where}"),
            count_params,
        ).scalar() or 0

    zones_list = []
    for r in rows:
        z: dict[str, Any] = {
            "id": r[0],
            "name": r[1],
            "zone_type": r[2],
            "bbox": {
                "minx": r[3],
                "miny": r[4],
                "maxx": r[5],
                "maxy": r[6],
            } if r[3] is not None else None,
            "created_at": r[7].isoformat() if r[7] else None,
            "updated_at": r[8].isoformat() if r[8] else None,
            "tags": r[9],
        }
        if include_geom and r[10]:
            z["geom"] = r[10] if isinstance(r[10], dict) else json.loads(r[10])
        zones_list.append(z)

    return {
        "zones": zones_list,
        "total": total,
        "limit": limit,
        "offset": offset,
        "meta": _zone_meta(request),
    }


@router.get("/{zone_id}", dependencies=[Depends(rate_limit("stats"))])
def get_zone(request: Request, zone_id: int) -> dict[str, Any]:
    """Get zone by id. Includes geometry."""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        row = conn.execute(
            text("""
                SELECT id, name, zone_type, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy,
                       created_at, updated_at, tags, ST_AsGeoJSON(geom)::json AS geom
                FROM zones
                WHERE id = :id
            """),
            {"id": zone_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Zone not found")

    return {
        "id": row[0],
        "name": row[1],
        "zone_type": row[2],
        "bbox": {
            "minx": row[3],
            "miny": row[4],
            "maxx": row[5],
            "maxy": row[6],
        } if row[3] is not None else None,
        "created_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
        "tags": row[9],
        "geom": row[10] if isinstance(row[10], dict) else json.loads(row[10]) if row[10] else None,
        "meta": _zone_meta(request),
    }


@router.delete("/{zone_id}", dependencies=[Depends(rate_limit("stats"))])
def delete_zone(request: Request, zone_id: int) -> dict[str, Any]:
    """Delete zone by id (hard delete)."""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        result = conn.execute(text("DELETE FROM zones WHERE id = :id RETURNING id"), {"id": zone_id})
        deleted = result.fetchone()
        conn.commit()

        if not deleted:
            raise HTTPException(status_code=404, detail="Zone not found")

    return {"deleted": zone_id, "meta": _zone_meta(request)}
