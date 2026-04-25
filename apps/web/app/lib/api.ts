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
  city?: string;
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
  if (params.city != null) p.set('city', params.city);
  return p.toString();
}

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

const HOTSPOTS_CACHE_TTL_MS = 3000;
const HOTSPOTS_CACHE_MAX_ENTRIES = 50;

type HotspotsCacheEntry =
  | { data: HotspotsGridResponse; ts: number; inFlightPromise?: never }
  | { data?: never; ts: number; inFlightPromise: Promise<HotspotsGridResponse> };

const hotspotsCache = new Map<string, HotspotsCacheEntry>();

function hotspotsCacheKey(params: FetchHotspotsParams): string {
  const k = [
    params.bbox,
    String(params.cell_m ?? 250),
    String(params.recent_days ?? 7),
    String(params.baseline_days ?? 30),
    String(params.limit ?? 3000),
  ];
  if (params.start != null) k.push(params.start);
  if (params.end != null) k.push(params.end);
  if (params.hour_start != null) k.push(String(params.hour_start));
  if (params.hour_end != null) k.push(String(params.hour_end));
  if (params.violation_type != null) k.push(params.violation_type);
  if (params.city != null) k.push(params.city);
  return k.join('|');
}

export function debugRateLimit(msg: string, data?: Record<string, unknown>): void {
  if (typeof window !== 'undefined' && localStorage?.getItem?.('TRAFFICLYT_DEBUG_RATE') === '1') {
    console.log(`[trafficlyt:rate] ${msg}`, data ?? '');
  }
}

function pruneHotspotsCache(excludeKey: string): void {
  if (hotspotsCache.size < HOTSPOTS_CACHE_MAX_ENTRIES) return;
  const candidates = [...hotspotsCache.entries()]
    .filter(([k, v]) => k !== excludeKey && 'data' in v)
    .sort((a, b) => a[1].ts - b[1].ts);
  const victim = candidates[0];
  if (victim) hotspotsCache.delete(victim[0]);
}

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

export async function fetchHotspotsGridCached(
  params: FetchHotspotsParams,
  signal?: AbortSignal
): Promise<HotspotsGridResponse> {
  const key = hotspotsCacheKey(params);
  const keyHash = key.slice(0, 20) + (key.length > 20 ? '…' : '');

  const entry = hotspotsCache.get(key);
  const now = Date.now();

  if (entry) {
    if (entry.inFlightPromise) {
      debugRateLimit('in-flight dedupe', { keyHash, endpoint: 'hotspots/grid' });
      return entry.inFlightPromise;
    }
    if (now - entry.ts < HOTSPOTS_CACHE_TTL_MS) {
      debugRateLimit('cache hit', { keyHash, endpoint: 'hotspots/grid', ageMs: now - entry.ts });
      return entry.data;
    }
  }

  pruneHotspotsCache(key);

  const doFetch = () =>
    fetchHotspotsGrid(params, signal).then((data) => {
      hotspotsCache.set(key, { data, ts: Date.now() });
      debugRateLimit('cache miss (success)', { keyHash, endpoint: 'hotspots/grid' });
      return data;
    });

  const promise = doFetch();
  hotspotsCache.set(key, { ts: now, inFlightPromise: promise });
  promise.catch(() => {
    hotspotsCache.delete(key);
  });

  return promise;
}

