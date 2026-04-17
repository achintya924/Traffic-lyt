'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchPolicySimulate,
  fetchZones,
  type PolicyConfidenceLabel,
  type PolicyHorizon,
  type PolicyIntervention,
  type PolicySimulateResponse,
  type ZoneSummary,
} from '@/app/lib/api';
import ZoneMultiSelect from '@/app/components/ZoneMultiSelect';
import CachePill from '@/app/components/CachePill';
import { downloadCsv, csvDate } from '@/app/lib/csv';

const MAX_INTERVENTIONS = 5;
type InterventionType = 'enforcement_intensity' | 'patrol_units' | 'peak_hour_reduction';

type DraftIntervention = {
  key: string;
  type: InterventionType;
  pct: number;
  from_units: number;
  to_units: number;
};

function newDraft(type: InterventionType = 'enforcement_intensity'): DraftIntervention {
  return {
    key: Math.random().toString(36).slice(2),
    type,
    pct: type === 'peak_hour_reduction' ? 30 : 120,
    from_units: 4,
    to_units: 6,
  };
}

function toIntervention(d: DraftIntervention): PolicyIntervention | null {
  if (d.type === 'enforcement_intensity') {
    return { type: 'enforcement_intensity', pct: d.pct };
  }
  if (d.type === 'peak_hour_reduction') {
    return { type: 'peak_hour_reduction', pct: d.pct };
  }
  if (d.from_units === d.to_units) return null;
  return { type: 'patrol_units', from_units: d.from_units, to_units: d.to_units };
}

function confidenceColor(label: PolicyConfidenceLabel | null | undefined): string {
  if (label === 'high') return '#22c55e';
  if (label === 'medium') return '#f59e0b';
  return '#94a3b8';
}

function deltaColor(delta: number): string {
  if (delta < 0) return '#22c55e';
  if (delta > 0) return '#ef4444';
  return '#94a3b8';
}

