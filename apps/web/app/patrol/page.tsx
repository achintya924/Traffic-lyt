'use client';

import dynamic from 'next/dynamic';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchPatrolAllocate,
  fetchZones,
  type PatrolAllocateResponse,
  type PatrolAssignment,
  type PatrolStrategy,
  type ZoneSummary,
  type WarningsExplainEntry,
} from '@/app/lib/api';
import ZoneMultiSelect from '@/app/components/ZoneMultiSelect';
import CachePill from '@/app/components/CachePill';
import type { PatrolMapMarker } from '@/app/patrol/PatrolMap';

const PatrolMap = dynamic(() => import('@/app/patrol/PatrolMap'), { ssr: false });

const STRATEGIES: { value: PatrolStrategy; label: string; hint: string }[] = [
  { value: 'risk_max', label: 'Risk Max', hint: 'Maximise volume + anomaly coverage' },
  { value: 'trend_focus', label: 'Trend Focus', hint: 'Prioritise trending-up zones' },
  { value: 'balanced', label: 'Balanced', hint: 'Mix of volume, trend, anomaly' },
];

function zoneCenter(z: ZoneSummary): { lat: number; lon: number } | null {
  const b = z.bbox;
  if (
    !b ||
    typeof b.minx !== 'number' ||
    typeof b.miny !== 'number' ||
    typeof b.maxx !== 'number' ||
    typeof b.maxy !== 'number'
  ) {
    return null;
  }
  return { lat: (b.miny + b.maxy) / 2, lon: (b.minx + b.maxx) / 2 };
}

function reasonLabel(signal: string, value: number | boolean | string): string {
  switch (signal) {
    case 'high_volume': return `High volume (${value})`;
    case 'trend_up': return `Trend up (+${value}%)`;
    case 'wow_spike': return `WoW spike (+${value}%)`;
    case 'mom_spike': return `MoM spike (+${value}%)`;
    case 'anomaly_cluster': return `Anomaly cluster (${value})`;
    case 'warning_high': return 'High-severity warning';
    case 'volume': return `Volume baseline (${value})`;
    default: return `${signal}: ${value}`;
  }
}

