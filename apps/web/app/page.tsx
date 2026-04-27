'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

/* ─── types ─────────────────────────────────────────────────────── */
type StatState = { value: string; loading: boolean };

/* ─── feature list ──────────────────────────────────────────────── */
const FEATURES: { href: string; icon: string; name: string; desc: string; tag: string }[] = [
  { href: '/map',      icon: '🗺️', name: 'Map & Heatmap',      desc: 'Explore violation markers, heatmap overlays, and predicted risk hotspots in real time.', tag: 'GEO'     },
  { href: '/zones',    icon: '📍', name: 'Zone Analytics',     desc: 'Browse neighborhood rankings, inspect trends, and compare zones side by side.',          tag: 'INSIGHTS'},
  { href: '/warnings', icon: '⚠️', name: 'Early Warnings',     desc: 'Automatic signals for traffic spikes, week-over-week anomalies, and cluster events.',    tag: 'ALERTS'  },
  { href: '/patrol',   icon: '🚔', name: 'Patrol Allocation',  desc: 'Allocate units across zones using a deterministic risk-priority scoring strategy.',      tag: 'OPS'     },
  { href: '/policy',   icon: '⚖️', name: 'Policy Simulator',   desc: 'Model enforcement interventions and preview their impact against forecast baselines.',    tag: 'SIM'     },
  { href: '/decision', icon: '🎯', name: 'Decision Dashboard', desc: 'Get a unified "what should I do right now?" recommendation with full evidence.',         tag: 'COMMAND' },
];

/* ─── sparkline ─────────────────────────────────────────────────── */
const SW = 96, SH = 32, SP = 2;

