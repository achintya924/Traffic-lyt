'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  API_BASE,
  fetchForecast,
  fetchHotspotsGrid,
  fetchRisk,
  fetchStats,
  type ForecastResponse,
  type HotspotCell,
  type RiskResponse,
  type StatsResponse,
} from '@/app/lib/api';
import AnchorInfo from '@/app/components/AnchorInfo';
import CachePill from '@/app/components/CachePill';
import RiskLegend from '@/app/components/RiskLegend';
import RiskPanel, { type ForecastMode } from '@/app/components/RiskPanel';

type Violation = {
  id: number;
  lat: number;
  lon: number;
  occurred_at: string | null;
  violation_type: string | null;
};

type HeatmapPoint = { lat: number; lon: number; count: number };
type MapBounds = { south: number; north: number; west: number; east: number };

type ViolationsResponse = {
  violations?: Violation[];
  error?: string;
};

type HourBucket = { hour: number; count: number };
type DayBucket = { day: string; count: number };

const ViolationsMap = dynamic(() => import('@/app/map/ViolationsMap'), { ssr: false });

const GRID_OPTIONS = [200, 250, 500, 1000] as const;

function bboxString(b: MapBounds): string {
  return `${b.west},${b.south},${b.east},${b.north}`;
}

function busiestHour(buckets: HourBucket[]): HourBucket | null {
  if (!buckets.length) return null;
  return buckets.reduce((best, b) =>
    b.count > best.count || (b.count === best.count && b.hour < best.hour) ? b : best
  );
}

function busiestDay(buckets: DayBucket[]): DayBucket | null {
  if (!buckets.length) return null;
  return buckets.reduce((best, b) =>
    b.count > best.count || (b.count === best.count && b.day < best.day) ? b : best
  );
}

function top5Hotspots(cells: HotspotCell[]): HotspotCell[] {
  return [...cells]
    .sort((a, b) => b.score !== a.score ? b.score - a.score : b.ratio - a.ratio)
    .slice(0, 5);
}

