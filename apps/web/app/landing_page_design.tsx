'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

type StatState = { value: string; loading: boolean };

const FEATURES: { href: string; icon: string; name: string; desc: string; tag: string }[] = [
  { href: '/map',      icon: '🗺️', name: 'Map & Heatmap',      desc: 'Explore violation markers, heatmap overlays, and predicted risk hotspots in real time.', tag: 'GEO' },
  { href: '/zones',    icon: '📍', name: 'Zone Analytics',     desc: 'Browse neighborhood rankings, inspect trends, and compare zones side by side.',          tag: 'INSIGHTS' },
  { href: '/warnings', icon: '⚠️', name: 'Early Warnings',     desc: 'Automatic signals for traffic spikes, week-over-week anomalies, and cluster events.',    tag: 'ALERTS' },
  { href: '/patrol',   icon: '🚔', name: 'Patrol Allocation',  desc: 'Allocate units across zones using a deterministic risk-priority scoring strategy.',      tag: 'OPS' },
  { href: '/policy',   icon: '⚖️', name: 'Policy Simulator',   desc: 'Model enforcement interventions and preview their impact against forecast baselines.',  tag: 'SIM' },
  { href: '/decision', icon: '🎯', name: 'Decision Dashboard', desc: 'Get a unified "what should I do right now?" recommendation with full evidence.',         tag: 'COMMAND' },
];

/* ─────────────────────────────────────────────────────────────
 * Three.js animated globe with violation hotspots + arcs
 * ───────────────────────────────────────────────────────────── */