export async function fetchStats(
  bbox?: string,
  city?: string,
  signal?: AbortSignal
): Promise<StatsResponse> {
  const p = new URLSearchParams();
  if (bbox) p.set('bbox', bbox);
  if (city) p.set('city', city);
  const qs = p.toString();
  const url = qs ? `${API_BASE}/violations/stats?${qs}` : `${API_BASE}/violations/stats`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Stats: HTTP ${res.status}`);
  return res.json();
}

export async function fetchRisk(
  params: { bbox: string; granularity?: string; horizon?: number; city?: string },
  signal?: AbortSignal
): Promise<RiskResponse> {
  const p = new URLSearchParams();
  p.set('bbox', params.bbox);
  p.set('granularity', params.granularity ?? 'hour');
  p.set('horizon', String(params.horizon ?? 24));
  if (params.city) p.set('city', params.city);
  const res = await fetch(`${API_BASE}/predict/risk?${p}`, { signal });
  if (!res.ok) throw new Error(`Risk: HTTP ${res.status}`);
  return res.json();
}

export type ForecastResponse = {
  granularity: string;
  model: { name: string; horizon: number };
  history: { ts: string; count: number }[];
  forecast: { ts: string; count: number }[];
  summary?: { expected_total: number; horizon: number; granularity: string; scope: string };
  meta?: Partial<ApiMeta> & { data_quality?: { status: string; reason?: string; recommendation?: string } | null };
};

export async function fetchForecast(
  params: { bbox: string; granularity?: string; horizon?: number; city?: string },
  signal?: AbortSignal
): Promise<ForecastResponse> {
  const p = new URLSearchParams();
  p.set('bbox', params.bbox);
  p.set('granularity', params.granularity ?? 'day');
  p.set('horizon', String(params.horizon ?? 30));
  if (params.city) p.set('city', params.city);
  const res = await fetch(`${API_BASE}/predict/forecast?${p}`, { signal });
  if (!res.ok) throw new Error(`Forecast: HTTP ${res.status}`);
  return res.json();
}

// --- Phase 5.7: Zones API ---

export type ZoneSummary = {
  id: number;
  name: string;
  zone_type: string;
  bbox?: { minx: number; miny: number; maxx: number; maxy: number } | null;
  created_at?: string | null;
};

export type ZonesListResponse = {
  zones: ZoneSummary[];
  total: number;
  limit: number;
  offset: number;
  meta?: Partial<ApiMeta>;
};

export type ZoneDetailResponse = ZoneSummary & {
  updated_at?: string | null;
  tags?: unknown;
  geom?: unknown;
};

export type ZoneAnalyticsResponse = {
  zone: { id: number; name: string; zone_type: string };
  summary: { total_count: number; trend_direction: string; percent_change: number };
  time_series: { bucket_ts: string; count: number }[];
  top_violation_types: { violation_type: string; count: number }[];
  meta?: { response_cache?: 'hit' | 'miss'; [k: string]: unknown };
};

export type ZoneCompareResponse = {
  zone: { id: number; name: string; zone_type: string };
  period: 'wow' | 'mom';
  current: { window: { start_ts: string; end_ts: string }; total_count: number };
  previous: { window: { start_ts: string; end_ts: string }; total_count: number };
  delta: { delta_count: number; delta_percent: number; trend_label: string };
  meta?: { response_cache?: 'hit' | 'miss'; [k: string]: unknown };
};

export async function fetchZones(city?: string, signal?: AbortSignal): Promise<ZonesListResponse> {
  const p = new URLSearchParams();
  p.set('limit', '200');
  if (city) p.set('city', city);
  const res = await fetch(`${API_BASE}/api/zones?${p}`, { signal });
  if (!res.ok) throw new Error(`Zones: HTTP ${res.status}`);
  return res.json();
}

export async function fetchZoneById(id: number, signal?: AbortSignal): Promise<ZoneDetailResponse> {
  const res = await fetch(`${API_BASE}/api/zones/${id}`, { signal });
  if (!res.ok) throw new Error(`Zone ${id}: HTTP ${res.status}`);
  return res.json();
}

export async function fetchZoneAnalytics(
  id: number,
  params?: { granularity?: string },
  signal?: AbortSignal
): Promise<ZoneAnalyticsResponse> {
  const p = new URLSearchParams();
  if (params?.granularity) p.set('granularity', params.granularity);
  const qs = p.toString();
  const url = `${API_BASE}/api/zones/${id}/analytics${qs ? `?${qs}` : ''}`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Zone analytics: HTTP ${res.status}`);
  return res.json();
}

