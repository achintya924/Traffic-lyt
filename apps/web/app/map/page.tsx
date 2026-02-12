'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

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

type StatsResponse = {
  total?: number;
  min_time?: string | null;
  max_time?: string | null;
  top_types?: { violation_type: string; count: number }[];
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
  const boundsTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
    let cancelled = false;
    setHeatmapError(null);
    setHeatmapLoading(true);
    const url = `${API_BASE}/aggregations/grid?cell_m=${gridSize}&bbox=${bboxString(bounds)}`;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((list: HeatmapPoint[]) => {
        if (!cancelled) {
          setHeatmapPoints(Array.isArray(list) ? list : []);
          setHeatmapError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setHeatmapError(e instanceof Error ? e.message : String(e));
          setHeatmapPoints([]);
        }
      })
      .finally(() => {
        if (!cancelled) setHeatmapLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [viewMode, bounds, gridSize]);

  // Re-fetch viewport-aware analytics (stats + hour/day buckets) whenever bounds change.
  useEffect(() => {
    if (!bounds) return;
    let cancelled = false;
    const bbox = bboxString(bounds);
    async function fetchViewportAnalytics() {
      try {
        const [statsRes, hourRes, dayRes] = await Promise.all([
          fetch(`${API_BASE}/violations/stats?bbox=${bbox}`),
          fetch(`${API_BASE}/aggregations/time/hour?bbox=${bbox}`),
          fetch(`${API_BASE}/aggregations/time/day?bbox=${bbox}`),
        ]);
        if (!statsRes.ok || !hourRes.ok || !dayRes.ok) {
          return;
        }
        const [statsJson, hoursJson, daysJson]: [StatsResponse, HourBucket[], DayBucket[]] =
          await Promise.all([statsRes.json(), hourRes.json(), dayRes.json()]);
        if (cancelled) return;
        if (typeof statsJson.total === 'number') {
          setStatsTotal(statsJson.total);
        }
        setHourBuckets(Array.isArray(hoursJson) ? hoursJson : []);
        setDayBuckets(Array.isArray(daysJson) ? daysJson : []);
      } catch {
        // Keep existing values on error; viewport insights simply won't update this time.
      }
    }
    fetchViewportAnalytics();
    return () => {
      cancelled = true;
    };
  }, [bounds]);

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
    <main style={{ padding: 0, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '0.75rem 1rem', background: '#1e293b', flexShrink: 0 }}>
        <h1 style={{ fontSize: '1.25rem' }}>Violations map</h1>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          Total violations (this view): {statsTotal !== null ? statsTotal : '…'}
        </p>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          {violations.length} points · NYC
        </p>
        {/* TEMP: bounds debug for Phase 2.2-B verification */}
        <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
          Bounds: {bounds ? `${bounds.west.toFixed(3)},${bounds.south.toFixed(3)},${bounds.east.toFixed(3)},${bounds.north.toFixed(3)}` : 'n/a'}
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
              {heatmapLoading && <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Loading…</span>}
              {heatmapError && <span style={{ fontSize: '0.8rem', color: '#f87171' }}>{heatmapError}</span>}
            </>
          )}
        </div>
        <div style={{ marginTop: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid #334155' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>
            Insights (this view)
          </div>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>
            Busiest hour: {hour && hour.count > 0 ? `${String(hour.hour).padStart(2, '0')}:00 (${hour.count})` : 'No data'}
          </p>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '0.25rem 0 0 0' }}>
            Busiest day: {day && day.count > 0 ? `${day.day} (${day.count})` : 'No data'}
          </p>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ViolationsMap
          violations={violations}
          viewMode={viewMode}
          heatmapPoints={heatmapPoints}
          onBoundsChange={onBoundsChange}
        />
      </div>
    </main>
  );
}
