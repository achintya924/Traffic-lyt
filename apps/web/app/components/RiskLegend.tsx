'use client';

const THRESHOLDS = { low: '0–33', medium: '34–66', high: '67–100' };
const COLORS = { low: '#22c55e', medium: '#f59e0b', high: '#ef4444' };

export default function RiskLegend() {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 16,
        right: 16,
        padding: '0.5rem 0.75rem',
        background: 'rgba(15, 23, 42, 0.9)',
        borderRadius: 6,
        fontSize: '0.75rem',
        color: '#e2e8f0',
        border: '1px solid #334155',
        zIndex: 1000,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '0.35rem' }}>Risk score</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
        {(Object.entries(THRESHOLDS) as [keyof typeof THRESHOLDS, string][]).map(([level, range]) => (
          <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: COLORS[level],
              }}
            />
            <span style={{ textTransform: 'capitalize' }}>{level}</span>
            <span style={{ color: '#94a3b8', fontSize: '0.7rem' }}>({range})</span>
          </div>
        ))}
      </div>
      <p style={{ margin: '0.35rem 0 0', fontSize: '0.65rem', color: '#64748b' }}>
        Directional effects, not causation.
      </p>
    </div>
  );
}
