'use client';

type CachePillProps = {
  hit?: boolean;
};

export default function CachePill({ hit }: CachePillProps) {
  if (typeof window === 'undefined') return null;
  if (process.env.NODE_ENV !== 'development') return null;
  if (!hit) return null;

  return (
    <span
      style={{
        padding: '0.1rem 0.35rem',
        borderRadius: 4,
        background: '#14532d',
        color: '#86efac',
        fontSize: '0.65rem',
        marginLeft: '0.35rem',
      }}
    >
      Cached
    </span>
  );
}