function formatSigned(n: number, digits = 1): string {
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}`;
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

export default function PolicyPage() {
  const [zones, setZones] = useState<ZoneSummary[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [zonesError, setZonesError] = useState<string | null>(null);
  const [zonesKey, setZonesKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [horizon, setHorizon] = useState<PolicyHorizon>('24h');
  const [interventions, setInterventions] = useState<DraftIntervention[]>([newDraft()]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<PolicySimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    setZonesLoading(true);
    setZonesError(null);
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

  const addIntervention = () => {
    setInterventions((prev) =>
      prev.length >= MAX_INTERVENTIONS ? prev : [...prev, newDraft()]
    );
  };

  const removeIntervention = (key: string) => {
    setInterventions((prev) => prev.filter((i) => i.key !== key));
  };

  const patchIntervention = (key: string, patch: Partial<DraftIntervention>) => {
    setInterventions((prev) =>
      prev.map((i) => (i.key === key ? { ...i, ...patch } : i))
    );
  };

  const handleExportResult = () => {
    if (!result) return;
    const rows: (string | number)[][] = [
      ['zone_id', 'baseline_total', 'simulated_total', 'delta', 'delta_pct', 'confidence_label'],
      ...perZone.map((r) => [r.zone_id, r.baseline, r.simulated, r.delta, r.delta_pct ?? '', confidenceLabel ?? '']),
    ];
    downloadCsv(rows, `policy-simulation-${csvDate()}.csv`);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIds.length === 0) {
      setError('Select at least one zone.');
      return;
    }
    if (interventions.length === 0) {
      setError('Add at least one intervention.');
      return;
    }
    const built: PolicyIntervention[] = [];
    for (const d of interventions) {
      const iv = toIntervention(d);
      if (!iv) {
        setError('Each "Patrol units" intervention needs different from/to values.');
        return;
      }
      built.push(iv);
    }
    const zoneNames = selectedIds
      .map((id) => zonesById.get(id)?.name)
      .filter((n): n is string => !!n);
    if (zoneNames.length === 0) {
      setError('Could not resolve zone names.');
      return;
    }

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetchPolicySimulate(
        { zones: zoneNames, horizon, interventions: built },
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

  const cacheHit = result?.meta?.response_cache?.status === 'hit';
  const overallDelta = result?.delta.overall_delta ?? 0;
  const overallDeltaPct = result?.delta.overall_delta_pct ?? null;
  const confidenceLabel = result?.baseline.confidence?.label ?? null;
  const confidenceScore = result?.baseline.confidence?.score ?? null;

  const perZone = useMemo(() => {
    if (!result) return [] as {
      zone_id: string;
      baseline: number;
      simulated: number;
      delta: number;
      delta_pct: number | null;
      max: number;
    }[];
    const baselineMap = new Map(result.baseline.zones.map((z) => [z.zone_id, z.total]));
    const simulatedMap = new Map(result.simulated.zones.map((z) => [z.zone_id, z.total]));
    const deltaMap = new Map(result.delta.zones.map((z) => [z.zone_id, z]));
    const ids = Array.from(
      new Set([...baselineMap.keys(), ...simulatedMap.keys()])
    );
    const rows = ids.map((id) => {
      const b = baselineMap.get(id) ?? 0;
      const s = simulatedMap.get(id) ?? 0;
      const d = deltaMap.get(id);
      return {
        zone_id: id,
        baseline: b,
        simulated: s,
        delta: d?.delta ?? s - b,
        delta_pct: d?.delta_pct ?? null,
        max: Math.max(b, s, 0.0001),
      };
    });
    return rows;
  }, [result]);

  const maxBarVal = useMemo(
    () => perZone.reduce((m, r) => Math.max(m, r.baseline, r.simulated), 0.0001),
    [perZone]
  );

  return (
    <main className="panel-page">
      <header className="panel-header">
        <h1>Policy Simulator</h1>
        <p className="panel-subtitle">
          Apply interventions to the forecast baseline and compare expected violations.
        </p>
      </header>

      <div className="panel-grid">
        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">Configure</div>
          </div>
          <form onSubmit={handleSubmit} className="form-stack">
            {zonesLoading ? (
              <SkeletonRows count={4} />
            ) : (
              <ZoneMultiSelect
                selectedIds={selectedIds}
                onChange={setSelectedIds}
                max={10}
                label="Zones"
              />
            )}
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

            <div>
              <span className="form-label-text">Horizon</span>
              <div className="panel-toggle-row" role="radiogroup" aria-label="Horizon">
                {(['24h', '30d'] as PolicyHorizon[]).map((h) => (
                  <button
                    key={h}
                    type="button"
                    role="radio"
                    aria-checked={horizon === h}
                    onClick={() => setHorizon(h)}
                    className={`panel-toggle${horizon === h ? ' panel-toggle-active' : ''}`}
                  >
                    {h === '24h' ? '24 hours' : '30 days'}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="form-label-row">
                <span className="form-label-text">
                  Interventions ({interventions.length}/{MAX_INTERVENTIONS})
                </span>
                <button
                  type="button"
                  onClick={addIntervention}
                  disabled={interventions.length >= MAX_INTERVENTIONS}
                  className="panel-btn"
                >
                  + Add
                </button>
              </div>
              <div className="intervention-list">
                {interventions.map((iv) => (
                  <InterventionEditor
                    key={iv.key}
                    draft={iv}
                    onChange={(patch) => patchIntervention(iv.key, patch)}
                    onRemove={() => removeIntervention(iv.key)}
                  />
                ))}
                {interventions.length === 0 && (
                  <p className="panel-muted">No interventions yet. Add one to simulate.</p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting || zonesLoading}
              className="panel-btn panel-btn-primary"
            >
              {submitting ? (
                <><span className="btn-spinner" aria-hidden="true" />Simulating…</>
              ) : (
                'Run simulation'
              )}
            </button>
            {error && (
              <div className="error-card">
                <div className="error-card-title">Simulation failed</div>
                <p className="error-card-message">{error}</p>
              </div>
            )}
          </form>
        </section>

        <section className="panel-card">
          <div className="panel-card-header">
            <div className="panel-card-title">Result</div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {result && (
                <button type="button" className="panel-btn" onClick={handleExportResult}>
                  Export CSV
                </button>
              )}
              {result && <CachePill hit={cacheHit} />}
            </div>
          </div>
          {!result && !submitting && (
            <div className="empty-state">
              <p className="empty-state-title">No simulation yet</p>
              <p className="empty-state-body">Configure zones and interventions, then run a simulation to see results.</p>
            </div>
          )}
          {submitting && (
            <div className="empty-state">
              <p className="empty-state-title">Computing simulation…</p>
            </div>
          )}
          {result && (
            <div className="policy-result-stack">
              <div className="policy-headline-row">
                <div className="policy-headline-block">
                  <div className="panel-muted-inline">Overall delta</div>
                  <div
                    className="policy-headline-value"
                    style={{ color: deltaColor(overallDelta) }}
                  >
                    {formatSigned(overallDelta, 1)}
                    {overallDeltaPct != null && (
                      <span className="policy-headline-pct">
                        {' '}({formatSigned(overallDeltaPct, 1)}%)
                      </span>
                    )}
                  </div>
                  <div className="panel-muted-inline">
                    {overallDelta < 0
                      ? 'expected reduction vs baseline'
                      : overallDelta > 0
                      ? 'expected increase vs baseline'
                      : 'no change vs baseline'}
                  </div>
                </div>
                {confidenceLabel && (
                  <div
                    className="policy-confidence-badge"
                    style={{
                      color: confidenceColor(confidenceLabel),
                      borderColor: confidenceColor(confidenceLabel),
                    }}
                  >
                    <div className="policy-confidence-label">{confidenceLabel}</div>
                    <div className="policy-confidence-score">
                      {confidenceScore != null ? confidenceScore.toFixed(2) : '—'}
                    </div>
                    <div className="panel-muted-inline">confidence</div>
                  </div>
                )}
              </div>

              <div className="policy-totals-row">
                <div>
                  <div className="panel-muted-inline">Baseline</div>
                  <div className="policy-total-value">
                    {result.baseline.overall_total.toFixed(1)}
                  </div>
                </div>
                <div>
                  <div className="panel-muted-inline">Simulated</div>
                  <div className="policy-total-value">
                    {result.simulated.overall_total.toFixed(1)}
                  </div>
                </div>
                <div>
                  <div className="panel-muted-inline">Horizon</div>
                  <div className="policy-total-value">{result.baseline.horizon}</div>
                </div>
              </div>

              {perZone.length > 0 && (
                <div>
                  <div className="form-label-text" style={{ marginBottom: '0.3rem' }}>
                    Per-zone comparison
                  </div>
                  <ul className="policy-zone-list">
                    {perZone.map((row) => (
                      <li key={row.zone_id} className="policy-zone-row">
                        <div className="policy-zone-head">
                          <span className="panel-rank-name">{row.zone_id}</span>
                          <span
                            className="policy-zone-delta"
                            style={{ color: deltaColor(row.delta) }}
                          >
                            {formatSigned(row.delta, 1)}
                            {row.delta_pct != null &&
                              ` (${formatSigned(row.delta_pct, 1)}%)`}
                          </span>
                        </div>
                        <div className="policy-bar-row">
                          <span className="policy-bar-label">baseline</span>
                          <div className="policy-bar-track">
                            <div
                              className="policy-bar-fill policy-bar-baseline"
                              style={{
                                width: `${(row.baseline / maxBarVal) * 100}%`,
                              }}
                            />
                          </div>
                          <span className="policy-bar-value">
                            {row.baseline.toFixed(1)}
                          </span>
                        </div>
                        <div className="policy-bar-row">
                          <span className="policy-bar-label">simulated</span>
                          <div className="policy-bar-track">
                            <div
                              className="policy-bar-fill policy-bar-simulated"
                              style={{
                                width: `${(row.simulated / maxBarVal) * 100}%`,
                                background: deltaColor(row.delta),
                              }}
                            />
                          </div>
                          <span className="policy-bar-value">
                            {row.simulated.toFixed(1)}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {result && result.explain && result.explain.length > 0 && (
        <section className="panel-card panel-card-wide" style={{ marginTop: '1rem' }}>
          <div className="panel-card-header">
            <div className="panel-card-title">Explain</div>
          </div>
          <ul className="explain-list">
            {result.explain.map((e, i) => (
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

function InterventionEditor({
  draft,
  onChange,
  onRemove,
}: {
  draft: DraftIntervention;
  onChange: (patch: Partial<DraftIntervention>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="intervention-row">
      <div className="intervention-row-head">
        <select
          value={draft.type}
          onChange={(e) => onChange({ type: e.target.value as InterventionType })}
          className="panel-input"
          style={{ flex: 1 }}
          aria-label="Intervention type"
        >
          <option value="enforcement_intensity">Enforcement intensity</option>
          <option value="patrol_units">Patrol units</option>
          <option value="peak_hour_reduction">Peak-hour reduction</option>
        </select>
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove intervention"
          className="panel-btn"
        >
          Remove
        </button>
      </div>

      {draft.type === 'enforcement_intensity' && (
        <label className="form-label">
          <span>
            Intensity: <strong>{draft.pct}%</strong> of baseline
          </span>
          <input
            type="range"
            min={0}
            max={200}
            step={1}
            value={draft.pct}
            onChange={(e) => onChange({ pct: Number(e.target.value) })}
          />
          <span className="panel-muted-inline">
            100% = baseline; below reduces enforcement, above increases it.
          </span>
        </label>
      )}

      {draft.type === 'peak_hour_reduction' && (
        <label className="form-label">
          <span>
            Reduction: <strong>{draft.pct}%</strong> of peak-hour violations
          </span>
          <input
            type="range"
            min={0}
            max={90}
            step={1}
            value={draft.pct}
            onChange={(e) => onChange({ pct: Number(e.target.value) })}
          />
        </label>
      )}

      {draft.type === 'patrol_units' && (
        <div className="intervention-units-row">
          <label className="form-label">
            <span>From units</span>
            <input
              type="number"
              min={0}
              max={50}
              value={draft.from_units}
              onChange={(e) => onChange({ from_units: Number(e.target.value) })}
              className="panel-input"
            />
          </label>
          <label className="form-label">
            <span>To units</span>
            <input
              type="number"
              min={0}
              max={50}
              value={draft.to_units}
              onChange={(e) => onChange({ to_units: Number(e.target.value) })}
              className="panel-input"
            />
          </label>
        </div>
      )}
    </div>
  );
}
