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

export default function ZonesPage() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [zonesError, setZonesError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<ZoneRankingsSortBy>('risk');
  const [rankings, setRankings] = useState<ZoneRankingRow[]>([]);
  const [rankingsCacheHit, setRankingsCacheHit] = useState(false);
  const [rankingsLoading, setRankingsLoading] = useState(true);
  const [rankingsError, setRankingsError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    const ac = new AbortController();
    setZonesLoading(true);
    setZonesError(null);
    fetchZones(ac.signal)
      .then((res) => {
        setZones(res.zones ?? []);
      })
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setZonesError(e instanceof Error ? e.message : String(e));
        setZones([]);
      })
      .finally(() => setZonesLoading(false));
    return () => ac.abort();
  }, []);

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
  }, [sortBy]);

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
            <CachePill hit={rankingsCacheHit} />
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
          {rankingsLoading && <p className="panel-muted">Loading rankings…</p>}
          {rankingsError && <p className="panel-error">{rankingsError}</p>}
          {!rankingsLoading && !rankingsError && rankings.length === 0 && (
            <p className="panel-muted">No rankings available.</p>
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
          {zonesLoading && <p className="panel-muted">Loading zones…</p>}
          {zonesError && <p className="panel-error">{zonesError}</p>}
          {!zonesLoading && !zonesError && filteredZones.length === 0 && (
            <p className="panel-muted">No zones match.</p>
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
