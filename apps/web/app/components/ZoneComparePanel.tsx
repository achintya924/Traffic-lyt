'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  API_BASE,
  fetchZoneAnalytics,
  fetchZoneCompare,
  fetchZones,
  fetchZoneById,
  type ZoneSummary,
  type ZoneAnalyticsResponse,
  type ZoneCompareResponse,
} from '@/app/lib/api';
import CachePill from '@/app/components/CachePill';

const MAX_ZONES = 5;
const DEBOUNCE_MS = 200;

export type ZoneCompareBounds = { south: number; north: number; west: number; east: number };

type ZoneComparePanelProps = {
  selectedIds: number[];
  onSelectionChange: (ids: number[]) => void;
  onZoomToZone?: (bounds: ZoneCompareBounds) => void;
};

type ZoneCardData = {
  zone: ZoneSummary | null;
  analytics: ZoneAnalyticsResponse | null;
  wow: ZoneCompareResponse | null;
  mom: ZoneCompareResponse | null;
  loading: boolean;
  error: string | null;
};

function ZoneCard({
  zoneId,
  data,
  onZoomTo,
  onRemove,
}: {
  zoneId: number;
  data: ZoneCardData;
  onZoomTo: () => void;
  onRemove: () => void;
}) {
  const { zone, analytics, wow, mom, loading, error } = data;
  const name = zone?.name ?? `Zone ${zoneId}`;

  const cardContent = (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0' }}>{name}</span>
        {!loading && !error && (
          <CachePill
            hit={
              analytics?.meta?.response_cache === 'hit' ||
              wow?.meta?.response_cache === 'hit' ||
              mom?.meta?.response_cache === 'hit'
            }
          />
        )}
      </div>
      {loading && <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: '#64748b' }}>Loading…</div>}
      {error && <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: '#f87171' }}>{error}</div>}
      {!loading && !error && (
        <>
          <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: '#94a3b8', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            <span>Total: {analytics?.summary?.total_count ?? 0}</span>
            <span>
              Trend: {analytics?.summary?.trend_direction ?? '—'}{' '}
              {typeof analytics?.summary?.percent_change === 'number' && analytics.summary.percent_change !== 0 &&
                `(${analytics.summary.percent_change > 0 ? '+' : ''}${analytics.summary.percent_change}%)`}
            </span>
            {wow?.delta?.delta_percent != null && <span>WoW: {wow.delta.delta_percent > 0 ? '+' : ''}{wow.delta.delta_percent}%</span>}
            {mom?.delta?.delta_percent != null && <span>MoM: {mom.delta.delta_percent > 0 ? '+' : ''}{mom.delta.delta_percent}%</span>}
          </div>
          <div style={{ marginTop: '0.25rem', fontSize: '0.65rem', color: '#64748b' }}>Click to zoom to zone</div>
        </>
      )}
    </>
  );

  if (loading) {
    return (
      <div
        style={{
          padding: '0.6rem 0.75rem',
          background: '#334155',
          borderRadius: 6,
          minHeight: 100,
          position: 'relative',
        }}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label="Remove zone"
          style={{
            position: 'absolute',
            top: 4,
            right: 4,
            padding: '0.15rem 0.35rem',
            fontSize: '0.7rem',
            background: '#475569',
            color: '#e2e8f0',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          ×
        </button>
        {cardContent}
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: '0.6rem 0.75rem',
          background: '#334155',
          borderRadius: 6,
          borderLeft: '3px solid #ef4444',
          position: 'relative',
        }}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label="Remove zone"
          style={{
            position: 'absolute',
            top: 4,
            right: 4,
            padding: '0.15rem 0.35rem',
            fontSize: '0.7rem',
            background: '#475569',
            color: '#e2e8f0',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          ×
        </button>
        {cardContent}
      </div>
    );
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={onZoomTo}
        style={{
          width: '100%',
          textAlign: 'left',
          padding: '0.6rem 0.75rem',
          paddingRight: '1.75rem',
          background: '#334155',
          borderRadius: 6,
          border: '1px solid #475569',
          cursor: 'pointer',
          color: 'inherit',
        }}
      >
        {cardContent}
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        aria-label="Remove zone"
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          padding: '0.15rem 0.35rem',
          fontSize: '0.7rem',
          background: '#475569',
          color: '#e2e8f0',
          border: 'none',
          borderRadius: 4,
          cursor: 'pointer',
        }}
      >
        ×
      </button>
    </div>
  );
}