export async function fetchZoneCompare(
  id: number,
  period: 'wow' | 'mom',
  params?: { granularity?: string },
  signal?: AbortSignal
): Promise<ZoneCompareResponse> {
  const p = new URLSearchParams();
  p.set('period', period);
  if (params?.granularity) p.set('granularity', params.granularity);
  const res = await fetch(`${API_BASE}/api/zones/${id}/compare?${p}`, { signal });
  if (!res.ok) throw new Error(`Zone compare: HTTP ${res.status}`);
  return res.json();
}

// --- Phase 6.1: Zone rankings + Warnings ---

export type ZoneRankingsSortBy = 'risk' | 'trend' | 'volume';

export type ZoneRankingRow = {
  zone_id: number;
  name: string;
  zone_type: string;
  total_count: number;
  trend_direction: string;
  percent_change: number;
  score: number;
};

export type ZoneRankingsResponse = {
  rankings: ZoneRankingRow[];
  meta?: { response_cache?: 'hit' | 'miss'; anchor_ts?: string | null; [k: string]: unknown };
};

export async function fetchZoneRankings(
  params?: { sort_by?: ZoneRankingsSortBy; limit?: number; city?: string },
  signal?: AbortSignal
): Promise<ZoneRankingsResponse> {
  const p = new URLSearchParams();
  p.set('sort_by', params?.sort_by ?? 'risk');
  p.set('limit', String(params?.limit ?? 20));
  if (params?.city) p.set('city', params.city);
  const res = await fetch(`${API_BASE}/api/zones/rankings?${p}`, { signal });
  if (!res.ok) throw new Error(`Rankings: HTTP ${res.status}`);
  return res.json();
}

export type WarningSeverity = 'high' | 'medium' | 'low';
export type WarningType = 'trend_up' | 'wow_spike' | 'mom_spike' | 'anomaly_cluster';

export type WarningCard = {
  warning_type: WarningType | string;
  severity: WarningSeverity;
  zone: { id: number; name: string; zone_type: string };
  headline: string;
  details?: Record<string, unknown>;
  recommendation_hint?: string;
};

export type WarningsExplainEntry = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export type WarningsResponse = {
  warnings: WarningCard[];
  explain?: WarningsExplainEntry[];
  meta?: { response_cache?: 'hit' | 'miss'; anchor_ts?: string | null; [k: string]: unknown };
};

export async function fetchWarnings(
  params?: { limit?: number; city?: string },
  signal?: AbortSignal
): Promise<WarningsResponse> {
  const p = new URLSearchParams();
  p.set('scope', 'zones');
  p.set('limit', String(params?.limit ?? 25));
  if (params?.city) p.set('city', params.city);
  const res = await fetch(`${API_BASE}/api/warnings?${p}`, { signal });
  if (!res.ok) throw new Error(`Warnings: HTTP ${res.status}`);
  return res.json();
}

// --- Phase 6.2: Patrol allocation ---

export type PatrolStrategy = 'balanced' | 'risk_max' | 'trend_focus';

export type PatrolAssignment = {
  zone: { id: number; name: string; zone_type: string };
  assigned_units: number;
  priority_score: number;
  reasons: { signal: string; value: number | boolean | string }[];
  recommendation_hint?: string;
};

export type PatrolAllocateResponse = {
  plan: PatrolAssignment[];
  meta?: { response_cache?: 'hit' | 'miss'; anchor_ts?: string | null; [k: string]: unknown };
  explain?: WarningsExplainEntry[];
};

export type PatrolAllocateBody = {
  units: number;
  strategy: PatrolStrategy;
  period?: 'current' | 'wow' | 'mom';
  shift_hours?: number;
  exclude_zone_ids?: number[];
};

export async function fetchPatrolAllocate(
  body: PatrolAllocateBody,
  signal?: AbortSignal
): Promise<PatrolAllocateResponse> {
  const res = await fetch(`${API_BASE}/api/patrol/allocate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Patrol: HTTP ${res.status}${detail ? ` ${detail}` : ''}`);
  }
  return res.json();
}

// --- Phase 6.2: Policy simulation ---

export type PolicyHorizon = '24h' | '30d';