export default function MapPage() {
  const [data, setData] = useState<ViolationsResponse | null>(null);
  const [statsTotal, setStatsTotal] = useState<number | null>(null);
  const [hourBuckets, setHourBuckets] = useState<HourBucket[]>([]);
  const [dayBuckets, setDayBuckets] = useState<DayBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'markers' | 'heatmap'>('markers');
  const [gridSize, setGridSize] = useState<number>(250);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [heatmapPoints, setHeatmapPoints] = useState<HeatmapPoint[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);
  const [hotspotsCells, setHotspotsCells] = useState<HotspotCell[]>([]);
  const [hotspotsLoading, setHotspotsLoading] = useState(false);
  const [hotspotsError, setHotspotsError] = useState<string | null>(null);
  const [flyToTarget, setFlyToTarget] = useState<[number, number] | null>(null);
  const [riskData, setRiskData] = useState<RiskResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [forecast30dData, setForecast30dData] = useState<ForecastResponse | null>(null);
  const [forecastMode, setForecastMode] = useState<ForecastMode>('24h');
  const [anchorMeta, setAnchorMeta] = useState<StatsResponse['meta'] | null>(null);
  const [cacheHit, setCacheHit] = useState(false);
  const [showLoadingSpinner, setShowLoadingSpinner] = useState(false);
  const boundsTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadingDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const firstBoundsSetRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      try {
        const [violationsRes, statsRes, hourRes, dayRes] = await Promise.all([
          fetch(`${API_BASE}/violations?limit=500`),
          fetch(`${API_BASE}/violations/stats`),
          fetch(`${API_BASE}/aggregations/time/hour`),
          fetch(`${API_BASE}/aggregations/time/day`),
        ]);
        const json: ViolationsResponse = await violationsRes.json();
        if (!cancelled) {
          if (!violationsRes.ok) {
            setError(json.error || `HTTP ${violationsRes.status}`);
          } else {
            setData(json);
            setError(json.error || null);
          }
        }
        const statsJson: StatsResponse = await statsRes.json();
        if (!cancelled && typeof statsJson.total === 'number') {
          setStatsTotal(statsJson.total);
        }
        if (!cancelled && hourRes.ok) {
          const hours: HourBucket[] = await hourRes.json();
          setHourBuckets(Array.isArray(hours) ? hours : []);
        }
        if (!cancelled && dayRes.ok) {
          const days: DayBucket[] = await dayRes.json();
          setDayBuckets(Array.isArray(days) ? days : []);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, []);

  const onBoundsChange = useCallback((b: MapBounds) => {
    // First bounds report: set immediately so heatmap can fetch without waiting for debounce.
    if (!firstBoundsSetRef.current) {
      firstBoundsSetRef.current = true;
      setBounds(b);
      return;
    }
    if (boundsTimeoutRef.current) clearTimeout(boundsTimeoutRef.current);
    boundsTimeoutRef.current = setTimeout(() => {
      setBounds(b);
      boundsTimeoutRef.current = null;
    }, 300);
  }, []);

  useEffect(() => {
    if (viewMode !== 'heatmap' || !bounds) return;
    const ac = new AbortController();
    setHeatmapError(null);
    setHeatmapLoading(true);
    const url = `${API_BASE}/aggregations/grid?cell_m=${gridSize}&bbox=${bboxString(bounds)}`;
    fetch(url, { signal: ac.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((list: HeatmapPoint[]) => {
        setHeatmapPoints(Array.isArray(list) ? list : []);
        setHeatmapError(null);
      })
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setHeatmapError(e instanceof Error ? e.message : String(e));
        setHeatmapPoints([]);
      })
      .finally(() => setHeatmapLoading(false));
    return () => ac.abort();
  }, [viewMode, bounds, gridSize]);

  // Re-fetch viewport-aware analytics (stats + hour/day + hotspots + risk) with AbortController.
  // Non-flickering loading: show spinner only if loading > 150ms.
  useEffect(() => {
    if (!bounds) return;
    const ac = new AbortController();
    abortRef.current = ac;
    const signal = ac.signal;

    setHotspotsError(null);
    setHotspotsLoading(true);
    setRiskLoading(true);
    setShowLoadingSpinner(false);

    if (loadingDelayRef.current) clearTimeout(loadingDelayRef.current);
    loadingDelayRef.current = setTimeout(() => setShowLoadingSpinner(true), 150);

    const bbox = bboxString(bounds);

    let gotStatsMeta = false;
    async function fetchViewportAnalytics() {
      try {
        const [statsRes, hourRes, dayRes] = await Promise.all([
          fetch(`${API_BASE}/violations/stats?bbox=${bbox}`, { signal }),
          fetch(`${API_BASE}/aggregations/time/hour?bbox=${bbox}`, { signal }),
          fetch(`${API_BASE}/aggregations/time/day?bbox=${bbox}`, { signal }),
        ]);
        if (signal.aborted) return;
        if (!statsRes.ok || !hourRes.ok || !dayRes.ok) return;

        const [statsJson, hoursJson, daysJson]: [StatsResponse, HourBucket[], DayBucket[]] =
          await Promise.all([statsRes.json(), hourRes.json(), dayRes.json()]);
        if (signal.aborted) return;

        setStatsTotal(typeof statsJson.total === 'number' ? statsJson.total : null);
        setHourBuckets(Array.isArray(hoursJson) ? hoursJson : []);
        setDayBuckets(Array.isArray(daysJson) ? daysJson : []);
        if (statsJson.meta) {
          setAnchorMeta(statsJson.meta);
          setCacheHit(!!statsJson.meta.response_cache?.hit);
          gotStatsMeta = true;
        }
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return;
      }

      try {
        const hotspots = await fetchHotspotsGrid(
          { bbox, cell_m: gridSize, recent_days: 7, baseline_days: 30, limit: 3000 },
          signal
        );
        if (signal.aborted) return;
        setHotspotsCells(hotspots.cells);
        setHotspotsError(null);
        if (!gotStatsMeta && hotspots.meta) {
          setAnchorMeta(hotspots.meta as StatsResponse['meta']);
          setCacheHit(!!(hotspots.meta as { response_cache?: { hit?: boolean } })?.response_cache?.hit);
        }
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setHotspotsError(e instanceof Error ? e.message : 'Hotspots unavailable');
        setHotspotsCells([]);
      }

      try {
        const risk = await fetchRisk({ bbox, granularity: 'hour', horizon: 24 }, signal);
        if (signal.aborted) return;
        setRiskData(risk);
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setRiskData(null);
      }

      try {
        const forecast = await fetchForecast({ bbox, granularity: 'day', horizon: 30 }, signal);
        if (signal.aborted) return;
        setForecast30dData(forecast);
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setForecast30dData(null);
      } finally {
        if (!signal.aborted) {
          setHotspotsLoading(false);
          setRiskLoading(false);
          if (loadingDelayRef.current) {
            clearTimeout(loadingDelayRef.current);
            loadingDelayRef.current = null;
          }
          setShowLoadingSpinner(false);
        }
      }
    }
    fetchViewportAnalytics();

    return () => {
      ac.abort();
      abortRef.current = null;
      if (loadingDelayRef.current) {
        clearTimeout(loadingDelayRef.current);
        loadingDelayRef.current = null;
      }
    };
  }, [bounds, gridSize]);

  if (loading) {
    return (
      <main style={{ padding: '2rem', textAlign: 'center' }}>
        <h1>Violations map</h1>
        <p>Loading violations…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main style={{ padding: '2rem' }}>
        <h1>Violations map</h1>
        <div className="status err" style={{ marginTop: '1rem' }}>
          <div className="label">Error</div>
          <p>{error}</p>
          <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>
            Ensure the API is running and you have run ingest.
          </p>
        </div>
      </main>
    );
  }

  const violations = data?.violations ?? [];
  const hour = busiestHour(hourBuckets);
  const day = busiestDay(dayBuckets);
  return (
    <main className="map-page">
      <header style={{ padding: '0.75rem 1rem', background: '#1e293b', flexShrink: 0 }}>
        <h1 style={{ fontSize: '1.25rem' }}>Violations map</h1>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          Total violations (this view): {statsTotal !== null ? statsTotal : '…'}
          <CachePill hit={cacheHit} />
        </p>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          {violations.length} points · NYC
        </p>
        <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>View:</span>
          <button
            type="button"
            onClick={() => setViewMode('markers')}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
              background: viewMode === 'markers' ? '#334155' : 'transparent',
              color: '#e2e8f0',
              border: '1px solid #475569',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Markers
          </button>
          <button
            type="button"
            onClick={() => setViewMode('heatmap')}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
              background: viewMode === 'heatmap' ? '#334155' : 'transparent',
              color: '#e2e8f0',
              border: '1px solid #475569',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Heatmap
          </button>
          {viewMode === 'heatmap' && (
            <>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Grid:</span>
              <select
                value={gridSize}
                onChange={(e) => setGridSize(Number(e.target.value))}
                style={{
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.8rem',
                  background: '#1e293b',
                  color: '#e2e8f0',
                  border: '1px solid #475569',
                  borderRadius: 4,
                }}
              >
                {GRID_OPTIONS.map((m) => (
                  <option key={m} value={m}>{m}m</option>
                ))}
              </select>
              {heatmapLoading && showLoadingSpinner && <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Loading…</span>}
              {heatmapError && <span style={{ fontSize: '0.8rem', color: '#f87171' }}>{heatmapError}</span>}
            </>
          )}
        </div>
        <AnchorInfo meta={anchorMeta} label="Data" />
        <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#94a3b8' }}>
          Busiest hour: {hour && hour.count > 0 ? `${String(hour.hour).padStart(2, '0')}:00 (${hour.count})` : 'No data'}
          {' · '}
          Busiest day: {day && day.count > 0 ? `${day.day} (${day.count})` : 'No data'}
        </div>
      </header>

      <div className="map-page-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}>
          <div className="map-map-container">
            <RiskLegend />
            <ViolationsMap
              violations={violations}
              viewMode={viewMode}
              heatmapPoints={heatmapPoints}
              onBoundsChange={onBoundsChange}
              flyToTarget={flyToTarget}
              onFlyToDone={() => setFlyToTarget(null)}
            />
          </div>
          <div style={{ background: '#1e293b', borderRadius: 8, padding: '0.75rem 1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>
              Top 5 Hotspots
            </div>
            {hotspotsLoading && showLoadingSpinner && (
              <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>Loading…</p>
            )}
            {hotspotsError && !hotspotsLoading && (
              <p style={{ fontSize: '0.8rem', color: '#f87171', margin: 0 }}>{hotspotsError}</p>
            )}
            {!hotspotsLoading && !hotspotsError && (() => {
              const top5 = top5Hotspots(hotspotsCells);
              if (top5.length === 0) {
                return <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>No hotspots in this view/time range.</p>;
              }
              const riskColors = { high: '#ef4444', medium: '#f59e0b', low: '#22c55e' };
              return (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {top5.map((cell, i) => (
                    <li
                      key={`${cell.centroid[0]}-${cell.centroid[1]}`}
                      style={{
                        fontSize: '0.75rem',
                        color: '#e2e8f0',
                        marginTop: '0.25rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                        flexWrap: 'wrap',
                      }}
                    >
                      <span style={{ fontWeight: 600, minWidth: '1.25rem' }}>{i + 1}.</span>
                      <span
                        style={{
                          background: riskColors[cell.risk_level],
                          color: '#fff',
                          padding: '0.1rem 0.35rem',
                          borderRadius: 4,
                          fontSize: '0.7rem',
                        }}
                      >
                        {cell.risk_level}
                      </span>
                      <span>Score {Math.round(cell.score)}</span>
                      <span style={{ color: '#94a3b8' }}>
                        ({cell.recent_count} vs {cell.baseline_count})
                      </span>
                      <button
                        type="button"
                        onClick={() => setFlyToTarget([cell.centroid[1], cell.centroid[0]])}
                        style={{
                          padding: '0.1rem 0.35rem',
                          fontSize: '0.7rem',
                          background: '#334155',
                          color: '#e2e8f0',
                          border: '1px solid #475569',
                          borderRadius: 4,
                          cursor: 'pointer',
                        }}
                      >
                        Go to
                      </button>
                    </li>
                  ))}
                </ul>
              );
            })()}
          </div>
        </div>

        <aside className="map-sidebar" style={{ background: '#1e293b', borderRadius: 8, padding: '0.75rem 1rem' }}>
          {riskLoading && showLoadingSpinner && <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>Loading…</p>}
          <RiskPanel
            evalMeta={riskData?.meta?.eval ?? null}
            explainMeta={riskData?.meta?.explain ?? null}
            forecastTotal={riskData?.forecast?.reduce((s, f) => s + f.expected_rounded, 0)}
            horizon={riskData?.model?.horizon}
            forecastMode={forecastMode}
            onForecastModeChange={setForecastMode}
            forecast30d={
              forecast30dData?.summary
                ? { expectedTotal: forecast30dData.summary.expected_total, horizon: forecast30dData.summary.horizon }
                : undefined
            }
            dataQualityWarning={forecast30dData?.meta?.data_quality?.status === 'insufficient_data'}
          />
        </aside>
      </div>
    </main>
  );
}
