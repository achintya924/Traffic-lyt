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

const ViolationsMap = dynamic(
  () => import('@/app/map/ViolationsMap'),
  { ssr: false }
);

export default function MapPage() {
  const [data, setData] = useState<ViolationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchViolations() {
      try {
        const res = await fetch(`${API_BASE}/violations?limit=500`);
        const json: ViolationsResponse = await res.json();
        if (!cancelled) {
          if (!res.ok) {
            setError(json.error || `HTTP ${res.status}`);
          } else {
            setData(json);
            setError(json.error || null);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchViolations();
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
  return (
    <main style={{ padding: 0, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '0.75rem 1rem', background: '#1e293b', flexShrink: 0 }}>
        <h1 style={{ fontSize: '1.25rem' }}>Violations map</h1>
        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          {violations.length} points · NYC
        </p>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ViolationsMap violations={violations} />
      </div>
    </main>
  );
}