function Spark({ data, color = '#2E86C1' }: { data: number[]; color?: string }) {
  const min = Math.min(...data), max = Math.max(...data);
  const range = Math.max(1, max - min);
  const pts = data.map((v, i) => {
    const x = SP + (i / (data.length - 1)) * (SW - 2 * SP);
    const y = SH - SP - ((v - min) / range) * (SH - 2 * SP);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const gid = `sg${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <svg className="lp-spark" viewBox={`0 0 ${SW} ${SH}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.38" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${SP},${SH - SP} ${pts} ${SW - SP},${SH - SP}`} fill={`url(#${gid})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

/* ─── globe ─────────────────────────────────────────────────────── */
function Globe({ pointCount = 200 }: { pointCount?: number }) {
  const mountRef  = useRef<HTMLDivElement | null>(null);
  const [hintShown, setHintShown] = useState(true);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const W = mount.clientWidth  || 600;
    const H = mount.clientHeight || 600;

    /* scene / camera */
    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    camera.position.set(0, 0, 5.2);

    /* renderer — create canvas, append to mount div */
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    Object.assign(renderer.domElement.style, {
      width: '100%', height: '100%', display: 'block', cursor: 'grab',
    });
    mount.appendChild(renderer.domElement);

    const earth = new THREE.Group();
    scene.add(earth);

    /* shell */
    const shellGeo = new THREE.SphereGeometry(1.5, 64, 64);
    const shellMat = new THREE.MeshBasicMaterial({ color: 0x0a1622, transparent: true, opacity: 0.92 });
    earth.add(new THREE.Mesh(shellGeo, shellMat));

    /* inner halo */
    const haloGeo = new THREE.SphereGeometry(1.55, 64, 64);
    const haloMat = new THREE.MeshBasicMaterial({ color: 0x2E86C1, transparent: true, opacity: 0.06, side: THREE.BackSide });
    earth.add(new THREE.Mesh(haloGeo, haloMat));

    /* atmosphere shader */
    const atmGeo = new THREE.SphereGeometry(1.62, 64, 64);
    const atmMat = new THREE.ShaderMaterial({
      transparent: true, side: THREE.BackSide,
      uniforms: { c: { value: 0.5 }, p: { value: 3.0 } },
      vertexShader: `varying vec3 vNormal;
        void main(){vNormal=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
      fragmentShader: `varying vec3 vNormal; uniform float c,p;
        void main(){float i=pow(c-dot(vNormal,vec3(0,0,1)),p);gl_FragColor=vec4(0.18,0.53,0.76,1.0)*i;}`,
    });
    scene.add(new THREE.Mesh(atmGeo, atmMat));

    /* wireframe */
    const wireGeo = new THREE.SphereGeometry(1.502, 32, 18);
    const wireMat = new THREE.LineBasicMaterial({ color: 0x2E86C1, transparent: true, opacity: 0.18 });
    earth.add(new THREE.LineSegments(new THREE.WireframeGeometry(wireGeo), wireMat));

    /* continent dots */
    const dotGeo = new THREE.SphereGeometry(0.012, 6, 6);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x3a5d7d, transparent: true, opacity: 0.6 });
    const continentDots = new THREE.Group();
    for (let i = 0; i < 700; i++) {
      const u = Math.random(), v = Math.random();
      const theta = 2 * Math.PI * u;
      const phi   = Math.acos(2 * v - 1);
      const lm = Math.sin(phi * 4) * Math.cos(theta * 3) + Math.cos(phi * 2 + 1) * Math.sin(theta * 2 - 0.7) + Math.sin(theta * 5 + phi);
      if (lm < 0.25) continue;
      const r = 1.508;
      const m = new THREE.Mesh(dotGeo, dotMat);
      m.position.set(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
      continentDots.add(m);
    }
    earth.add(continentDots);

    /* hotspots */
    type Hot = { pos: THREE.Vector3; ring: THREE.Mesh; ringMat: THREE.MeshBasicMaterial; phase: number };
    const hotspots: Hot[] = [];
    const hotspotGroup = new THREE.Group();
    earth.add(hotspotGroup);
    const ringGeo = new THREE.RingGeometry(0.018, 0.028, 24);
    const hotGeo  = new THREE.SphereGeometry(0.018, 12, 12);

    for (let i = 0; i < pointCount; i++) {
      const theta = Math.random() * 2 * Math.PI;
      const phi   = Math.acos(2 * Math.random() - 1);
      const r     = 1.51;
      const pos   = new THREE.Vector3(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
      const sev   = Math.random();
      const color = sev > 0.85 ? 0xE55353 : sev > 0.55 ? 0xF4B740 : 0x5DADE2;

      const dot = new THREE.Mesh(hotGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }));
      dot.position.copy(pos);
      hotspotGroup.add(dot);

      const ringMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false });
      const ring    = new THREE.Mesh(ringGeo, ringMat);
      ring.position.copy(pos);
      ring.lookAt(pos.clone().multiplyScalar(2));
      hotspotGroup.add(ring);

      hotspots.push({ pos, ring, ringMat, phase: Math.random() * Math.PI * 2 });
    }

    /* connecting arcs */
    const arcGroup  = new THREE.Group();
    earth.add(arcGroup);
    const baseArcMat = new THREE.LineBasicMaterial({ color: 0x2E86C1, transparent: true, opacity: 0.35 });
    const made = new Set<string>();
    for (let i = 0; i < hotspots.length; i++) {
      const a     = hotspots[i].pos;
      const cands: { j: number; d: number }[] = [];
      for (let j = 0; j < hotspots.length; j++) {
        if (i === j) continue;
        const d = a.distanceTo(hotspots[j].pos);
        if (d < 0.9) cands.push({ j, d });
      }
      cands.sort((x, y) => x.d - y.d);
      cands.slice(0, 2).forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (made.has(key)) return;
        made.add(key);
        const b   = hotspots[j].pos;
        const mid = a.clone().add(b).multiplyScalar(0.5);
        mid.normalize().multiplyScalar(1.51 * (1 + a.distanceTo(b) * 0.3));
        const pts = new THREE.QuadraticBezierCurve3(a, mid, b).getPoints(24);
        arcGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), baseArcMat.clone()));
      });
    }

    /* drag interaction */
    let isDragging = false, lastX = 0, lastY = 0, rotVelX = 0, rotVelY = 0;

    const getXY = (e: MouseEvent | TouchEvent) => {
      const t = (e as TouchEvent).touches?.[0];
      return t ? { x: t.clientX, y: t.clientY } : { x: (e as MouseEvent).clientX, y: (e as MouseEvent).clientY };
    };
    const onDown = (e: MouseEvent | TouchEvent) => {
      isDragging = true; setHintShown(false);
      const p = getXY(e); lastX = p.x; lastY = p.y; rotVelX = rotVelY = 0;
    };
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isDragging) return;
      if ((e as TouchEvent).touches) e.preventDefault?.();
      const p = getXY(e);
      rotVelY = (p.x - lastX) * 0.005; rotVelX = (p.y - lastY) * 0.005;
      lastX = p.x; lastY = p.y;
      earth.rotation.y += rotVelY;
      earth.rotation.x  = Math.max(-1.2, Math.min(1.2, earth.rotation.x + rotVelX));
    };
    const onUp = () => { isDragging = false; };

    renderer.domElement.addEventListener('mousedown',  onDown as EventListener);
    renderer.domElement.addEventListener('touchstart', onDown as EventListener, { passive: true });
    window.addEventListener('mousemove',  onMove as EventListener);
    window.addEventListener('mouseup',    onUp);
    window.addEventListener('touchmove',  onMove as EventListener, { passive: false });
    window.addEventListener('touchend',   onUp);

    /* resize */
    const onResize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(mount);

    earth.rotation.set(-0.3, 0.6, 0);

    /* animation loop */
    let raf = 0;
    const t0 = performance.now();
    const animate = () => {
      const t = (performance.now() - t0) / 1000;
      if (!isDragging) {
        rotVelY *= 0.94; rotVelX *= 0.94;
        earth.rotation.y += rotVelY + 0.0015;
        earth.rotation.x += rotVelX;
      }
      for (const h of hotspots) {
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
      renderer.domElement.removeEventListener('mousedown',  onDown as EventListener);
      renderer.domElement.removeEventListener('touchstart', onDown as EventListener);
      window.removeEventListener('mousemove',  onMove as EventListener);
      window.removeEventListener('mouseup',    onUp);
      window.removeEventListener('touchmove',  onMove as EventListener);
      window.removeEventListener('touchend',   onUp);
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
      renderer.dispose();
      shellGeo.dispose(); shellMat.dispose();
      haloGeo.dispose();  haloMat.dispose();
      atmGeo.dispose();   atmMat.dispose();
      wireGeo.dispose();  wireMat.dispose();
      ringGeo.dispose();  hotGeo.dispose(); dotGeo.dispose(); dotMat.dispose();
    };
  }, [pointCount]);

  return (
    <div className="hero-globe-wrap">
      <div className="globe-rings" />
      <div ref={mountRef} className="globe-mount" />
      <div className={`globe-hint${hintShown ? ' shown' : ''}`}>Drag to rotate</div>
    </div>
  );
}

/* ─── stat card ─────────────────────────────────────────────────── */
function StatCard({
  label, stat, spark, color,
}: {
  label: string; stat: StatState; spark: number[]; color: string;
}) {
  return (
    <div className="lp-stat-card">
      <div className="lp-stat-head">
        <div className="lp-stat-label">{label}</div>
      </div>
      {stat.loading ? (
        <div className="lp-skel" />
      ) : (
        <div className="lp-stat-value">{stat.value}</div>
      )}
      <Spark data={spark} color={color} />
    </div>
  );
}

/* ─── page CSS injected client-side ─────────────────────────────── */
const LP_CSS = `
  .lp-root {
    --bg:#0D1B2A; --bg2:#0a1622; --ln:rgba(46,134,193,.18); --ln2:rgba(255,255,255,.06);
    --ac:#2E86C1; --ac2:#5DADE2; --acg:rgba(46,134,193,.35);
    --tx:#F5F8FB; --tx2:#B7C3D0; --tx3:#6E7C8C;
    --good:#3DD68C; --warn:#F4B740; --dng:#E55353;
    background:var(--bg)!important; color:var(--tx); position:relative;
    min-height:100vh; overflow-x:hidden;
    font-family:'Inter',system-ui,-apple-system,sans-serif;
    padding:0!important; max-width:none!important; margin:0!important;
  }
  .lp-bg {
    position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      radial-gradient(1200px 600px at 80% -10%,rgba(46,134,193,.18),transparent 60%),
      radial-gradient(900px 500px at -10% 30%,rgba(46,134,193,.10),transparent 60%);
  }
  /* hero */
  .lp-hero {
    position:relative; z-index:1;
    display:grid; grid-template-columns:1.05fr 1fr; gap:40px; align-items:center;
    padding:60px 40px 40px; max-width:1440px; margin:0 auto; min-height:640px;
  }
  .lp-hero-text { max-width:580px; }
  .lp-hero-badge {
    display:inline-flex; align-items:center; gap:8px;
    padding:6px 12px; border:1px solid var(--ln); background:rgba(46,134,193,.06);
    border-radius:999px; font-size:12px; font-weight:500; color:var(--tx2); margin-bottom:24px;
  }
  .lp-badge-dot {
    display:inline-block; width:6px; height:6px; border-radius:50%;
    background:var(--good); box-shadow:0 0 8px var(--good);
    animation:lp-pulse 2s ease-in-out infinite;
  }
  @keyframes lp-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
  .lp-hero-title {
    font-size:clamp(56px,7vw,96px); font-weight:800;
    letter-spacing:-.04em; line-height:.98; margin:0 0 18px;
    background:linear-gradient(180deg,#fff 0%,#B7C3D0 100%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }
  .lp-accent {
    background:linear-gradient(180deg,var(--ac2) 0%,var(--ac) 100%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }
  .lp-hero-sub  { font-size:20px; font-weight:500; letter-spacing:-.01em; margin-bottom:14px; }
  .lp-hero-desc { font-size:17px; color:var(--tx2); line-height:1.55; margin-bottom:32px; max-width:460px; }
  .lp-hero-actions { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
  .lp-btn {
    display:inline-flex; align-items:center; gap:8px;
    padding:14px 22px; border-radius:10px; font-size:15px; font-weight:600;
    text-decoration:none; transition:all .18s ease;
  }
  .lp-btn-primary {
    background:var(--ac); color:#fff;
    box-shadow:0 8px 24px -8px var(--acg),inset 0 1px 0 rgba(255,255,255,.18);
  }
  .lp-btn-primary:hover { background:var(--ac2); transform:translateY(-2px); }
  .lp-btn-secondary { background:transparent; color:var(--tx); border:1px solid var(--ln); }
  .lp-btn-secondary:hover { background:rgba(255,255,255,.04); border-color:rgba(46,134,193,.4); }
  .lp-btn-arrow { transition:transform .18s; }
  .lp-btn:hover .lp-btn-arrow { transform:translateX(3px); }
  .lp-hero-trust {
    margin-top:48px; display:flex; gap:28px; flex-wrap:wrap;
    color:var(--tx3); font-size:12px; text-transform:uppercase; letter-spacing:.12em;
  }
  .lp-trust-item { display:flex; align-items:center; gap:8px; }
  .lp-trust-item::before { content:""; width:4px; height:4px; border-radius:50%; background:var(--ac); }
  /* globe */
  .hero-globe-wrap {
    position:relative; aspect-ratio:1/1; width:100%; max-width:620px; justify-self:end;
  }
  .globe-mount {
    position:absolute; inset:0; width:100%; height:100%;
  }
  .globe-rings {
    position:absolute; inset:0; pointer-events:none; border-radius:50%; z-index:1;
  }
  .globe-rings::before,.globe-rings::after {
    content:""; position:absolute; inset:6%;
    border:1px dashed rgba(46,134,193,.18); border-radius:50%;
    animation:lp-spin 80s linear infinite;
  }
  .globe-rings::after { inset:-2%; border:1px solid rgba(46,134,193,.08); animation-duration:120s; animation-direction:reverse; }
  @keyframes lp-spin{to{transform:rotate(360deg)}}
  .globe-overlay-stat {
    position:absolute; z-index:2; background:rgba(13,27,42,.78);
    border:1px solid var(--ln); backdrop-filter:blur(10px);
    border-radius:12px; padding:10px 14px; display:flex; flex-direction:column;
    font-family:'JetBrains Mono',monospace; pointer-events:none;
    animation:lp-float 6s ease-in-out infinite;
  }
  .gos-lbl { font-size:9px; color:var(--tx3); text-transform:uppercase; letter-spacing:.14em; }
  .gos-val { font-size:16px; color:var(--tx); font-weight:600; margin-top:2px; }
  .gos-acc { color:var(--ac2); }
  .gos-1 { top:10%; left:-2%; }
  .gos-2 { bottom:18%; right:-4%; animation-delay:-2s; }
  .gos-3 { bottom:4%; left:8%; animation-delay:-4s; }
  @keyframes lp-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
  .globe-hint {
    position:absolute; bottom:-8px; left:50%; transform:translateX(-50%); z-index:2;
    font-family:'JetBrains Mono',monospace; font-size:10px;
    color:var(--tx3); letter-spacing:.1em; text-transform:uppercase;
    opacity:0; transition:opacity .5s;
  }
  .globe-hint.shown { opacity:1; }
  /* stats */
  .lp-stats {
    position:relative; z-index:1; max-width:1440px; margin:0 auto;
    padding:24px 40px 40px; display:grid; grid-template-columns:repeat(3,1fr); gap:16px;
  }
  .lp-stat-card {
    background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,0));
    border:1px solid var(--ln2); border-radius:14px; padding:22px 24px;
    position:relative; overflow:hidden; transition:border-color .2s,transform .2s;
  }
  .lp-stat-card:hover { border-color:var(--ln); transform:translateY(-2px); }
  .lp-stat-card::before {
    content:""; position:absolute; top:0; left:24px; right:24px; height:1px;
    background:linear-gradient(90deg,transparent,var(--ac),transparent); opacity:.4;
  }
  .lp-stat-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
  .lp-stat-label { font-size:12px; font-weight:500; color:var(--tx3); text-transform:uppercase; letter-spacing:.1em; }
  .lp-stat-pill {
    font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--good);
    padding:3px 8px; background:rgba(61,214,140,.1); border:1px solid rgba(61,214,140,.25);
    border-radius:999px; display:inline-flex; align-items:center; gap:5px;
  }
  .lp-stat-pill::before {
    content:""; width:5px; height:5px; border-radius:50%;
    background:var(--good); box-shadow:0 0 6px var(--good);
    animation:lp-pulse 1.6s ease-in-out infinite;
  }
  .lp-stat-value {
    font-size:40px; font-weight:700; letter-spacing:-.03em; line-height:1;
    font-variant-numeric:tabular-nums; margin-bottom:6px;
  }
  .lp-stat-trend { font-size:12px; margin-bottom:10px; }
  .lp-trend-up   { color:var(--good); }
  .lp-trend-down { color:var(--dng); }
  .lp-skel {
    height:40px; width:140px; border-radius:6px;
    background:linear-gradient(90deg,rgba(255,255,255,.04) 25%,rgba(255,255,255,.10) 50%,rgba(255,255,255,.04) 75%);
    background-size:200% 100%; animation:lp-shimmer 1.4s ease-in-out infinite;
  }
  @keyframes lp-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
  .lp-spark { width:100%; height:32px; display:block; }
  /* section */
  .lp-section { position:relative; z-index:1; max-width:1440px; margin:0 auto; padding:60px 40px; }
  .lp-section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:32px; flex-wrap:wrap; }
  .lp-eyebrow {
    font-family:'JetBrains Mono',monospace; font-size:11px;
    color:var(--ac2); text-transform:uppercase; letter-spacing:.18em;
    margin-bottom:14px; display:flex; align-items:center; gap:10px;
  }
  .lp-eyebrow::before { content:""; width:16px; height:1px; background:var(--ac); }
  .lp-section-title { font-size:40px; font-weight:700; letter-spacing:-.025em; line-height:1.05; max-width:600px; margin:0; }
  .lp-section-sub   { font-size:16px; color:var(--tx2); max-width:380px; line-height:1.55; text-align:right; }
  /* features */
  .lp-features { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .lp-feature {
    position:relative; text-decoration:none; color:inherit;
    background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,0));
    border:1px solid var(--ln2); border-radius:14px; padding:24px;
    transition:transform .25s,border-color .25s,box-shadow .25s;
    overflow:hidden; display:flex; flex-direction:column; min-height:240px;
  }
  .lp-feature::before {
    content:""; position:absolute; top:0; left:0; right:0; height:1px;
    background:linear-gradient(90deg,transparent,var(--ac),transparent);
    opacity:0; transition:opacity .25s;
  }
  .lp-feature:hover { transform:translateY(-4px); border-color:rgba(46,134,193,.35); box-shadow:0 18px 40px -20px rgba(46,134,193,.5); }
  .lp-feature:hover::before { opacity:1; }
  .lp-feat-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:18px; }
  .lp-feat-icon {
    width:44px; height:44px; border-radius:10px;
    background:rgba(46,134,193,.10); border:1px solid var(--ln);
    display:flex; align-items:center; justify-content:center; font-size:22px;
  }
  .lp-feat-tag  { font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--tx3); letter-spacing:.1em; }
  .lp-feat-name { font-size:18px; font-weight:600; letter-spacing:-.01em; margin-bottom:8px; }
  .lp-feat-desc { font-size:14px; color:var(--tx2); line-height:1.55; flex-grow:1; margin-bottom:18px; }
  .lp-feat-link {
    display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600;
    color:var(--ac2); align-self:flex-start; padding:8px 12px;
    border:1px solid var(--ln); background:rgba(46,134,193,.05);
    border-radius:8px; transition:background .18s,border-color .18s;
  }
  .lp-feature:hover .lp-feat-link { background:rgba(46,134,193,.15); border-color:rgba(46,134,193,.5); }
  /* bottom cta */
  .lp-bottom-cta {
    position:relative; z-index:1; max-width:1440px; margin:40px auto 0;
    padding:60px 40px; border-top:1px solid var(--ln2); text-align:center;
  }
  .lp-bottom-cta::before {
    content:""; position:absolute; left:50%; top:-1px; transform:translateX(-50%);
    width:320px; height:2px; background:linear-gradient(90deg,transparent,var(--ac),transparent);
  }
  .lp-bottom-cta h2 { font-size:44px; font-weight:700; letter-spacing:-.025em; margin-bottom:12px; }
  .lp-bottom-cta p  { color:var(--tx2); font-size:16px; max-width:480px; margin:0 auto 28px; }
  .lp-bottom-actions { display:flex; justify-content:center; gap:12px; flex-wrap:wrap; }
  /* footer */
  .lp-footer {
    position:relative; z-index:1;
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;
    padding:28px 40px; border-top:1px solid var(--ln2);
    font-size:13px; color:var(--tx3);
  }
  .lp-footer-links { display:flex; gap:20px; }
  .lp-footer-link  { color:var(--tx3); text-decoration:none; transition:color .12s; }
  .lp-footer-link:hover { color:var(--tx2); }
  /* responsive */
  @media(max-width:1024px){
    .lp-hero    { grid-template-columns:1fr; padding:48px 28px; gap:32px; }
    .hero-globe-wrap { max-width:480px; margin:0 auto; justify-self:center; }
    .lp-stats   { grid-template-columns:1fr; padding:16px 28px 28px; }
    .lp-features { grid-template-columns:repeat(2,1fr); }
    .lp-section { padding:48px 28px; }
    .lp-section-sub { text-align:left; }
  }
  @media(max-width:640px){
    .lp-hero   { padding:32px 20px; min-height:auto; }
    .lp-hero-title { font-size:56px!important; }
    .lp-features { grid-template-columns:1fr; }
    .lp-section { padding:36px 20px; }
    .lp-section-title { font-size:30px; }
    .lp-section-head  { flex-direction:column; align-items:flex-start; }
    .lp-section-sub   { text-align:left; max-width:100%; }
    .lp-bottom-cta { padding:48px 20px; }
    .lp-bottom-cta h2 { font-size:30px; }
    .globe-overlay-stat { display:none; }
    .lp-footer { padding:20px; flex-direction:column; align-items:flex-start; }
  }
`;

/* ─── page ───────────────────────────────────────────────────────── */
export default function Home() {
  /* inject styles */
  useEffect(() => {
    const el = document.createElement('style');
    el.id = 'lp-styles';
    el.textContent = LP_CSS;
    document.head.appendChild(el);
    return () => { el.remove(); };
  }, []);

  /* api stats */
  const [violations, setViolations] = useState<StatState>({ value: '-', loading: true });
  const [zones,      setZones]      = useState<StatState>({ value: '-', loading: true });
  const [warnings,   setWarnings]   = useState<StatState>({ value: '-', loading: true });

  useEffect(() => {
    const ac  = new AbortController();
    const sig = ac.signal;

    fetch(`${API}/violations/stats`, { signal: sig })
      .then(r => r.json())
      .then(d => setViolations({ value: (d.total ?? 0).toLocaleString(), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setViolations({ value: '-', loading: false }); });

    fetch(`${API}/api/zones`, { signal: sig })
      .then(r => r.json())
      .then(d => setZones({ value: String((d.zones ?? []).length), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setZones({ value: '-', loading: false }); });

    fetch(`${API}/api/warnings`, { signal: sig })
      .then(r => r.json())
      .then(d => setWarnings({ value: String((d.warnings ?? []).length), loading: false }))
      .catch(e => { if (e?.name !== 'AbortError') setWarnings({ value: '-', loading: false }); });

    return () => ac.abort();
  }, []);

  return (
    <main
      className="lp-root landing-page"
      style={{ background: '#0D1B2A', color: '#F5F8FB', minHeight: '100vh', padding: 0, maxWidth: 'none', margin: 0 }}
    >
      <div className="lp-bg" />

      {/* ── hero ── */}
      <section className="lp-hero">
        <div className="lp-hero-text">
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
        </div>

        <Globe pointCount={200} />
      </section>

      {/* ── stats ── */}
      <section className="lp-stats">
        <StatCard
          label="Violations Tracked" stat={violations}
          spark={[12,18,14,22,25,21,28,24,30,33,31,38]} color="#5DADE2"
        />
        <StatCard
          label="Active Zones" stat={zones}
          spark={[170,172,171,174,176,178,177,179,181,180,183,184]} color="#3DD68C"
        />
        <StatCard
          label="Warnings Detected" stat={warnings}
          spark={[35,38,42,39,36,33,31,34,30,29,28,27]} color="#F4B740"
        />
      </section>

      {/* ── features ── */}
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
              <span className="lp-feat-link">
                Open
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* ── bottom cta ── */}
      <section className="lp-bottom-cta">
        <h2>Ready to deploy smarter?</h2>
        <p>
          Select your zones, set a horizon, and get a unified recommendation in seconds —
          backed by live data and explainable evidence.
        </p>
        <div className="lp-bottom-actions">
          <Link href="/decision" className="lp-btn lp-btn-primary">
            Open Decision Dashboard <span className="lp-btn-arrow">→</span>
          </Link>
          <Link href="/map" className="lp-btn lp-btn-secondary">Explore the Map</Link>
        </div>
      </section>

      {/* ── footer ── */}
      <footer className="lp-footer">
        <div>© 2026 Traffic-lyt · Smart-City Analytics</div>
        <div className="lp-footer-links">
          <a className="lp-footer-link" href="https://github.com/achintya924/Traffic-lyt" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
        </div>
      </footer>
    </main>
  );
}
