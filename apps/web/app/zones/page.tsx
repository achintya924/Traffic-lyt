'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchZones,
  fetchZoneRankings,
  type ZoneSummary,
  type ZoneRankingRow,
  type ZoneRankingsSortBy,
} from '@/app/lib/api';
import ZoneComparePanel from '@/app/components/ZoneComparePanel';
import CachePill from '@/app/components/CachePill';
import { downloadCsv, csvDate } from '@/app/lib/csv';

const SORT_OPTIONS: { value: ZoneRankingsSortBy; label: string }[] = [
  { value: 'risk', label: 'Risk' },
  { value: 'trend', label: 'Trend' },
  { value: 'volume', label: 'Volume' },
];

function trendBadge(direction: string, pct: number) {
  const norm = direction === 'up' ? 'up' : direction === 'down' ? 'down' : 'flat';
  const color = norm === 'up' ? '#f87171' : norm === 'down' ? '#4ade80' : '#94a3b8';
  const symbol = norm === 'up' ? '↑' : norm === 'down' ? '↓' : '·';
  return (
    <span style={{ color, fontSize: '0.75rem' }}>
      {symbol} {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  );
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

function ErrorCard({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="error-card">
      <div className="error-card-title">{title}</div>
      <p className="error-card-message">{message}</p>
      <div className="error-card-footer">
        <button type="button" className="panel-btn" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}

export default function ZonesPage() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [zonesError, setZonesError] = useState<string | null>(null);
  const [zonesKey, setZonesKey] = useState(0);
  const [sortBy, setSortBy] = useState<ZoneRankingsSortBy>('risk');
  const [rankings, setRankings] = useState<ZoneRankingRow[]>([]);
  const [rankingsCacheHit, setRankingsCacheHit] = useState(false);
  const [rankingsLoading, setRankingsLoading] = useState(true);
  const [rankingsError, setRankingsError] = useState<string | null>(null);
  const [rankingsKey, setRankingsKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    const ac = new AbortController();
    setZonesLoading(true);
    setZonesError(null);
    fetchZones(ac.signal)
      .then((res) => setZones(res.zones ?? []))
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setZonesError(e instanceof Error ? e.message : String(e));
        setZones([]);
      })
      .finally(() => setZonesLoading(false));
    return () => ac.abort();
  }, [zonesKey]);

  useEffect(() => {
    const ac = new AbortController();
    setRankingsLoading(true);
    setRankingsError(null);
    fetchZoneRankings({ sort_by: sortBy, limit: 20 }, ac.signal)
      .then((res) => {
        setRankings(res.rankings ?? []);
        setRankingsCacheHit(res.meta?.response_cache === 'hit');
      })
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setRankingsError(e instanceof Error ? e.message : String(e));
        setRankings([]);
      })
      .finally(() => setRankingsLoading(false));
    return () => ac.abort();
  }, [sortBy, rankingsKey]);

  const handleExportRankings = () => {
    const rows: (string | number)[][] = [
      ['zone_id', 'zone_name', 'risk_score', 'trend_direction', 'violation_count', 'wow_delta', 'mom_delta'],
      ...rankings.map((r) => [r.zone_id, r.name, r.score, r.trend_direction, r.total_count, r.percent_change, '']),
    ];
    downloadCsv(rows, `zones-rankings-${csvDate()}.csv`);
  };

  const addZone = useCallback((id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }, []);

  const filteredZones = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return zones;
    return zones.filter(
      (z) => z.name.toLowerCase().includes(q) || z.zone_type.toLowerCase().includes(q)
    );
  }, [zones, filter]);

  return (
    <main className="panel-page">
      <header className="panel-header">
        <h1>Zones</h1>
        <p className="panel-subtitle">
          Browse zones, inspect rankings, and compare analytics side by side.
        </p>
      </header>

      <div className="panel-grid">
        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">Rankings</div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {rankings.length > 0 && (
                <button type="button" className="panel-btn" onClick={handleExportRankings}>
                  Export CSV
                </button>
              )}
              <CachePill hit={rankingsCacheHit} />
            </div>
          </div>
          <div className="panel-toggle-row" role="tablist" aria-label="Sort rankings by">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={sortBy === opt.value}
                onClick={() => setSortBy(opt.value)}
                className={`panel-toggle${sortBy === opt.value ? ' panel-toggle-active' : ''}`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {rankingsLoading && <SkeletonRows count={5} />}
          {!rankingsLoading && rankingsError && (
            <ErrorCard
              title="Failed to load rankings"
              message={rankingsError}
              onRetry={() => setRankingsKey((k) => k + 1)}
            />
          )}
          {!rankingsLoading && !rankingsError && rankings.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">No rankings yet</p>
              <p className="empty-state-body">
                Rankings appear once zone violation data has been ingested.
              </p>
            </div>
          )}
          {!rankingsLoading && !rankingsError && rankings.length > 0 && (
            <ol className="panel-rankings-list">
              {rankings.map((row, i) => {
                const already = selectedIds.includes(row.zone_id);
                return (
                  <li key={row.zone_id} className="panel-rankings-row">
                    <span className="panel-rank-idx">{i + 1}.</span>
                    <div className="panel-rank-main">
                      <div className="panel-rank-name">{row.name}</div>
                      <div className="panel-rank-meta">
                        <span>{row.zone_type}</span>
                        <span>·</span>
                        <span>Total {row.total_count}</span>
                        <span>·</span>
                        {trendBadge(row.trend_direction, row.percent_change)}
                        <span>·</span>
                        <span>
                          Score {sortBy === 'volume' ? row.score : row.score.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => addZone(row.zone_id)}
                      disabled={already}
                      className={`panel-btn${already ? ' panel-btn-disabled' : ''}`}
                    >
                      {already ? 'Added' : 'Compare'}
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">All zones</div>
            <span className="panel-muted-inline">
              {zonesLoading ? '…' : `${filteredZones.length} / ${zones.length}`}
            </span>
          </div>
          <input
            type="search"
            placeholder="Filter by name or type…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="panel-input"
            aria-label="Filter zones"
          />

          {zonesLoading && <SkeletonRows count={4} />}
          {!zonesLoading && zonesError && (
            <ErrorCard
              title="Failed to load zones"
              message={zonesError}
              onRetry={() => setZonesKey((k) => k + 1)}
            />
          )}
          {!zonesLoading && !zonesError && zones.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">No zones found</p>
              <p className="empty-state-body">
                Add zones via the API to start analysing your area.
              </p>
            </div>
          )}
          {!zonesLoading && !zonesError && zones.length > 0 && filteredZones.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">No matching zones</p>
              <p className="empty-state-body">
                No zones match &ldquo;{filter}&rdquo;. Try a different search term.
              </p>
            </div>
          )}
          {!zonesLoading && !zonesError && filteredZones.length > 0 && (
            <ul className="panel-zones-list">
              {filteredZones.map((z) => {
                const already = selectedIds.includes(z.id);
                return (
                  <li key={z.id} className="panel-zone-row">
                    <div className="panel-zone-main">
                      <div className="panel-zone-name">{z.name}</div>
                      <div className="panel-zone-type">{z.zone_type}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => addZone(z.id)}
                      disabled={already}
                      className={`panel-btn${already ? ' panel-btn-disabled' : ''}`}
                    >
                      {already ? 'Added' : 'View'}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="panel-card panel-card-wide">
          <div className="panel-card-header">
            <div className="panel-card-title">Compare</div>
          </div>
          <p className="panel-muted" style={{ marginBottom: '0.5rem' }}>
            Select two or more zones to view totals, trend, and WoW/MoM deltas side by side.
          </p>
          <ZoneComparePanel
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
          />
        </section>
      </div>
    </main>
  );
}