function Globe({ pointCount = 200 }: { pointCount?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hintShown, setHintShown] = useState(true);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const W = canvas.clientWidth;
    const H = canvas.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    camera.position.set(0, 0, 5.2);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);

    const earth = new THREE.Group();
    scene.add(earth);

    // shell
    const shellGeo = new THREE.SphereGeometry(1.5, 64, 64);
    const shellMat = new THREE.MeshBasicMaterial({ color: 0x0a1622, transparent: true, opacity: 0.92 });
    earth.add(new THREE.Mesh(shellGeo, shellMat));

    // inner halo
    const haloGeo = new THREE.SphereGeometry(1.55, 64, 64);
    const haloMat = new THREE.MeshBasicMaterial({ color: 0x2e86c1, transparent: true, opacity: 0.06, side: THREE.BackSide });
    earth.add(new THREE.Mesh(haloGeo, haloMat));

    // atmosphere
    const atmGeo = new THREE.SphereGeometry(1.62, 64, 64);
    const atmMat = new THREE.ShaderMaterial({
      transparent: true,
      side: THREE.BackSide,
      uniforms: { c: { value: 0.5 }, p: { value: 3.0 } },
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        varying vec3 vNormal;
        uniform float c;
        uniform float p;
        void main() {
          float intensity = pow(c - dot(vNormal, vec3(0.0, 0.0, 1.0)), p);
          gl_FragColor = vec4(0.18, 0.53, 0.76, 1.0) * intensity;
        }`,
    });
    scene.add(new THREE.Mesh(atmGeo, atmMat));

    // wireframe lat/lon
    const wireGeo = new THREE.SphereGeometry(1.502, 32, 18);
    const wireMat = new THREE.LineBasicMaterial({ color: 0x2e86c1, transparent: true, opacity: 0.18 });
    const wire = new THREE.LineSegments(new THREE.WireframeGeometry(wireGeo), wireMat);
    earth.add(wire);

    // continent dots
    const dotGeo = new THREE.SphereGeometry(0.012, 6, 6);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x3a5d7d, transparent: true, opacity: 0.6 });
    const continentDots = new THREE.Group();
    for (let i = 0; i < 700; i++) {
      const u = Math.random();
      const v = Math.random();
      const theta = 2 * Math.PI * u;
      const phi = Math.acos(2 * v - 1);
      const lm =
        Math.sin(phi * 4) * Math.cos(theta * 3) +
        Math.cos(phi * 2 + 1) * Math.sin(theta * 2 - 0.7) +
        Math.sin(theta * 5 + phi);
      if (lm < 0.25) continue;
      const r = 1.508;
      const m = new THREE.Mesh(dotGeo, dotMat);
      m.position.set(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta)
      );
      continentDots.add(m);
    }
    earth.add(continentDots);

    // hotspots
    type Hot = { pos: THREE.Vector3; ring: THREE.Mesh; ringMat: THREE.MeshBasicMaterial; phase: number };
    const hotspots: Hot[] = [];
    const hotspotGroup = new THREE.Group();
    earth.add(hotspotGroup);

    const ringGeo = new THREE.RingGeometry(0.018, 0.028, 24);
    const hotGeo = new THREE.SphereGeometry(0.018, 12, 12);

    for (let i = 0; i < pointCount; i++) {
      const theta = Math.random() * 2 * Math.PI;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.51;
      const pos = new THREE.Vector3(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta)
      );
      const sev = Math.random();
      const color = sev > 0.85 ? 0xe55353 : sev > 0.55 ? 0xf4b740 : 0x5dade2;

      const dot = new THREE.Mesh(hotGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }));
      dot.position.copy(pos);
      hotspotGroup.add(dot);

      const ringMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.position.copy(pos);
      ring.lookAt(pos.clone().multiplyScalar(2));
      hotspotGroup.add(ring);

      hotspots.push({ pos, ring, ringMat, phase: Math.random() * Math.PI * 2 });
    }

    // connecting arcs
    const arcGroup = new THREE.Group();
    earth.add(arcGroup);
    const baseArcMat = new THREE.LineBasicMaterial({ color: 0x2e86c1, transparent: true, opacity: 0.35 });
    const made = new Set<string>();
    const MAX_LINKS = 2;
    const DIST = 0.9;
    for (let i = 0; i < hotspots.length; i++) {
      const a = hotspots[i].pos;
      const cands: { j: number; d: number }[] = [];
      for (let j = 0; j < hotspots.length; j++) {
        if (i === j) continue;
        const d = a.distanceTo(hotspots[j].pos);
        if (d < DIST) cands.push({ j, d });
      }
      cands.sort((x, y) => x.d - y.d);
      cands.slice(0, MAX_LINKS).forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (made.has(key)) return;
        made.add(key);
        const b = hotspots[j].pos;
        const mid = a.clone().add(b).multiplyScalar(0.5);
        const lift = 1 + a.distanceTo(b) * 0.3;
        mid.normalize().multiplyScalar(1.51 * lift);
        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const points = curve.getPoints(24);
        const g = new THREE.BufferGeometry().setFromPoints(points);
        arcGroup.add(new THREE.Line(g, baseArcMat.clone()));
      });
    }

    // interaction
    let isDragging = false;
    let lastX = 0, lastY = 0;
    let rotVelX = 0, rotVelY = 0;
    const AUTO = 0.0015;

    const getXY = (e: MouseEvent | TouchEvent) => {
      const t = (e as TouchEvent).touches?.[0];
      return t ? { x: t.clientX, y: t.clientY } : { x: (e as MouseEvent).clientX, y: (e as MouseEvent).clientY };
    };
    const onDown = (e: MouseEvent | TouchEvent) => {
      isDragging = true;
      setHintShown(false);
      const p = getXY(e);
      lastX = p.x; lastY = p.y;
      rotVelX = rotVelY = 0;
    };
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isDragging) return;
      if ((e as TouchEvent).touches) e.preventDefault?.();
      const p = getXY(e);
      const dx = p.x - lastX;
      const dy = p.y - lastY;
      lastX = p.x; lastY = p.y;
      rotVelY = dx * 0.005;
      rotVelX = dy * 0.005;
      earth.rotation.y += rotVelY;
      earth.rotation.x = Math.max(-1.2, Math.min(1.2, earth.rotation.x + rotVelX));
    };
    const onUp = () => { isDragging = false; };

    canvas.addEventListener('mousedown', onDown as EventListener);
    window.addEventListener('mousemove', onMove as EventListener);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('touchstart', onDown as EventListener, { passive: true });
    window.addEventListener('touchmove', onMove as EventListener, { passive: false });
    window.addEventListener('touchend', onUp);

    const onResize = () => {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(canvas);

    earth.rotation.x = -0.3;
    earth.rotation.y = 0.6;

    let raf = 0;
    const t0 = performance.now();
    const animate = () => {
      const t = (performance.now() - t0) / 1000;
      if (!isDragging) {
        rotVelY *= 0.94; rotVelX *= 0.94;
        earth.rotation.y += rotVelY;
        earth.rotation.x += rotVelX;
        earth.rotation.y += AUTO;
      }
      for (let i = 0; i < hotspots.length; i++) {
        const h = hotspots[i];
        const k = (Math.sin(t * 1.6 + h.phase) + 1) / 2;
        h.ring.scale.setScalar(1 + k * 1.6);
        h.ringMat.opacity = (1 - k) * 0.7;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };
    animate();

    const hintT = setTimeout(() => setHintShown(false), 6000);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(hintT);
      ro.disconnect();
      canvas.removeEventListener('mousedown', onDown as EventListener);
      window.removeEventListener('mousemove', onMove as EventListener);
      window.removeEventListener('mouseup', onUp);
      canvas.removeEventListener('touchstart', onDown as EventListener);
      window.removeEventListener('touchmove', onMove as EventListener);
      window.removeEventListener('touchend', onUp);
      renderer.dispose();
    };
  }, [pointCount]);

  return (
    <div className="hero-globe-wrap">
      <div className="globe-rings" />
      <canvas ref={canvasRef} className="globe-canvas" />
      <div className="globe-overlay-stat gos-1">
        <span className="gos-lbl">Live Feed</span>
        <span className="gos-val"><span className="gos-acc">●</span> 1,247 / sec</span>
      </div>
      <div className="globe-overlay-stat gos-2">
        <span className="gos-lbl">Coverage</span>
        <span className="gos-val">42 cities</span>
      </div>
      <div className="globe-overlay-stat gos-3">
        <span className="gos-lbl">Latency</span>
        <span className="gos-val">87 ms</span>
      </div>
      <div className={`globe-hint${hintShown ? ' shown' : ''}`}>Drag to rotate</div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
 * Stat card (with shimmer skeleton while loading)
 * ───────────────────────────────────────────────────────────── */
function StatCard({ label, stat }: { label: string; stat: StatState }) {
  return (
    <div className="lp-stat-card">
      <div className="lp-stat-head">
        <div className="lp-stat-label">{label}</div>
        <span className="lp-stat-pill">LIVE</span>
      </div>
      {stat.loading ? (
        <div className="lp-skel" />
      ) : (
        <div className="lp-stat-value">{stat.value}</div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
 * Page
 * ───────────────────────────────────────────────────────────── */
export default function Home() {
  const [violations, setViolations] = useState<StatState>({ value: '-', loading: true });
  const [zones,      setZones]      = useState<StatState>({ value: '-', loading: true });
  const [warnings,   setWarnings]   = useState<StatState>({ value: '-', loading: true });

  useEffect(() => {
    const ac = new AbortController();
    const sig = ac.signal;

    fetch(`${API_BASE}/violations/stats`, { signal: sig })
      .then(r => r.json())
      .then(d => setViolations({ value: (d.total ?? 0).toLocaleString(), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setViolations({ value: '-', loading: false }); });

    fetch(`${API_BASE}/api/zones`, { signal: sig })
      .then(r => r.json())
      .then(d => setZones({ value: String((d.zones ?? []).length), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setZones({ value: '-', loading: false }); });

    fetch(`${API_BASE}/api/warnings`, { signal: sig })
      .then(r => r.json())
      .then(d => setWarnings({ value: String((d.warnings ?? []).length), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setWarnings({ value: '-', loading: false }); });

    return () => ac.abort();
  }, []);

  return (
    <main className="lp-root">
      <div className="lp-bg" />

      {/* Hero */}
      <section className="lp-hero">
        <div className="lp-hero-text">
          <div className="lp-hero-badge">
            <span className="lp-hero-badge-dot" />
            v2.4 · Live across 42 cities
          </div>
          <h1 className="lp-hero-title">
            Traffic<span className="lp-accent">-lyt</span>
          </h1>
          <div className="lp-hero-sub">Smart-City Traffic Violation Analytics</div>
          <p className="lp-hero-desc">Detect hotspots. Predict violations. Deploy smarter.</p>
          <div className="lp-hero-actions">
            <Link href="/decision" className="lp-btn lp-btn-primary">
              Get Started <span className="lp-btn-arrow">→</span>
            </Link>
            <Link href="/map" className="lp-btn lp-btn-secondary">View Map</Link>
          </div>
          <div className="lp-hero-trust">
            <span className="lp-trust-item">SOC 2 Type II</span>
            <span className="lp-trust-item">Sub-100ms</span>
            <span className="lp-trust-item">99.99% Uptime</span>
          </div>
        </div>

        <Globe pointCount={200} />
      </section>

      {/* Live stats */}
      <section className="lp-stats">
        <StatCard label="Violations Tracked" stat={violations} />
        <StatCard label="Active Zones"       stat={zones}      />
        <StatCard label="Warnings Detected"  stat={warnings}   />
      </section>

      {/* Features */}
      <section className="lp-section">
        <div className="lp-section-head">
          <div>
            <div className="lp-eyebrow">The Platform</div>
            <h2 className="lp-section-title">Six modules. One unified command surface.</h2>
          </div>
          <p className="lp-section-sub">
            Every layer — from raw violation feeds to patrol allocation —
            is built on a single deterministic scoring core.
          </p>
        </div>

        <div className="lp-features">
          {FEATURES.map((f, i) => (
            <Link key={f.href} href={f.href} className="lp-feature">
              <div className="lp-feat-head">
                <div className="lp-feat-icon" aria-hidden="true">{f.icon}</div>
                <div className="lp-feat-tag">0{i + 1} · {f.tag}</div>
              </div>
              <div className="lp-feat-name">{f.name}</div>
              <p className="lp-feat-desc">{f.desc}</p>
              <span className="lp-feat-link">Open →</span>
            </Link>
          ))}
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="lp-bottom-cta">
        <h2>Ready to deploy smarter?</h2>
        <p>Select your zones, set a horizon, and get a unified recommendation in seconds — backed by live data and explainable evidence.</p>
        <div className="lp-bottom-actions">
          <Link href="/decision" className="lp-btn lp-btn-primary">
            Open Decision Dashboard <span className="lp-btn-arrow">→</span>
          </Link>
          <Link href="/map" className="lp-btn lp-btn-secondary">Explore the Map</Link>
        </div>
      </section>

      <style jsx>{`
        .lp-root {
          --bg:#0D1B2A; --bg-2:#0a1622; --line:rgba(46,134,193,0.18); --line-2:rgba(255,255,255,0.06);
          --accent:#2E86C1; --accent-2:#5DADE2; --accent-glow:rgba(46,134,193,0.35);
          --text:#F5F8FB; --text-2:#B7C3D0; --text-3:#6E7C8C;
          --good:#3DD68C; --warn:#F4B740; --danger:#E55353;
          background: var(--bg); color: var(--text); position: relative;
          min-height: 100vh; overflow-x: hidden;
          font-family: 'Inter', system-ui, -apple-system, sans-serif;
          padding: 0; max-width: none; margin: 0;
        }
        .lp-bg {
          position: fixed; inset: 0; pointer-events: none; z-index: 0;
          background:
            radial-gradient(1200px 600px at 80% -10%, rgba(46,134,193,0.18), transparent 60%),
            radial-gradient(900px 500px at -10% 30%, rgba(46,134,193,0.10), transparent 60%);
        }

        /* hero */
        .lp-hero {
          position: relative; z-index: 1;
          display: grid; grid-template-columns: 1.05fr 1fr;
          gap: 40px; align-items: center;
          padding: 60px 40px 40px; max-width: 1440px; margin: 0 auto;
          min-height: 640px;
        }
        .lp-hero-text { max-width: 580px; }
        .lp-hero-badge {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 6px 12px; border: 1px solid var(--line);
          background: rgba(46,134,193,0.06);
          border-radius: 999px; font-size: 12px; font-weight: 500;
          color: var(--text-2); margin-bottom: 24px;
        }
        .lp-hero-badge-dot {
          width: 6px; height: 6px; border-radius: 50%;
          background: var(--good); box-shadow: 0 0 8px var(--good);
          animation: lp-pulse 2s ease-in-out infinite;
        }
        @keyframes lp-pulse { 0%,100%{opacity:1;transform:scale(1);} 50%{opacity:.5;transform:scale(.8);} }

        .lp-hero-title {
          font-size: clamp(56px, 7vw, 96px); font-weight: 800;
          letter-spacing: -0.04em; line-height: 0.98; margin: 0 0 18px;
          background: linear-gradient(180deg, #ffffff 0%, #B7C3D0 100%);
          -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .lp-accent {
          background: linear-gradient(180deg, var(--accent-2) 0%, var(--accent) 100%);
          -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .lp-hero-sub { font-size: 20px; font-weight: 500; letter-spacing: -0.01em; margin-bottom: 14px; }
        .lp-hero-desc { font-size: 17px; color: var(--text-2); line-height: 1.55; margin-bottom: 32px; max-width: 460px; }

        .lp-hero-actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
        .lp-btn {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 14px 22px; border-radius: 10px;
          font-size: 15px; font-weight: 600; text-decoration: none;
          transition: all 0.18s ease;
        }
        .lp-btn-primary {
          background: var(--accent); color: #fff;
          box-shadow: 0 8px 24px -8px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,0.18);
        }
        .lp-btn-primary:hover { background: var(--accent-2); transform: translateY(-2px); }
        .lp-btn-secondary { background: transparent; color: var(--text); border: 1px solid var(--line); }
        .lp-btn-secondary:hover { background: rgba(255,255,255,0.04); border-color: rgba(46,134,193,0.4); }
        .lp-btn-arrow { transition: transform .18s; }
        .lp-btn:hover .lp-btn-arrow { transform: translateX(3px); }

        .lp-hero-trust {
          margin-top: 48px; display: flex; gap: 28px; flex-wrap: wrap;
          color: var(--text-3); font-size: 12px;
          text-transform: uppercase; letter-spacing: 0.12em;
        }
        .lp-trust-item { display: flex; align-items: center; gap: 8px; }
        .lp-trust-item::before { content: ""; width: 4px; height: 4px; border-radius: 50%; background: var(--accent); }

        /* globe */
        .hero-globe-wrap {
          position: relative; aspect-ratio: 1/1; width: 100%;
          max-width: 620px; justify-self: end;
        }
        .globe-canvas { width: 100%; height: 100%; display: block; cursor: grab; }
        .globe-canvas:active { cursor: grabbing; }
        .globe-rings { position: absolute; inset: 0; pointer-events: none; border-radius: 50%; }
        .globe-rings::before, .globe-rings::after {
          content: ""; position: absolute; inset: 6%;
          border: 1px dashed rgba(46,134,193,0.18); border-radius: 50%;
          animation: lp-spin 80s linear infinite;
        }
        .globe-rings::after { inset: -2%; border: 1px solid rgba(46,134,193,0.08); animation: lp-spin 120s linear infinite reverse; }
        @keyframes lp-spin { to { transform: rotate(360deg); } }

        .globe-overlay-stat {
          position: absolute; background: rgba(13,27,42,0.78);
          border: 1px solid var(--line); backdrop-filter: blur(10px);
          border-radius: 12px; padding: 10px 14px;
          display: flex; flex-direction: column;
          font-family: 'JetBrains Mono', monospace; pointer-events: none;
          animation: lp-float 6s ease-in-out infinite;
        }
        .gos-lbl { font-size: 9px; color: var(--text-3); text-transform: uppercase; letter-spacing: .14em; }
        .gos-val { font-size: 16px; color: var(--text); font-weight: 600; margin-top: 2px; }
        .gos-acc { color: var(--accent-2); }
        .gos-1 { top: 10%; left: -2%; }
        .gos-2 { bottom: 18%; right: -4%; animation-delay: -2s; }
        .gos-3 { bottom: 4%; left: 8%; animation-delay: -4s; }
        @keyframes lp-float { 0%,100%{transform:translateY(0);} 50%{transform:translateY(-6px);} }

        .globe-hint {
          position: absolute; bottom: -8px; left: 50%; transform: translateX(-50%);
          font-family: 'JetBrains Mono', monospace; font-size: 10px;
          color: var(--text-3); letter-spacing: .1em; text-transform: uppercase;
          opacity: 0; transition: opacity .5s;
        }
        .globe-hint.shown { opacity: 1; }

        /* stats */
        .lp-stats {
          position: relative; z-index: 1;
          max-width: 1440px; margin: 0 auto;
          padding: 24px 40px 40px;
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
        }
        .lp-stat-card {
          background: linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0));
          border: 1px solid var(--line-2); border-radius: 14px;
          padding: 22px 24px; position: relative; overflow: hidden;
          transition: border-color .2s, transform .2s;
        }
        .lp-stat-card:hover { border-color: var(--line); transform: translateY(-2px); }
        .lp-stat-card::before {
          content: ""; position: absolute; top: 0; left: 24px; right: 24px;
          height: 1px;
          background: linear-gradient(90deg, transparent, var(--accent), transparent);
          opacity: 0.4;
        }
        .lp-stat-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
        .lp-stat-label { font-size: 12px; font-weight: 500; color: var(--text-3); text-transform: uppercase; letter-spacing: .1em; }
        .lp-stat-pill {
          font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--good);
          padding: 3px 8px; background: rgba(61,214,140,0.1);
          border: 1px solid rgba(61,214,140,0.25); border-radius: 999px;
          display: inline-flex; align-items: center; gap: 5px;
        }
        .lp-stat-pill::before {
          content: ""; width: 5px; height: 5px; border-radius: 50%;
          background: var(--good); box-shadow: 0 0 6px var(--good);
          animation: lp-pulse 1.6s ease-in-out infinite;
        }
        .lp-stat-value { font-size: 40px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; font-variant-numeric: tabular-nums; }

        .lp-skel {
          height: 40px; width: 140px; border-radius: 6px;
          background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.04) 75%);
          background-size: 200% 100%; animation: lp-shimmer 1.4s ease-in-out infinite;
        }
        @keyframes lp-shimmer { 0%{background-position:200% 0;} 100%{background-position:-200% 0;} }

        /* sections */
        .lp-section { position: relative; z-index: 1; max-width: 1440px; margin: 0 auto; padding: 60px 40px; }
        .lp-section-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 32px; flex-wrap: wrap; }
        .lp-eyebrow {
          font-family: 'JetBrains Mono', monospace; font-size: 11px;
          color: var(--accent-2); text-transform: uppercase; letter-spacing: .18em;
          margin-bottom: 14px; display: flex; align-items: center; gap: 10px;
        }
        .lp-eyebrow::before { content: ""; width: 16px; height: 1px; background: var(--accent); }
        .lp-section-title { font-size: 40px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.05; max-width: 600px; margin: 0; }
        .lp-section-sub { font-size: 16px; color: var(--text-2); max-width: 380px; line-height: 1.55; text-align: right; }

        /* features */
        .lp-features { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .lp-feature {
          position: relative; text-decoration: none; color: inherit;
          background: linear-gradient(180deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0) 100%);
          border: 1px solid var(--line-2); border-radius: 14px;
          padding: 24px; transition: transform .25s ease, border-color .25s, box-shadow .25s;
          overflow: hidden; display: flex; flex-direction: column; min-height: 240px;
        }
        .lp-feature::before {
          content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, var(--accent), transparent);
          opacity: 0; transition: opacity .25s;
        }
        .lp-feature:hover { transform: translateY(-4px); border-color: rgba(46,134,193,0.35); box-shadow: 0 18px 40px -20px rgba(46,134,193,0.5); }
        .lp-feature:hover::before { opacity: 1; }
        .lp-feat-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
        .lp-feat-icon {
          width: 44px; height: 44px; border-radius: 10px;
          background: rgba(46,134,193,0.10); border: 1px solid var(--line);
          display: flex; align-items: center; justify-content: center; font-size: 22px;
        }
        .lp-feat-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-3); letter-spacing: .1em; }
        .lp-feat-name { font-size: 18px; font-weight: 600; letter-spacing: -0.01em; margin-bottom: 8px; }
        .lp-feat-desc { font-size: 14px; color: var(--text-2); line-height: 1.55; flex-grow: 1; margin-bottom: 18px; }
        .lp-feat-link {
          display: inline-flex; align-items: center; gap: 6px;
          font-size: 13px; font-weight: 600; color: var(--accent-2);
          align-self: flex-start; padding: 8px 12px;
          border: 1px solid var(--line); background: rgba(46,134,193,0.05);
          border-radius: 8px; transition: background .18s, border-color .18s;
        }
        .lp-feature:hover .lp-feat-link { background: rgba(46,134,193,0.15); border-color: rgba(46,134,193,0.5); }

        /* bottom cta */
        .lp-bottom-cta {
          position: relative; z-index: 1;
          max-width: 1440px; margin: 40px auto 0;
          padding: 60px 40px; border-top: 1px solid var(--line-2);
          text-align: center;
        }
        .lp-bottom-cta::before {
          content: ""; position: absolute; left: 50%; top: -1px; transform: translateX(-50%);
          width: 320px; height: 2px;
          background: linear-gradient(90deg, transparent, var(--accent), transparent);
        }
        .lp-bottom-cta h2 { font-size: 44px; font-weight: 700; letter-spacing: -0.025em; margin-bottom: 12px; }
        .lp-bottom-cta p { color: var(--text-2); font-size: 16px; max-width: 480px; margin: 0 auto 28px; }
        .lp-bottom-actions { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }

        /* responsive */
        @media (max-width: 1024px) {
          .lp-hero { grid-template-columns: 1fr; padding: 48px 28px; gap: 32px; }
          .hero-globe-wrap { max-width: 480px; margin: 0 auto; justify-self: center; }
          .lp-stats { grid-template-columns: 1fr; padding: 16px 28px 28px; }
          .lp-features { grid-template-columns: repeat(2, 1fr); }
          .lp-section { padding: 48px 28px; }
          .lp-section-sub { text-align: left; }
        }
        @media (max-width: 640px) {
          .lp-hero { padding: 32px 20px; min-height: auto; }
          .lp-hero-title { font-size: 56px; }
          .lp-features { grid-template-columns: 1fr; }
          .lp-section { padding: 36px 20px; }
          .lp-section-title { font-size: 30px; }
          .lp-section-head { flex-direction: column; align-items: flex-start; }
          .lp-section-sub { text-align: left; max-width: 100%; }
          .lp-bottom-cta { padding: 48px 20px; }
          .lp-bottom-cta h2 { font-size: 30px; }
          .globe-overlay-stat { display: none; }
        }
      `}</style>
    </main>
  );
}