export type EnforcementIntensityIntervention = {
  type: 'enforcement_intensity';
  pct: number;
};

export type PatrolUnitsIntervention = {
  type: 'patrol_units';
  from_units: number;
  to_units: number;
};

export type PeakHourReductionIntervention = {
  type: 'peak_hour_reduction';
  pct: number;
};

export type PolicyIntervention =
  | EnforcementIntensityIntervention
  | PatrolUnitsIntervention
  | PeakHourReductionIntervention;

export type PolicySimulateBody = {
  zones: string[];
  horizon: PolicyHorizon;
  interventions: PolicyIntervention[];
  anchor_ts?: string | null;
};

export type PolicyConfidenceLabel = 'low' | 'medium' | 'high';

export type PolicyZoneTotal = {
  zone_id: string;
  total: number;
  confidence_score?: number | null;
  confidence_label?: PolicyConfidenceLabel | null;
};

export type PolicyZoneDelta = {
  zone_id: string;
  delta: number;
  delta_pct: number | null;
};

export type PolicyConfidenceBlock = {
  score: number;
  label: PolicyConfidenceLabel;
  details?: Record<string, unknown> | null;
};

export type PolicyBaselineBlock = {
  horizon: PolicyHorizon;
  zones: PolicyZoneTotal[];
  overall_total: number;
  confidence?: PolicyConfidenceBlock | null;
};

export type PolicyDeltaBlock = {
  zones: PolicyZoneDelta[];
  overall_delta: number;
  overall_delta_pct: number | null;
};

export type PolicySimulateResponse = {
  meta: {
    request_id: string;
    anchor_ts: string;
    response_cache: { status: 'hit' | 'miss'; key?: string | null };
  };
  baseline: PolicyBaselineBlock;
  simulated: PolicyBaselineBlock;
  delta: PolicyDeltaBlock;
  explain: WarningsExplainEntry[];
};

// --- Phase 6.3: Decision endpoint ---

export type DecisionHorizon = '24h' | '30d';

export type DecisionHotspot = {
  cell_lon: number;
  cell_lat: number;
  count: number;
  zone_id: number;
  zone_name: string;
};

export type DecisionConfidence = {
  confidence_score: number;
  confidence_label: 'low' | 'medium' | 'high';
  details?: Record<string, unknown> | null;
};

export type DecisionPatrolPlan = {
  strategy: string;
  units: number;
  assignments: PatrolAssignment[];
};

export type DecisionForecastZone = {
  zone_id: string;
  total: number;
  confidence_score?: number | null;
  confidence_label?: string | null;
};

export type DecisionForecastBlock = {
  horizon: DecisionHorizon;
  zones: DecisionForecastZone[];
  overall_total: number;
};

export type DecisionVerdict = {
  priority_action: string;
  reasoning: string;
};

export type DecisionResponse = {
  meta: {
    request_id: string;
    anchor_ts: string;
    response_cache: { status: 'hit' | 'miss'; key?: string | null };
  };
  confidence: DecisionConfidence | null;
  warnings: WarningCard[];
  hotspots: DecisionHotspot[];
  patrol: DecisionPatrolPlan;
  forecast: DecisionForecastBlock;
  verdict: DecisionVerdict;
  explain: WarningsExplainEntry[];
};

export type DecisionNowBody = {
  zones: string[];
  horizon: DecisionHorizon;
  anchor_ts?: string | null;
};

export async function fetchDecisionNow(
  body: DecisionNowBody,
  signal?: AbortSignal
): Promise<DecisionResponse> {
  const res = await fetch(`${API_BASE}/api/decision/now`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Decision: HTTP ${res.status}${detail ? ` ${detail}` : ''}`);
  }
  return res.json();
}

export async function fetchPolicySimulate(
  body: PolicySimulateBody,
  signal?: AbortSignal
): Promise<PolicySimulateResponse> {
  const res = await fetch(`${API_BASE}/api/policy/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Policy: HTTP ${res.status}${detail ? ` ${detail}` : ''}`);
  }
  return res.json();
}
