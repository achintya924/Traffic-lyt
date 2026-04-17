'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  fetchWarnings,
  type WarningCard,
  type WarningsExplainEntry,
  type WarningSeverity,
  type WarningType,
} from '@/app/lib/api';
import CachePill from '@/app/components/CachePill';

const REFRESH_MS = 60_000;

const SEVERITY_COLOR: Record<WarningSeverity, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#22c55e',
};

const TYPE_LABEL: Record<string, string> = {
  trend_up: 'Trend up',
  wow_spike: 'WoW spike',
  mom_spike: 'MoM spike',
  anomaly_cluster: 'Anomaly cluster',
};

const TYPE_BG: Record<string, string> = {
  trend_up: '#7c2d12',
  wow_spike: '#7f1d1d',
  mom_spike: '#581c87',
  anomaly_cluster: '#0c4a6e',
};

function typeLabel(t: string): string {
  return TYPE_LABEL[t] ?? t.replace(/_/g, ' ');
}

function typeBg(t: string): string {
  return TYPE_BG[t] ?? '#334155';
}

function explainFor(
  warning: WarningCard,
  explain: WarningsExplainEntry[] | undefined
): string | null {
  if (!explain || explain.length === 0) return null;
  const code = `warning_${warning.warning_type}`;
  const match = explain.find((e) => {
    if (e.code !== code) return false;
    const d = e.details ?? {};
    const zid = (d as { zone_id?: number }).zone_id;
    const wtype = (d as { warning_type?: string }).warning_type;
    return (
      (zid == null || zid === warning.zone.id) &&
      (wtype == null || wtype === warning.warning_type)
    );
  });
  return match?.message ?? null;
}

type LoadState = 'initial' | 'loading' | 'ready' | 'error';

function SkeletonGrid() {
  return (
    <div className="warnings-grid" style={{ marginTop: '0.75rem' }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="warning-card">
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.1rem' }}>
            <div className="skel-line" style={{ width: '5rem' }} />
            <div className="skel-line" style={{ width: '2.5rem' }} />
          </div>
          <div className="skel-line" style={{ width: '55%' }} />
          <div className="skel-line" style={{ width: '85%' }} />
          <div className="skel-line" style={{ width: '45%' }} />
        </div>
      ))}
    </div>
  );
}

export default function WarningsPage() {
  const [warnings, setWarnings] = useState<WarningCard[]>([]);
  const [explain, setExplain] = useState<WarningsExplainEntry[]>([]);
  const [cacheHit, setCacheHit] = useState(false);
  const [anchorTs, setAnchorTs] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('initial');
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [severityFilter, setSeverityFilter] = useState<'all' | WarningSeverity>('all');
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let ac: AbortController | null = null;

    const load = (initial: boolean) => {
      ac?.abort();
      ac = new AbortController();
      if (initial) setLoadState('loading');
      fetchWarnings({ limit: 50 }, ac.signal)
        .then((res) => {
          if (cancelled) return;
          setWarnings(res.warnings ?? []);
          setExplain(res.explain ?? []);
          setCacheHit(res.meta?.response_cache === 'hit');
          setAnchorTs((res.meta?.anchor_ts as string | null | undefined) ?? null);
          setLastUpdated(Date.now());
          setLoadState('ready');
          setError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          if ((e as { name?: string })?.name === 'AbortError') return;
          setError(e instanceof Error ? e.message : String(e));
          setLoadState('error');
        });
    };

    load(true);
    const interval = window.setInterval(() => load(false), REFRESH_MS);
    return () => {
      cancelled = true;
      ac?.abort();
      window.clearInterval(interval);
    };
  }, [retryCount]);

  const filtered = useMemo(() => {
    if (severityFilter === 'all') return warnings;
    return warnings.filter((w) => w.severity === severityFilter);
  }, [warnings, severityFilter]);

  const counts = useMemo(() => {
    const c: Record<WarningSeverity, number> = { high: 0, medium: 0, low: 0 };
    for (const w of warnings) c[w.severity] = (c[w.severity] ?? 0) + 1;
    return c;
  }, [warnings]);

  return (
    <main className="panel-page">
      <header className="panel-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
          <h1>Warnings</h1>
          <CachePill hit={cacheHit} />
          <span className="panel-muted-inline">
            Auto-refreshes every 60s
            {lastUpdated && ` · updated ${new Date(lastUpdated).toLocaleTimeString()}`}
          </span>
        </div>
        <p className="panel-subtitle">
          Active early-warning signals across zones.
          {anchorTs && <> Anchor: <code>{anchorTs}</code></>}
        </p>
        <div className="panel-toggle-row" role="tablist" aria-label="Filter by severity">
          {(['all', 'high', 'medium', 'low'] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={severityFilter === k}
              onClick={() => setSeverityFilter(k)}
              className={`panel-toggle${severityFilter === k ? ' panel-toggle-active' : ''}`}
            >
              {k === 'all'
                ? `All (${warnings.length})`
                : `${k[0].toUpperCase()}${k.slice(1)} (${counts[k]})`}
            </button>
          ))}
        </div>
      </header>

      {loadState === 'loading' && warnings.length === 0 && <SkeletonGrid />}

      {loadState === 'error' && (
        <div className="error-card" style={{ marginTop: '0.75rem' }}>
          <div className="error-card-title">Failed to load warnings</div>
          <p className="error-card-message">{error}</p>
          <div className="error-card-footer">
            <button
              type="button"
              className="panel-btn"
              onClick={() => setRetryCount((c) => c + 1)}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {loadState === 'ready' && filtered.length === 0 && severityFilter === 'all' && (
        <div className="empty-state" style={{ marginTop: '0.5rem' }}>
          <p className="empty-state-title">No active warnings</p>
          <p className="empty-state-body">
            All zones are within normal parameters. Warnings appear when thresholds are exceeded.
          </p>
        </div>
      )}

      {loadState === 'ready' && filtered.length === 0 && severityFilter !== 'all' && (
        <div className="empty-state" style={{ marginTop: '0.5rem' }}>
          <p className="empty-state-title">No {severityFilter} warnings</p>
          <p className="empty-state-body">
            There are no {severityFilter}-severity warnings right now.
            {warnings.length > 0 && ' Warnings exist at other severity levels.'}
          </p>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="warnings-grid">
          {filtered.map((w, i) => {
            const sevColor = SEVERITY_COLOR[w.severity] ?? '#94a3b8';
            const explainMsg = explainFor(w, explain);
            return (
              <article
                key={`${w.zone.id}-${w.warning_type}-${i}`}
                className="warning-card"
                style={{ borderLeftColor: sevColor }}
              >
                <div className="warning-card-header">
                  <span
                    className="warning-type-badge"
                    style={{ background: typeBg(w.warning_type) }}
                  >
                    {typeLabel(w.warning_type as WarningType)}
                  </span>
                  <span
                    className="warning-severity"
                    style={{ color: sevColor, borderColor: sevColor }}
                  >
                    {w.severity}
                  </span>
                </div>
                <div className="warning-zone">{w.zone.name}</div>
                <div className="warning-zone-type">{w.zone.zone_type}</div>
                <p className="warning-headline">{w.headline}</p>
                {explainMsg && <p className="warning-explain">{explainMsg}</p>}
                {w.recommendation_hint && (
                  <p className="warning-hint">{w.recommendation_hint}</p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </main>
  );
}
