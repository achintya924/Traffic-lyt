'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchDecisionNow,
  fetchZones,
  type DecisionResponse,
  type ZoneSummary,
} from '@/app/lib/api';
import ZoneMultiSelect from '@/app/components/ZoneMultiSelect';
import CachePill from '@/app/components/CachePill';
// no csv import needed — decision page uses window.print() only

const SEVERITY_COLOR: Record<string, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#3b82f6',
};

const TYPE_BG: Record<string, string> = {
  trend_up: '#fef3c7',
  wow_spike: '#fee2e2',
  mom_spike: '#fde8d8',
  anomaly_cluster: '#ede9fe',
};

const URGENCY_LABEL: Record<string, string> = {
  urgent: 'Urgent',
  caution: 'Caution',
  info: 'Monitor',
  clear: 'All Clear',
};

function verdictUrgency(
  result: DecisionResponse
): 'urgent' | 'caution' | 'info' | 'clear' {
  const warnings = result.warnings ?? [];
  const hotspots = result.hotspots ?? [];
  if (warnings.some((w) => w.severity === 'high')) return 'urgent';
  if (warnings.some((w) => w.severity === 'medium')) return 'caution';
  if (warnings.length > 0 || hotspots.length > 0) return 'info';
  return 'clear';
}

function hotspotRisk(count: number): 'high' | 'medium' | 'low' {
  if (count >= 20) return 'high';
  if (count >= 8) return 'medium';
  return 'low';
}

function confidenceColor(label: string | null | undefined): string {
  if (label === 'high') return '#22c55e';
  if (label === 'medium') return '#f59e0b';
  return '#ef4444';
}

function capitalize(s: string | null | undefined): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
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

