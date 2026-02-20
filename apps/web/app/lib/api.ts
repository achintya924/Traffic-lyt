/**
 * API helpers for map/insights.
 * Phase 4.8: Extended meta types (anchor, cache, eval, explain).
 */

import type { ApiMeta } from './types';

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
  } & Partial<ApiMeta>;
};

export type StatsResponse = {
  total: number;
  min_time: string | null;
  max_time: string | null;
  top_types: { violation_type: string; count: number }[];
  meta?: Partial<ApiMeta>;
};

export type RiskForecastItem = { ts: string; expected: number; expected_rounded: number };

export type RiskResponse = {
  granularity: string;
  model: { name: string; alpha?: number; horizon: number };
  history_points: number;
  metrics: { mae?: number; mape?: number; test_points?: number };
  explain: { top_positive: { feature: string; coef: number }[]; top_negative: { feature: string; coef: number }[] };
  forecast: RiskForecastItem[];
  meta?: Partial<ApiMeta>;
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

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

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

export async function fetchStats(bbox?: string, signal?: AbortSignal): Promise<StatsResponse> {
  const url = bbox
    ? `${API_BASE}/violations/stats?bbox=${encodeURIComponent(bbox)}`
    : `${API_BASE}/violations/stats`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Stats: HTTP ${res.status}`);
  return res.json();
}

export async function fetchRisk(
  params: { bbox: string; granularity?: string; horizon?: number },
  signal?: AbortSignal
): Promise<RiskResponse> {
  const p = new URLSearchParams();
  p.set('bbox', params.bbox);
  p.set('granularity', params.granularity ?? 'hour');
  p.set('horizon', String(params.horizon ?? 24));
  const res = await fetch(`${API_BASE}/predict/risk?${p}`, { signal });
  if (!res.ok) throw new Error(`Risk: HTTP ${res.status}`);
  return res.json();
}
