/* global React, ReactDOM, Globe */

const FEATURES = [
  {
    href: '/map',
    icon: '🗺️',
    name: 'Map & Heatmap',
    desc: 'Explore violation markers, heatmap overlays, and predicted risk hotspots in real time.',
    tag: 'GEO',
  },
  {
    href: '/zones',
    icon: '📍',
    name: 'Zone Analytics',
    desc: 'Browse neighborhood rankings, inspect trends, and compare zones side by side.',
    tag: 'INSIGHTS',
  },
  {
    href: '/warnings',
    icon: '⚠️',
    name: 'Early Warnings',
    desc: 'Automatic signals for traffic spikes, week-over-week anomalies, and cluster events.',
    tag: 'ALERTS',
  },
  {
    href: '/patrol',
    icon: '🚔',
    name: 'Patrol Allocation',
    desc: 'Allocate units across zones using a deterministic risk-priority scoring strategy.',
    tag: 'OPS',
  },
  {
    href: '/policy',
    icon: '⚖️',
    name: 'Policy Simulator',
    desc: 'Model enforcement interventions and preview their impact against forecast baselines.',
    tag: 'SIM',
  },
  {
    href: '/decision',
    icon: '🎯',
    name: 'Decision Dashboard',
    desc: 'Get a unified "what should I do right now?" recommendation with full evidence.',
    tag: 'COMMAND',
  },
];

// ───────── Sparkline (SVG) ─────────
const Spark = ({ data, color = '#2E86C1' }) => {
  const w = 96, h = 32, pad = 2;
  const min = Math.min(...data), max = Math.max(...data);
  const range = Math.max(1, max - min);
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - 2 * pad);
    const y = h - pad - ((v - min) / range) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg className="stat-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`g-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`${pad},${h-pad} ${pts} ${w-pad},${h-pad}`}
        fill={`url(#g-${color})`}
      />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
};

// ───────── Stat Card ─────────
const StatCard = ({ label, stat, trend, spark, color }) => (
  <div className="stat-card">
    <div className="stat-head">
      <div className="stat-label">{label}</div>
      <span className="stat-pill">LIVE</span>
    </div>
    {stat.loading ? (
      <div className="skel" />
    ) : (
      <div className="stat-value">{stat.value}</div>
    )}
    {!stat.loading && trend && (
      <div className="stat-trend">
        <span className={trend.dir}>{trend.dir === 'up' ? '↑' : '↓'} {trend.pct}</span>
        {' '}vs last 7d
      </div>
    )}
    {!stat.loading && spark && <Spark data={spark} color={color} />}
  </div>
);

// ───────── Nav ─────────
const Nav = () => (
  <nav className="nav">
    <a className="nav-brand" href="/">
      <span className="brand-dot"></span>
      Traffic-lyt
    </a>
    <div className="nav-links">
      <a className="nav-link" href="/map">Map</a>
      <a className="nav-link" href="/zones">Zones</a>
      <a className="nav-link" href="/warnings">Warnings</a>
      <a className="nav-link" href="/patrol">Patrol</a>
      <a className="nav-link" href="/policy">Policy</a>
      <a className="nav-cta" href="/decision">Decision →</a>
    </div>
  </nav>
);

// ───────── App ─────────
const App = () => {
  const [violations, setViolations] = React.useState({ value: '-', loading: true });
  const [zones,      setZones]      = React.useState({ value: '-', loading: true });
  const [warnings,   setWarnings]   = React.useState({ value: '-', loading: true });

  // Demo: simulate API fetch with realistic numbers (the real page.tsx hits the actual API)
  React.useEffect(() => {
    const t1 = setTimeout(() => setViolations({ value: (1284371).toLocaleString(), loading: false }), 900);
    const t2 = setTimeout(() => setZones({ value: '184', loading: false }), 1300);
    const t3 = setTimeout(() => setWarnings({ value: '27', loading: false }), 1700);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, []);

  return (
    <>
      <Nav />

      {/* ── HERO ── */}
      <section className="hero">
        <div className="hero-text">
          <div className="hero-badge">
            <span className="dot"></span>
            v2.4 · Live across 42 cities
          </div>
          <h1 className="hero-title">
            Traffic<span className="accent">-lyt</span>
          </h1>
          <div className="hero-subhead">Smart-City Traffic Violation Analytics</div>
          <p className="hero-desc">
            Detect hotspots. Predict violations. Deploy smarter.
          </p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="/decision">
              Get Started <span className="btn-arrow">→</span>
            </a>
            <a className="btn btn-secondary" href="/map">View Map</a>
          </div>
          <div className="hero-trust">
            <span className="hero-trust-item">SOC 2 Type II</span>
            <span className="hero-trust-item">Sub-100ms</span>
            <span className="hero-trust-item">99.99% Uptime</span>
          </div>
        </div>

        <Globe pointCount={200} />
      </section>

      {/* ── STATS ── */}
      <section className="stats">
        <StatCard
          label="Violations Tracked"
          stat={violations}
          trend={{ dir: 'up', pct: '+12.4%' }}
          spark={[12, 18, 14, 22, 25, 21, 28, 24, 30, 33, 31, 38]}
          color="#5DADE2"
        />
        <StatCard
          label="Active Zones"
          stat={zones}
          trend={{ dir: 'up', pct: '+3.1%' }}
          spark={[170, 172, 171, 174, 176, 178, 177, 179, 181, 180, 183, 184]}
          color="#3DD68C"
        />
        <StatCard
          label="Warnings Detected"
          stat={warnings}
          trend={{ dir: 'down', pct: '-8.2%' }}
          spark={[35, 38, 42, 39, 36, 33, 31, 34, 30, 29, 28, 27]}
          color="#F4B740"
        />
      </section>

      {/* ── FEATURES ── */}
      <section className="section">
        <div className="section-head">
          <div>
            <div className="eyebrow">The Platform</div>
            <h2 className="section-title">Six modules. One unified command surface.</h2>
          </div>
          <p className="section-sub">
            Every layer — from raw violation feeds to patrol allocation —
            is built on a single deterministic scoring core.
          </p>
        </div>

        <div className="features">
          {FEATURES.map((f, i) => (
            <a key={f.href} className="feature" href={f.href}>
              <div className="feat-head">
                <div className="feat-icon">{f.icon}</div>
                <div className="feat-tag">0{i + 1} · {f.tag}</div>
              </div>
              <div className="feat-name">{f.name}</div>
              <p className="feat-desc">{f.desc}</p>
              <span className="feat-link">
                Open
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12"/>
                  <polyline points="12 5 19 12 12 19"/>
                </svg>
              </span>
            </a>
          ))}
        </div>
      </section>

      {/* ── BOTTOM CTA ── */}
      <section className="bottom-cta">
        <h2>Ready to deploy smarter?</h2>
        <p>
          Select your zones, set a horizon, and get a unified recommendation in seconds —
          backed by live data and explainable evidence.
        </p>
        <div className="bottom-actions">
          <a className="btn btn-primary" href="/decision">
            Open Decision Dashboard <span className="btn-arrow">→</span>
          </a>
          <a className="btn btn-secondary" href="/map">Explore the Map</a>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="footer">
        <div>© 2026 Traffic-lyt · Smart-City Analytics</div>
        <div className="footer-links">
          <a className="footer-link" href="#">Docs</a>
          <a className="footer-link" href="#">API</a>
          <a className="footer-link" href="#">Status</a>
          <a className="footer-link" href="https://github.com/achintya924/Traffic-lyt" target="_blank" rel="noopener">GitHub ↗</a>
        </div>
      </footer>
    </>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
