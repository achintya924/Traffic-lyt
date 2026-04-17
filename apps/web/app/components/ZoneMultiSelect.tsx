'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchZones, type ZoneSummary } from '@/app/lib/api';

type ZoneMultiSelectProps = {
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  max?: number;
  label?: string;
};

export default function ZoneMultiSelect({
  selectedIds,
  onChange,
  max = 10,
  label = 'Zones',
}: ZoneMultiSelectProps) {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    fetchZones(ac.signal)
      .then((res) => setZones(res.zones ?? []))
      .catch((e) => {
        if ((e as { name?: string })?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : String(e));
        setZones([]);
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, []);

  const zonesById = useMemo(() => {
    const m = new Map<number, ZoneSummary>();
    zones.forEach((z) => m.set(z.id, z));
    return m;
  }, [zones]);

  const available = useMemo(
    () => zones.filter((z) => !selectedIds.includes(z.id)),
    [zones, selectedIds]
  );

  const add = useCallback(
    (id: number) => {
      if (selectedIds.length >= max) return;
      if (selectedIds.includes(id)) return;
      onChange([...selectedIds, id]);
    },
    [selectedIds, onChange, max]
  );

  const remove = useCallback(
    (id: number) => {
      onChange(selectedIds.filter((x) => x !== id));
    },
    [selectedIds, onChange]
  );

  const atMax = selectedIds.length >= max;

  return (
    <div className="zone-multiselect">
      <div className="zone-multiselect-header">
        <span className="zone-multiselect-label">{label}</span>
        <span className="panel-muted-inline">
          {selectedIds.length} / {max}
        </span>
      </div>
      {loading && <p className="panel-muted">Loading zones…</p>}
      {error && <p className="panel-error">{error}</p>}
      {!loading && !error && (
        <>
          <select
            value=""
            disabled={atMax}
            onChange={(e) => {
              const v = e.target.value;
              if (v) add(Number(v));
              e.target.value = '';
            }}
            className="panel-input"
            aria-label="Add zone"
          >
            <option value="">{atMax ? `Max ${max} zones reached` : 'Add zone…'}</option>
            {available.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name} ({z.zone_type})
              </option>
            ))}
          </select>
          <div className="zone-chips">
            {selectedIds.map((id) => {
              const z = zonesById.get(id);
              return (
                <span key={id} className="zone-chip">
                  <span className="zone-chip-label">{z ? z.name : `Zone ${id}`}</span>
                  <button
                    type="button"
                    onClick={() => remove(id)}
                    aria-label={`Remove ${z?.name ?? `zone ${id}`}`}
                    className="zone-chip-remove"
                  >
                    ×
                  </button>
                </span>
              );
            })}
            {selectedIds.length === 0 && (
              <span className="panel-muted-inline">No zones selected.</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
