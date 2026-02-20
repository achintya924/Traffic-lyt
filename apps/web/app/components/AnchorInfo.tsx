'use client';

import type { MetaTimeContract } from '@/app/lib/types';

type AnchorInfoProps = {
  meta?: Partial<MetaTimeContract> | null;
  label?: string;
};

function formatTs(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return String(ts);
  }
}

function parseWindow(ew: MetaTimeContract['effective_window']): { start?: string; end?: string } {
  if (!ew) return {};
  if (typeof ew === 'object') {
    const o = ew as { start_ts?: string; end_ts?: string; start?: string; end?: string };
    return { start: o.start_ts ?? o.start, end: o.end_ts ?? o.end };
  }
  if (typeof ew === 'string') {
    const m = ew.match(/(.+?)\s*\.\.\.\s*(.+)/);
    return m ? { start: m[1].trim(), end: m[2].trim() } : {};
  }
  return {};
}

export default function AnchorInfo({ meta, label = 'Data' }: AnchorInfoProps) {
  if (!meta) return null;

  const anchor = meta.anchor_ts ?? meta.data_max_ts;
  const windowSource = meta.window_source ?? 'unknown';
  const { start, end } = parseWindow(meta.effective_window);
  const isAnchored = windowSource === 'anchored';

  if (!anchor && !start && !end) return null;

  return (
    <div
      style={{
        fontSize: '0.75rem',
        color: '#94a3b8',
        marginTop: '0.25rem',
        padding: '0.35rem 0.5rem',
        background: '#1e293b',
        borderRadius: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
        <span>{label} anchored to:</span>
        <code style={{ fontSize: '0.7rem', color: '#e2e8f0' }}>
          {formatTs(anchor)}
        </code>
        <span
          style={{
            padding: '0.1rem 0.35rem',
            borderRadius: 4,
            background: isAnchored ? '#334155' : '#475569',
            color: '#cbd5e1',
            fontSize: '0.65rem',
          }}
        >
          {isAnchored ? 'anchored' : 'absolute'}
        </span>
      </div>
      {(start || end) && (
        <div style={{ marginTop: '0.25rem', fontSize: '0.7rem' }}>
          Window: {formatTs(start ?? undefined)} → {formatTs(end ?? undefined)}
        </div>
      )}
      <div style={{ marginTop: '0.15rem', fontSize: '0.65rem', color: '#64748b' }}>
        Timezone: UTC
      </div>
    </div>
  );
}