export default function DecisionPage() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [horizon, setHorizon] = useState<'24h' | '30d'>('24h');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<DecisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explainOpen, setExplainOpen] = useState(false);
  const [autoRefreshActive, setAutoRefreshActive] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const lastParamsRef = useRef<{ zones: string[]; horizon: '24h' | '30d' } | null>(null);

  useEffect(() => {
    if (!localStorage.getItem('decision-walkthrough-dismissed')) {
      setBannerDismissed(false);
    }
  }, []);

  const dismissBanner = () => {
    localStorage.setItem('decision-walkthrough-dismissed', '1');
    setBannerDismissed(true);
  };

  useEffect(() => {
    const ac = new AbortController();
    setZonesLoading(true);
    fetchZones(ac.signal)
      .then((res) => setZones(res.zones ?? []))
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
      })
      .finally(() => setZonesLoading(false));
    return () => ac.abort();
  }, []);

  const zonesById = useMemo(() => {
    const m = new Map<number, ZoneSummary>();
    zones.forEach((z) => m.set(z.id, z));
    return m;
  }, [zones]);

  const doFetch = useCallback(
    async (
      zoneNames: string[],
      h: '24h' | '30d',
      signal: AbortSignal
    ): Promise<boolean> => {
      setSubmitting(true);
      setError(null);
      try {
        const res = await fetchDecisionNow({ zones: zoneNames, horizon: h }, signal);
        setResult(res);
        return true;
      } catch (err) {
        if ((err as { name?: string })?.name === 'AbortError') return false;
        setError(err instanceof Error ? err.message : String(err));
        return false;
      } finally {
        setSubmitting(false);
      }
    },
    []
  );

  const handlePrint = () => {
    setExplainOpen(true);
    setTimeout(() => window.print(), 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIds.length === 0) {
      setError('Select at least one zone.');
      return;
    }
    const zoneNames = selectedIds
      .map((id) => zonesById.get(id)?.name)
      .filter((n): n is string => Boolean(n));
    if (zoneNames.length === 0) {
      setError('Selected zones not found in zone list.');
      return;
    }
    lastParamsRef.current = { zones: zoneNames, horizon };
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    const ok = await doFetch(zoneNames, horizon, ac.signal);
    if (ok) setAutoRefreshActive(true);
  };

  useEffect(() => {
    if (!autoRefreshActive) return;
    const iv = setInterval(() => {
      const params = lastParamsRef.current;
      if (!params) return;
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      void doFetch(params.zones, params.horizon, ac.signal);
    }, 120_000);
    return () => clearInterval(iv);
  }, [autoRefreshActive, doFetch]);

  const urgency = result ? verdictUrgency(result) : 'clear';
  const cacheHit = result?.meta?.response_cache?.status === 'hit';

  // Defensive array extractions — guards against null/missing fields in partial responses
  const warnings = result?.warnings ?? [];
  const hotspots = result?.hotspots ?? [];
  const patrol = result?.patrol;
  const assignments = patrol?.assignments ?? [];
  const forecast = result?.forecast;
  const forecastZones = forecast?.zones ?? [];
  const explainEntries = result?.explain ?? [];

  return (
    <main className="panel-page">
      <header className="panel-header">
        <h1>Decision Dashboard</h1>
        <p className="panel-subtitle">What should I do right now?</p>
      </header>

      {!bannerDismissed && (
        <div className="walkthrough-banner no-print" role="note">
          <button
            type="button"
            className="walkthrough-banner-dismiss"
            onClick={dismissBanner}
            aria-label="Dismiss guide"
          >
            ✕
          </button>
          <p className="walkthrough-banner-text">
            <strong>New here?</strong> Try this: Select 2–3 zones, choose a horizon,
            and click <em>Get Recommendation</em> to see a unified action plan.
          </p>
          <div className="walkthrough-steps" aria-label="Steps">
            {(['Step 1 — Select zones', 'Step 2 — Choose horizon', 'Step 3 — Get Recommendation'] as const).map(
              (label, i, arr) => (
                <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span className="walkthrough-step">{label}</span>
                  {i < arr.length - 1 && (
                    <span className="walkthrough-step-arrow" aria-hidden="true">→</span>
                  )}
                </span>
              )
            )}
          </div>
        </div>
      )}

      <section className="panel-card no-print" style={{ marginBottom: '1rem' }}>
        <div className="panel-card-header">
          <div className="panel-card-title">Configure</div>
          {autoRefreshActive && (
            <span className="panel-muted-inline">auto-refreshing every 120s</span>
          )}
        </div>
        <form onSubmit={handleSubmit} className="form-stack">
          {zonesLoading ? (
            <SkeletonRows count={4} />
          ) : (
            <ZoneMultiSelect
              selectedIds={selectedIds}
              onChange={setSelectedIds}
              max={10}
              label="Zones to analyse"
            />
          )}

          <div>
            <span className="form-label-text">Horizon</span>
            <div className="panel-toggle-row" role="radiogroup" aria-label="Horizon">
              {(['24h', '30d'] as const).map((h) => (
                <button
                  key={h}
                  type="button"
                  role="radio"
                  aria-checked={horizon === h}
                  onClick={() => setHorizon(h)}
                  className={`panel-toggle${horizon === h ? ' panel-toggle-active' : ''}`}
                >
                  {h}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting || selectedIds.length === 0}
            className="panel-btn panel-btn-primary"
          >
            {submitting ? (
              <><span className="btn-spinner" aria-hidden="true" />Analysing…</>
            ) : (
              'Get Recommendation'
            )}
          </button>

          {error && (
            <div className="error-card">
              <div className="error-card-title">Request failed</div>
              <p className="error-card-message">{error}</p>
            </div>
          )}
        </form>
      </section>

      {submitting && !result && (
        <div className="empty-state">
          <p className="empty-state-title">Analysing zones…</p>
        </div>
      )}

      {result && (
        <>
          {/* Verdict */}
          <section
            className={`decision-verdict decision-verdict-${urgency}`}
            style={{ marginBottom: '1rem' }}
          >
            <div className="decision-verdict-header">
              <span className={`decision-urgency-badge decision-urgency-${urgency}`}>
                {URGENCY_LABEL[urgency]}
              </span>
              <CachePill hit={cacheHit} />
              <button
                type="button"
                className="panel-btn no-print"
                style={{ marginLeft: 'auto' }}
                onClick={handlePrint}
              >
                Print Report
              </button>
            </div>
            <p className="decision-verdict-action">
              {result.verdict?.priority_action ?? 'No action available.'}
            </p>
            <p className="decision-verdict-reasoning">
              {result.verdict?.reasoning ?? ''}
            </p>
          </section>

          <div className="panel-grid" style={{ marginBottom: '1rem' }}>
            {/* Confidence */}
            <section className="panel-card">
              <div className="panel-card-header">
                <div className="panel-card-title">Confidence</div>
              </div>
              {result.confidence ? (
                <div className="decision-confidence">
                  <div className="decision-confidence-label-row">
                    <span
                      className="decision-confidence-label"
                      style={{
                        color: confidenceColor(result.confidence.confidence_label),
                      }}
                    >
                      {capitalize(result.confidence.confidence_label)}
                    </span>
                    <span className="decision-confidence-score">
                      {((result.confidence.confidence_score ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="decision-confidence-bar-track">
                    <div
                      className="decision-confidence-bar-fill"
                      style={{
                        width: `${Math.min(
                          100,
                          (result.confidence.confidence_score ?? 0) * 100
                        ).toFixed(1)}%`,
                        backgroundColor: confidenceColor(result.confidence.confidence_label),
                      }}
                    />
                  </div>
                  <p className="panel-muted" style={{ marginTop: '0.4rem', fontSize: '0.78rem' }}>
                    Forecast confidence for the {forecast?.horizon} horizon across{' '}
                    {forecastZones.length} zone(s).
                  </p>
                </div>
              ) : (
                <p className="panel-muted">No confidence data available.</p>
              )}
            </section>

            {/* Active Warnings */}
            <section className="panel-card">
              <div className="panel-card-header">
                <div className="panel-card-title">Active Warnings</div>
                <span className="panel-muted-inline">{warnings.length}</span>
              </div>
              {warnings.length === 0 ? (
                <p className="panel-muted">No active warnings.</p>
              ) : (
                <ul className="decision-warning-list">
                  {warnings.slice(0, 5).map((w, i) => (
                    <li
                      key={i}
                      className="decision-warning-row"
                      style={{ borderLeftColor: SEVERITY_COLOR[w.severity] ?? '#94a3b8' }}
                    >
                      <div className="decision-warning-head">
                        <span
                          className="warning-type-badge"
                          style={{ background: TYPE_BG[w.warning_type] ?? '#f1f5f9' }}
                        >
                          {(w.warning_type ?? '').replace(/_/g, ' ')}
                        </span>
                        <span className="decision-warning-severity">{w.severity}</span>
                      </div>
                      <p className="decision-warning-headline">{w.headline}</p>
                      {w.recommendation_hint && (
                        <p className="warning-hint">{w.recommendation_hint}</p>
                      )}
                    </li>
                  ))}
                  {warnings.length > 5 && (
                    <li
                      className="panel-muted"
                      style={{ listStyle: 'none', paddingTop: '0.4rem' }}
                    >
                      +{warnings.length - 5} more
                    </li>
                  )}
                </ul>
              )}
            </section>
          </div>

          <div className="panel-grid" style={{ marginBottom: '1rem' }}>
            {/* Hotspots */}
            <section className="panel-card">
              <div className="panel-card-header">
                <div className="panel-card-title">Top Hotspots</div>
                <span className="panel-muted-inline">{hotspots.length}</span>
              </div>
              {hotspots.length === 0 ? (
                <p className="panel-muted">No hotspots detected.</p>
              ) : (
                <ol className="decision-hotspot-list">
                  {hotspots.map((h, i) => {
                    const risk = hotspotRisk(h.count ?? 0);
                    return (
                      <li key={i} className="decision-hotspot-row">
                        <span className="panel-rank-idx">{i + 1}.</span>
                        <div className="panel-rank-main">
                          <div className="panel-rank-name">{h.zone_name ?? '—'}</div>
                          <div className="panel-rank-meta">
                            <span>{h.count ?? 0} events</span>
                          </div>
                        </div>
                        <span className="decision-risk-badge" data-risk={risk}>
                          {risk}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </section>

            {/* Patrol */}
            <section className="panel-card">
              <div className="panel-card-header">
                <div className="panel-card-title">Patrol Recommendation</div>
                <span className="panel-muted-inline">
                  {patrol?.units ?? 0} unit{(patrol?.units ?? 0) === 1 ? '' : 's'}
                </span>
              </div>
              {assignments.length === 0 ? (
                <p className="panel-muted">No patrol assignments.</p>
              ) : (
                <ol className="patrol-plan-list">
                  {assignments.map((a, i) => (
                    <li key={a.zone?.id ?? i} className="patrol-plan-row">
                      <span className="panel-rank-idx">{i + 1}.</span>
                      <div className="panel-rank-main">
                        <div className="panel-rank-name">{a.zone?.name ?? '—'}</div>
                        <div className="panel-rank-meta">
                          <span>{a.zone?.zone_type ?? ''}</span>
                          <span>·</span>
                          <span>
                            Priority{' '}
                            {typeof a.priority_score === 'number'
                              ? a.priority_score.toFixed(2)
                              : '—'}
                          </span>
                        </div>
                      </div>
                      <span className="patrol-units-pill">
                        {a.assigned_units} unit{a.assigned_units === 1 ? '' : 's'}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>

          {/* Forecast */}
          <section className="panel-card" style={{ marginBottom: '1rem' }}>
            <div className="panel-card-header">
              <div className="panel-card-title">Forecast Summary</div>
              <span className="panel-muted-inline">
                {forecast?.horizon} · ~{Math.round(forecast?.overall_total ?? 0)} total
              </span>
            </div>
            {forecastZones.length === 0 ? (
              <p className="panel-muted">No forecast data.</p>
            ) : (
              <ul className="decision-forecast-list">
                {forecastZones.map((z, i) => (
                  <li key={i} className="decision-forecast-row">
                    <span className="decision-forecast-zone">{z.zone_id ?? '—'}</span>
                    <span className="decision-forecast-total">
                      ~{Math.round(z.total ?? 0)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Explain (collapsible) */}
          {explainEntries.length > 0 && (
            <section className="panel-card" style={{ marginBottom: '1rem' }}>
              <button
                className="decision-explain-toggle"
                onClick={() => setExplainOpen((o) => !o)}
                aria-expanded={explainOpen}
              >
                <span>Why this recommendation?</span>
                <span className="decision-explain-caret">{explainOpen ? '▲' : '▼'}</span>
              </button>
              {explainOpen && (
                <ul className="explain-list" style={{ marginTop: '0.75rem' }}>
                  {explainEntries.map((e, i) => (
                    <li key={i} className="explain-row">
                      <span className="explain-code">{e.code}</span>
                      <p className="explain-message">{e.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