function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skel-row">
          <div className="skel-line" style={{ width: '1.5rem', flexShrink: 0 }} />
          <div className="skel-block">
            <div className="skel-line" style={{ width: `${55 + (i % 3) * 12}%` }} />
            <div className="skel-line" style={{ width: `${28 + (i % 4) * 8}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PatrolPage() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [zonesError, setZonesError] = useState<string | null>(null);
  const [zonesKey, setZonesKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [units, setUnits] = useState<number>(10);
  const [strategy, setStrategy] = useState<PatrolStrategy>('balanced');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<PatrolAllocateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    setZonesLoading(true);
    fetchZones(ac.signal)
      .then((res) => setZones(res.zones ?? []))
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setZonesError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setZonesLoading(false));
    return () => ac.abort();
  }, [zonesKey]);

  const zonesById = useMemo(() => {
    const m = new Map<number, ZoneSummary>();
    zones.forEach((z) => m.set(z.id, z));
    return m;
  }, [zones]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!units || units < 1) {
      setError('Units must be at least 1.');
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setSubmitting(true);
    setError(null);
    try {
      const excludeIds =
        selectedIds.length > 0
          ? zones.map((z) => z.id).filter((id) => !selectedIds.includes(id))
          : [];
      const res = await fetchPatrolAllocate(
        { units, strategy, period: 'current', shift_hours: 6, exclude_zone_ids: excludeIds },
        ac.signal
      );
      setResult(res);
    } catch (err) {
      if ((err as { name?: string })?.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  };

  const markers: PatrolMapMarker[] = useMemo(() => {
    if (!result?.plan) return [];
    return result.plan
      .map((a) => {
        const z = zonesById.get(a.zone.id);
        const center = z ? zoneCenter(z) : null;
        if (!center) return null;
        return {
          zone_id: a.zone.id,
          name: a.zone.name,
          zone_type: a.zone.zone_type,
          lat: center.lat,
          lon: center.lon,
          units: a.assigned_units,
          priority_score: a.priority_score,
        };
      })
      .filter((m): m is PatrolMapMarker => m !== null);
  }, [result, zonesById]);

  const explainEntries: WarningsExplainEntry[] = result?.explain ?? [];
  const totalAssigned = useMemo(
    () => (result?.plan ?? []).reduce((s, a) => s + a.assigned_units, 0),
    [result]
  );
  const cacheHit = result?.meta?.response_cache === 'hit';

  return (
    <main className="panel-page">
      <header className="panel-header">
        <h1>Patrol Allocation</h1>
        <p className="panel-subtitle">
          Allocate patrol units across zones using a deterministic scoring strategy.
        </p>
      </header>

      <div className="panel-grid">
        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">Configure</div>
          </div>
          <form onSubmit={handleSubmit} className="form-stack">
            <label className="form-label">
              <span>Units</span>
              <input
                type="number"
                min={1}
                max={50}
                value={units}
                onChange={(e) => setUnits(Number(e.target.value))}
                className="panel-input"
                required
              />
            </label>

            <div>
              <span className="form-label-text">Strategy</span>
              <div className="panel-toggle-row" role="radiogroup" aria-label="Strategy">
                {STRATEGIES.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    role="radio"
                    aria-checked={strategy === s.value}
                    onClick={() => setStrategy(s.value)}
                    title={s.hint}
                    className={`panel-toggle${strategy === s.value ? ' panel-toggle-active' : ''}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <p className="panel-muted" style={{ marginTop: '0.3rem' }}>
                {STRATEGIES.find((s) => s.value === strategy)?.hint}
              </p>
            </div>

            {zonesLoading ? (
              <SkeletonRows count={4} />
            ) : (
              <>
                <ZoneMultiSelect
                  selectedIds={selectedIds}
                  onChange={setSelectedIds}
                  max={10}
                  label="Zones to consider (optional)"
                />
                <p className="panel-muted">
                  {selectedIds.length === 0
                    ? 'Leave empty to consider all zones.'
                    : `Only the ${selectedIds.length} selected zone${selectedIds.length === 1 ? '' : 's'} will be considered; others will be excluded.`}
                </p>
              </>
            )}

            <button
              type="submit"
              disabled={submitting || zonesLoading}
              className="panel-btn panel-btn-primary"
            >
              {submitting ? (
                <><span className="btn-spinner" aria-hidden="true" />Allocating…</>
              ) : (
                'Allocate patrols'
              )}
            </button>

            {zonesError && (
              <div className="error-card">
                <div className="error-card-title">Failed to load zones</div>
                <p className="error-card-message">{zonesError}</p>
                <div className="error-card-footer">
                  <button
                    type="button"
                    className="panel-btn"
                    onClick={() => setZonesKey((k) => k + 1)}
                  >
                    Retry
                  </button>
                </div>
              </div>
            )}
            {error && (
              <div className="error-card">
                <div className="error-card-title">Allocation failed</div>
                <p className="error-card-message">{error}</p>
              </div>
            )}
          </form>
        </section>

        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">Plan</div>
            {result && <CachePill hit={cacheHit} />}
          </div>
          {!result && !submitting && (
            <div className="empty-state">
              <p className="empty-state-title">No plan yet</p>
              <p className="empty-state-body">
                Submit the form to compute a patrol allocation plan.
              </p>
            </div>
          )}
          {submitting && (
            <div className="empty-state">
              <p className="empty-state-title">Computing allocation…</p>
            </div>
          )}
          {result && result.plan.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">No zones matched</p>
              <p className="empty-state-body">
                Try a different zone selection or strategy.
              </p>
            </div>
          )}
          {result && result.plan.length > 0 && (
            <>
              <p className="panel-muted">
                {totalAssigned} of {units} unit{units === 1 ? '' : 's'} assigned across{' '}
                {result.plan.length} zone{result.plan.length === 1 ? '' : 's'}.
              </p>
              <ol className="patrol-plan-list">
                {result.plan.map((a: PatrolAssignment, i: number) => (
                  <li key={a.zone.id} className="patrol-plan-row">
                    <span className="panel-rank-idx">{i + 1}.</span>
                    <div className="panel-rank-main">
                      <div className="panel-rank-name">{a.zone.name}</div>
                      <div className="panel-rank-meta">
                        <span>{a.zone.zone_type}</span>
                        <span>·</span>
                        <span>Priority {a.priority_score.toFixed(2)}</span>
                      </div>
                      {a.reasons && a.reasons.length > 0 && (
                        <div className="patrol-reasons">
                          {a.reasons.map((r, idx) => (
                            <span key={idx} className="patrol-reason-chip">
                              {reasonLabel(r.signal, r.value)}
                            </span>
                          ))}
                        </div>
                      )}
                      {a.recommendation_hint && (
                        <p className="warning-hint" style={{ marginTop: '0.2rem' }}>
                          {a.recommendation_hint}
                        </p>
                      )}
                    </div>
                    <span className="patrol-units-pill">
                      {a.assigned_units} unit{a.assigned_units === 1 ? '' : 's'}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      </div>

      <section className="panel-card panel-card-wide" style={{ marginTop: '1rem' }}>
        <div className="panel-card-header">
          <div className="panel-card-title">Map</div>
          {result && markers.length < result.plan.length && (
            <span className="panel-muted-inline">
              {result.plan.length - markers.length} zone(s) missing coordinates
            </span>
          )}
        </div>
        <div className="patrol-map-container">
          <PatrolMap markers={markers} />
          {markers.length === 0 && !submitting && (
            <div className="patrol-map-empty">Submit a plan to see zone markers.</div>
          )}
        </div>
      </section>

      {explainEntries.length > 0 && (
        <section className="panel-card panel-card-wide" style={{ marginTop: '1rem' }}>
          <div className="panel-card-header">
            <div className="panel-card-title">Explain</div>
          </div>
          <ul className="explain-list">
            {explainEntries.map((e, i) => (
              <li key={i} className="explain-row">
                <span className="explain-code">{e.code}</span>
                <p className="explain-message">{e.message}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