export default function ZoneComparePanel({
  selectedIds,
  onSelectionChange,
  onZoomToZone,
}: ZoneComparePanelProps) {
  const [zonesList, setZonesList] = useState<ZoneSummary[]>([]);
  const [zonesListLoading, setZonesListLoading] = useState(true);
  const [zonesListError, setZonesListError] = useState<string | null>(null);
  const [cardData, setCardData] = useState<Record<number, ZoneCardData>>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    setZonesListLoading(true);
    setZonesListError(null);
    fetchZones(ac.signal)
      .then((res) => {
        setZonesList(res.zones ?? []);
      })
      .catch((e) => {
        if ((e as { name?: string })?.name !== 'AbortError') {
          setZonesListError(e instanceof Error ? e.message : String(e));
          setZonesList([]);
        }
      })
      .finally(() => setZonesListLoading(false));
    return () => ac.abort();
  }, []);

  const fetchForZone = useCallback(
    async (id: number, signal: AbortSignal) => {
      setCardData((prev) => ({
        ...prev,
        [id]: {
          ...prev[id],
          zone: prev[id]?.zone ?? null,
          loading: true,
          error: null,
        },
      }));
      try {
        const [analyticsRes, wowRes, momRes] = await Promise.all([
          fetchZoneAnalytics(id, { granularity: 'day' }, signal),
          fetchZoneCompare(id, 'wow', { granularity: 'day' }, signal),
          fetchZoneCompare(id, 'mom', { granularity: 'day' }, signal),
        ]);
        if (signal.aborted) return;
        const zoneFromAnalytics = analyticsRes.zone
          ? { id: analyticsRes.zone.id, name: analyticsRes.zone.name, zone_type: analyticsRes.zone.zone_type }
          : null;
        setCardData((prev) => ({
          ...prev,
          [id]: {
            zone: zoneFromAnalytics,
            analytics: analyticsRes,
            wow: wowRes,
            mom: momRes,
            loading: false,
            error: null,
          },
        }));
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setCardData((prev) => ({
          ...prev,
          [id]: {
            ...prev[id],
            zone: prev[id]?.zone ?? null,
            analytics: null,
            wow: null,
            mom: null,
            loading: false,
            error: e instanceof Error ? e.message : String(e),
          },
        }));
      }
    },
    []
  );

  useEffect(() => {
    if (selectedIds.length === 0) {
      setCardData({});
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      if (abortRef.current) abortRef.current.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      const signal = ac.signal;
      selectedIds.forEach((id) => fetchForZone(id, signal));
      return () => ac.abort();
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [selectedIds.join(','), fetchForZone]);

  const handleZoomTo = useCallback(
    async (zoneId: number) => {
      if (!onZoomToZone) return;
      try {
        const zone = await fetchZoneById(zoneId);
        const b = zone.bbox;
        if (b && typeof b.minx === 'number' && typeof b.miny === 'number' && typeof b.maxx === 'number' && typeof b.maxy === 'number') {
          onZoomToZone({ south: b.miny, north: b.maxy, west: b.minx, east: b.maxx });
        }
      } catch {
        // ignore
      }
    },
    [onZoomToZone]
  );

  const addZone = useCallback(
    (id: number) => {
      if (selectedIds.includes(id) || selectedIds.length >= MAX_ZONES) return;
      onSelectionChange([...selectedIds, id]);
    },
    [selectedIds, onSelectionChange]
  );

  const removeZone = useCallback(
    (id: number) => {
      onSelectionChange(selectedIds.filter((x) => x !== id));
    },
    [selectedIds, onSelectionChange]
  );

  const availableToAdd = zonesList.filter((z) => !selectedIds.includes(z.id));

  return (
    <div style={{ background: '#1e293b', borderRadius: 8, padding: '0.75rem 1rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.5rem' }}>
        Compare zones (max {MAX_ZONES})
      </div>
      {zonesListLoading && (
        <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: 0 }}>Loading zones…</p>
      )}
      {zonesListError && (
        <p style={{ fontSize: '0.75rem', color: '#f87171', margin: 0 }}>{zonesListError}</p>
      )}
      {!zonesListLoading && !zonesListError && zonesList.length > 0 && (
        <div style={{ marginBottom: '0.5rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value=""
            onChange={(e) => {
              const v = e.target.value;
              if (v) addZone(Number(v));
              e.target.value = '';
            }}
            style={{
              padding: '0.35rem 0.5rem',
              fontSize: '0.75rem',
              background: '#334155',
              color: '#e2e8f0',
              border: '1px solid #475569',
              borderRadius: 4,
              flex: 1,
              minWidth: 120,
            }}
          >
            <option value="">Add zone…</option>
            {availableToAdd.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name} ({z.zone_type})
              </option>
            ))}
          </select>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {selectedIds.map((id) => (
          <ZoneCard
            key={id}
            zoneId={id}
            data={cardData[id] ?? { zone: null, analytics: null, wow: null, mom: null, loading: true, error: null }}
            onZoomTo={() => handleZoomTo(id)}
            onRemove={() => removeZone(id)}
          />
        ))}
      </div>
      {selectedIds.length === 0 && !zonesListLoading && (
        <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: 0 }}>Select zones above to compare.</p>
      )}
    </div>
  );
}
