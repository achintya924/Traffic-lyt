'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type Violation = {
  id: number;
  lat: number;
  lon: number;
  occurred_at: string | null;
  violation_type: string | null;
};

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

const ViolationsMap = dynamic(
  () => import('@/app/map/ViolationsMap'),
  { ssr: false }
);

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
          Total violations (filtered): {statsTotal !== null ? statsTotal : '…'}
        </p>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          {violations.length} points · NYC
        </p>
        <div style={{ marginTop: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid #334155' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>Insights</div>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>
            Busiest hour: {hour && hour.count > 0 ? `${String(hour.hour).padStart(2, '0')}:00 (${hour.count})` : 'No data'}
          </p>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '0.25rem 0 0 0' }}>
            Busiest day: {day && day.count > 0 ? `${day.day} (${day.count})` : 'No data'}
          </p>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ViolationsMap violations={violations} />
      </div>
    </main>
  );
}
