'use client';

import Link from 'next/link';
import { useCity } from '@/app/lib/CityContext';
import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type StatState = { value: string; loading: boolean };

const FEATURES: { href: string; icon: string; name: string; desc: string }[] = [
  {
    href: '/map',
    icon: '🗺️',
    name: 'Live Map',
    desc: 'Explore violation markers, heatmap overlays, and predicted risk hotspots across NYC in real time.',
  },
  {
    href: '/zones',
    icon: '📍',
    name: 'Zone Analytics',
    desc: 'Browse neighborhood rankings, inspect violation trends, and compare zones side by side.',
  },
  {
    href: '/warnings',
    icon: '⚠️',
    name: 'Early Warnings',
    desc: 'Automatic signals for traffic spikes, week-over-week anomalies, and anomaly cluster events.',
  },
  {
    href: '/patrol',
    icon: '🚔',
    name: 'Patrol Allocation',
    desc: 'Allocate patrol units across zones using a deterministic risk-priority scoring strategy.',
  },
  {
    href: '/policy',
    icon: '⚖️',
    name: 'Policy Simulator',
    desc: 'Model enforcement interventions and preview their impact against the violation forecast baseline.',
  },
  {
    href: '/decision',
    icon: '🎯',
    name: 'Decision Dashboard',
    desc: 'Get a unified "what should I do right now?" recommendation with full supporting evidence.',
  },
];

function StatCard({ label, stat }: { label: string; stat: StatState }) {
  return (
    <div className="landing-stat-card">
      {stat.loading ? (
        <div
          className="skel-line"
          style={{ width: '4rem', height: '2rem', borderRadius: '4px', marginBottom: '0.45rem' }}
        />
      ) : (
        <div className="landing-stat-value">{stat.value}</div>
      )}
      <div className="landing-stat-label">{label}</div>
    </div>
  );
}

export default function Home() {
  const { city } = useCity();
  const cityParam = city !== 'all' ? city : undefined;
  const [violations, setViolations] = useState<StatState>({ value: '-', loading: true });
  const [zones,      setZones]      = useState<StatState>({ value: '-', loading: true });
  const [warnings,   setWarnings]   = useState<StatState>({ value: '-', loading: true });

  useEffect(() => {
    const ac  = new AbortController();
    const sig = ac.signal;

    fetch(`${API_BASE}/violations/stats${cityParam ? '?city=' + cityParam : ''}`, { signal: sig })
      .then((r) => r.json())
      .then((d) => setViolations({ value: (d.total ?? 0).toLocaleString(), loading: false }))
      .catch((e) => { if (e?.name !== 'AbortError') setViolations({ value: '-', loading: false }); });

    fetch(`${API_BASE}/api/zones?limit=200${cityParam ? '&city=' + cityParam : ''}`, { signal: sig })
      .then((r) => r.json())
      .then((d) => setZones({ value: String((d.zones ?? []).length), loading: false }))
      .catch((e) => { if (e?.name !== 'AbortError') setZones({ value: '-', loading: false }); });

    fetch(`${API_BASE}/api/warnings?limit=50${cityParam ? '&city=' + cityParam : ''}`, { signal: sig })
      .then((r) => r.json())
      .then((d) => setWarnings({ value: String((d.warnings ?? []).length), loading: false }))
      .catch((e) => { if (e?.name !== 'AbortError') setWarnings({ value: '-', loading: false }); });

    return () => ac.abort();
  }, [cityParam]);

  return (
    <main className="landing-page">

      {/* ── Hero ───────────────────────────────────────────────── */}
      <section className="landing-hero">
        <div className="landing-hero-inner">
          <div className="landing-hero-badge">Smart City Platform</div>
          <h1 className="landing-hero-title">Traffic-lyt</h1>
          <p className="landing-hero-tagline">
            Real-time traffic violation analytics and predictive decision support for smart cities.
          </p>
          <div className="landing-hero-actions">
            <Link href="/decision" className="landing-cta-btn">
              Get Started →
            </Link>
            <Link href="/map" className="landing-secondary-btn">
              View Map
            </Link>
          </div>
        </div>
      </section>

      {/* ── Live stats ─────────────────────────────────────────── */}
      <section className="landing-stats-section">
        <div className="landing-stats-grid">
          <StatCard label="Violations in database" stat={violations} />
          <StatCard label="Active zones"            stat={zones}      />
          <StatCard label="Active warnings"         stat={warnings}   />
        </div>
      </section>

      {/* ── Feature cards ──────────────────────────────────────── */}
      <section className="landing-features-section">
        <h2 className="landing-section-title">Everything you need</h2>
        <div className="landing-features-grid">
          {FEATURES.map((f) => (
            <div key={f.href} className="landing-feature-card">
              <span className="landing-feature-icon" aria-hidden="true">{f.icon}</span>
              <div className="landing-feature-name">{f.name}</div>
              <p className="landing-feature-desc">{f.desc}</p>
              <Link href={f.href} className="landing-feature-link">
                Open →
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ─────────────────────────────────────────── */}
      <section className="landing-bottom-cta">
        <h2 className="landing-bottom-cta-title">Ready to take action?</h2>
        <p className="landing-bottom-cta-sub">
          Select your zones, set a horizon, and get a unified recommendation in seconds.
        </p>
        <Link href="/decision" className="landing-cta-btn">
          Open Decision Dashboard →
        </Link>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="landing-footer">
        <span>Traffic-lyt</span>
        <span className="landing-footer-sep">·</span>
        <a
          href="https://github.com/achintya924/Traffic-lyt"
          target="_blank"
          rel="noopener noreferrer"
          className="landing-footer-link"
        >
          github.com/achintya924/Traffic-lyt
        </a>
      </footer>

    </main>
  );
}
