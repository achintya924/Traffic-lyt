'use client';

import { useState } from 'react';
import type { MetaEval, MetaExplain, MetaExplainFeature } from '@/app/lib/types';

type RiskPanelProps = {
  evalMeta?: MetaEval;
  explainMeta?: MetaExplain;
  forecastTotal?: number;
  horizon?: number;
};

function ModelEval({ evalMeta }: { evalMeta: MetaEval }) {
  if (!evalMeta || !evalMeta.metrics) return null;
  const m = evalMeta.metrics;
  const mae = m.mae;
  const mape = m.mape;
  const testPoints = evalMeta.test_points;
  const trainPoints = evalMeta.train_points;
  const horizon = evalMeta.horizon;
  const granularity = evalMeta.granularity;

  if (mae == null && mape == null && !testPoints && !trainPoints) return null;

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>
        Model evaluation
      </div>
      <div
        style={{
          padding: '0.35rem 0.5rem',
          background: '#1e293b',
          borderRadius: 4,
          fontSize: '0.75rem',
          color: '#94a3b8',
        }}
      >
        {mae != null && <span>MAE: {mae.toFixed(2)}</span>}
        {mae != null && mape != null && <span style={{ marginLeft: '0.75rem' }}>|</span>}
        {mape != null && <span style={{ marginLeft: '0.75rem' }}>MAPE: {mape.toFixed(1)}%</span>}
        {(testPoints ?? trainPoints ?? horizon) != null && (
          <div style={{ marginTop: '0.25rem' }}>
            {testPoints != null && <span>Test points: {testPoints}</span>}
            {trainPoints != null && <span style={{ marginLeft: '0.75rem' }}>Train: {trainPoints}</span>}
            {horizon != null && <span style={{ marginLeft: '0.75rem' }}>Horizon: {horizon}{granularity === 'hour' ? 'h' : 'd'}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function FeatureRow({ f }: { f: MetaExplainFeature }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontSize: '0.75rem',
        marginTop: '0.2rem',
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: 1,
          background: f.effect === 'increase' ? '#22c55e' : '#ef4444',
          flexShrink: 0,
        }}
      />
      <span style={{ color: '#e2e8f0', flex: 1 }}>{f.name}</span>
      <span style={{ color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>
        {f.weight.toFixed(3)}
      </span>
    </div>
  );
}

function TopDrivers({ explainMeta }: { explainMeta: MetaExplain }) {
  if (!explainMeta?.features?.length) return null;

  const [showAll, setShowAll] = useState(false);
  const features = explainMeta.features;
  const displayed = showAll ? features.slice(0, 10) : features.slice(0, 5);
  const hasMore = features.length > 5;

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>
        Top drivers
      </div>
      <div
        style={{
          padding: '0.35rem 0.5rem',
          background: '#1e293b',
          borderRadius: 4,
        }}
      >
        {displayed.map((f, i) => (
          <FeatureRow key={`${f.raw_feature}-${i}`} f={f} />
        ))}
        {hasMore && (
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            style={{
              marginTop: '0.35rem',
              padding: '0.1rem 0.35rem',
              fontSize: '0.7rem',
              background: 'transparent',
              color: '#64748b',
              border: '1px solid #334155',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            {showAll ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>
    </div>
  );
}

export default function RiskPanel({
  evalMeta,
  explainMeta,
  forecastTotal,
  horizon,
}: RiskPanelProps) {
  const hasEval = evalMeta && (evalMeta.metrics?.mae != null || evalMeta.metrics?.mape != null || evalMeta.test_points != null);
  const hasExplain = explainMeta?.features?.length;

  if (!hasEval && !hasExplain && forecastTotal == null) return null;

  return (
    <div
      style={{
        marginTop: '0.75rem',
        paddingTop: '0.5rem',
        borderTop: '1px solid #334155',
      }}
    >
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '0.25rem' }}>
        Risk forecast
      </div>
      {forecastTotal != null && horizon != null && (
        <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: 0 }}>
          Expected ~{forecastTotal} violations over next {horizon}h
        </p>
      )}
      <ModelEval evalMeta={evalMeta ?? null} />
      <TopDrivers explainMeta={explainMeta ?? null} />
    </div>
  );
}
