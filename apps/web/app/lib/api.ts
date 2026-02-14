/**
 * API helpers for map/insights. Hotspots grid (Phase 3.3).
 */

export type HotspotCell = {
  centroid: [number, number]; // [lon, lat]
  recent_count: number;
  baseline_count: number;
  ratio: number;
  score: number;
  risk_level: 'low' | 'medium' | 'high';
};

export type HotspotsGridResponse = {
  cells: HotspotCell[];
  meta: {
    cell_m: number;
    grid_size_deg: number;
    recent_days: number;
    baseline_days: number;
    points: number;
  };
};

export type FetchHotspotsParams = {
  bbox: string;
  cell_m?: number;
  recent_days?: number;
  baseline_days?: number;
  limit?: number;
  start?: string;
  end?: string;
  hour_start?: number;
  hour_end?: number;
  violation_type?: string;
};

function searchParams(
  params: FetchHotspotsParams
): string {
  const p = new URLSearchParams();
  p.set('bbox', params.bbox);
  p.set('cell_m', String(params.cell_m ?? 250));
  p.set('recent_days', String(params.recent_days ?? 7));
  p.set('baseline_days', String(params.baseline_days ?? 30));
  p.set('limit', String(params.limit ?? 3000));
  if (params.start != null) p.set('start', params.start);
  if (params.end != null) p.set('end', params.end);
  if (params.hour_start != null) p.set('hour_start', String(params.hour_start));
  if (params.hour_end != null) p.set('hour_end', String(params.hour_end));
  if (params.violation_type != null) p.set('violation_type', params.violation_type);
  return p.toString();
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export async function fetchHotspotsGrid(
  params: FetchHotspotsParams,
  signal?: AbortSignal
): Promise<HotspotsGridResponse> {
  const url = `${API_BASE}/predict/hotspots/grid?${searchParams(params)}`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`Hotspots: HTTP ${res.status}`);
  }
  const json = await res.json();
  return {
    cells: Array.isArray(json.cells) ? json.cells : [],
    meta: json.meta ?? { cell_m: 0, grid_size_deg: 0, recent_days: 0, baseline_days: 0, points: 0 },
  };
}
