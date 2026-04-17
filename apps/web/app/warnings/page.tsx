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
    return (zid == null || zid === warning.zone.id) &&
      (wtype == null || wtype === warning.warning_type);
  });
  return match?.message ?? null;
}

type LoadState = 'initial' | 'loading' | 'ready' | 'error';

export default function WarningsPage() {
  const [warnings, setWarnings] = useState<WarningCard[]>([]);
  const [explain, setExplain] = useState<WarningsExplainEntry[]>([]);
  const [cacheHit, setCacheHit] = useState(false);
  const [anchorTs, setAnchorTs] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('initial');
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [severityFilter, setSeverityFilter] = useState<'all' | WarningSeverity>('all');

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
  }, []);

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
              {k === 'all' ? `All (${warnings.length})` : `${k[0].toUpperCase()}${k.slice(1)} (${counts[k]})`}
            </button>
          ))}
        </div>
      </header>

      {loadState === 'loading' && warnings.length === 0 && (
        <p className="panel-muted">Loading warnings…</p>
      )}
      {loadState === 'error' && (
        <div className="status err" style={{ marginTop: '1rem' }}>
          <div className="label">Error</div>
          <p>{error}</p>
        </div>
      )}
      {loadState === 'ready' && filtered.length === 0 && (
        <p className="panel-muted">No active warnings for the current window.</p>
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
