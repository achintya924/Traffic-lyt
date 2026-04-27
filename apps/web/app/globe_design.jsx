/* global THREE, React */
// Three.js animated globe with violation hotspots + connecting lines.
// Auto-rotates; drag to rotate. No external textures — wireframe + dotted earth.

const Globe = ({ pointCount = 200 }) => {
  const mountRef = React.useRef(null);
  const [hintShown, setHintShown] = React.useState(true);

  React.useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const W = mount.clientWidth;
    const H = mount.clientHeight;

    // ── scene / camera / renderer ─────────────────────────
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    camera.position.set(0, 0, 5.2);

    const renderer = new THREE.WebGLRenderer({
      canvas: mount,
      antialias: true,
      alpha: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H, false);

    // root group we rotate
    const earth = new THREE.Group();
    scene.add(earth);

    // ── translucent sphere shell (deep navy) ──────────────
    const shellGeo = new THREE.SphereGeometry(1.5, 64, 64);
    const shellMat = new THREE.MeshBasicMaterial({
      color: 0x0a1622,
      transparent: true,
      opacity: 0.92,
    });
    const shell = new THREE.Mesh(shellGeo, shellMat);
    earth.add(shell);

    // ── glowing inner halo (back-side sphere) ─────────────
    const haloGeo = new THREE.SphereGeometry(1.55, 64, 64);
    const haloMat = new THREE.MeshBasicMaterial({
      color: 0x2E86C1,
      transparent: true,
      opacity: 0.06,
      side: THREE.BackSide,
    });
    earth.add(new THREE.Mesh(haloGeo, haloMat));

    // ── outer atmosphere (front-side bigger sphere) ───────
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

    // ── wireframe latitude/longitude ──────────────────────
    const wireGeo = new THREE.SphereGeometry(1.502, 32, 18);
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x2E86C1,
      transparent: true,
      opacity: 0.18,
    });
    const wire = new THREE.LineSegments(
      new THREE.WireframeGeometry(wireGeo),
      wireMat
    );
    earth.add(wire);

    // ── continent dots (procedural — no texture file) ─────
    // generate tiny dots scattered on the globe to suggest land masses
    const continentDots = new THREE.Group();
    const dotGeo = new THREE.SphereGeometry(0.012, 6, 6);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x3a5d7d, transparent: true, opacity: 0.6 });
    // simple noise-ish bias toward landmass-shaped clumps using sin/cos
    for (let i = 0; i < 700; i++) {
      const u = Math.random();
      const v = Math.random();
      const theta = 2 * Math.PI * u;
      const phi = Math.acos(2 * v - 1);
      // crude land mask
      const lm =
        Math.sin(phi * 4) * Math.cos(theta * 3) +
        Math.cos(phi * 2 + 1) * Math.sin(theta * 2 - 0.7) +
        Math.sin(theta * 5 + phi);
      if (lm < 0.25) continue;
      const r = 1.508;
      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.cos(phi);
      const z = r * Math.sin(phi) * Math.sin(theta);
      const m = new THREE.Mesh(dotGeo, dotMat);
      m.position.set(x, y, z);
      continentDots.add(m);
    }
    earth.add(continentDots);

    // ── violation hotspots ─────────────────────────────────
    const hotspots = [];
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
      // 3 severities
      const severity = Math.random();
      const color =
        severity > 0.85 ? 0xE55353 : severity > 0.55 ? 0xF4B740 : 0x5DADE2;

      // glowing dot
      const dotMaterial = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.95,
      });
      const dot = new THREE.Mesh(hotGeo, dotMaterial);
      dot.position.copy(pos);
      hotspotGroup.add(dot);

      // pulsing ring (oriented outward)
      const ringMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.6,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.position.copy(pos);
      ring.lookAt(pos.clone().multiplyScalar(2)); // face outward
      hotspotGroup.add(ring);

      hotspots.push({ pos, ring, ringMat, phase: Math.random() * Math.PI * 2, severity });
    }

    // ── connecting arcs between near hotspots ─────────────
    const arcGroup = new THREE.Group();
    earth.add(arcGroup);

    const arcMat = new THREE.LineBasicMaterial({
      color: 0x2E86C1,
      transparent: true,
      opacity: 0.35,
    });

    // Connect each hotspot to its ~2 nearest neighbors (within distance threshold)
    const MAX_LINKS_PER = 2;
    const DIST_THRESHOLD = 0.9;
    const made = new Set();
    for (let i = 0; i < hotspots.length; i++) {
      const a = hotspots[i].pos;
      // find nearest
      const cands = [];
      for (let j = 0; j < hotspots.length; j++) {
        if (i === j) continue;
        const d = a.distanceTo(hotspots[j].pos);
        if (d < DIST_THRESHOLD) cands.push({ j, d });
      }
      cands.sort((x, y) => x.d - y.d);
      cands.slice(0, MAX_LINKS_PER).forEach(({ j }) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (made.has(key)) return;
        made.add(key);
        const b = hotspots[j].pos;

        // build a curved arc that lifts off the surface
        const mid = a.clone().add(b).multiplyScalar(0.5);
        const lift = 1 + a.distanceTo(b) * 0.3; // farther = higher arc
        mid.normalize().multiplyScalar(1.51 * lift);
        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const points = curve.getPoints(24);
        const g = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(g, arcMat.clone());
        arcGroup.add(line);
      });
    }

    // ── interaction: drag to rotate, auto rotate when idle
    let isDragging = false;
    let lastX = 0;
    let lastY = 0;
    let rotVelX = 0;
    let rotVelY = 0;
    const AUTO = 0.0015;
    let userInteracted = false;

    const onDown = (e) => {
      isDragging = true;
      userInteracted = true;
      setHintShown(false);
      const p = e.touches ? e.touches[0] : e;
      lastX = p.clientX;
      lastY = p.clientY;
      rotVelX = rotVelY = 0;
    };
    const onMove = (e) => {
      if (!isDragging) return;
      e.preventDefault?.();
      const p = e.touches ? e.touches[0] : e;
      const dx = p.clientX - lastX;
      const dy = p.clientY - lastY;
      lastX = p.clientX;
      lastY = p.clientY;
      rotVelY = dx * 0.005;
      rotVelX = dy * 0.005;
      earth.rotation.y += rotVelY;
      earth.rotation.x = Math.max(-1.2, Math.min(1.2, earth.rotation.x + rotVelX));
    };
    const onUp = () => { isDragging = false; };

    mount.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    mount.addEventListener('touchstart', onDown, { passive: true });
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onUp);

    // ── resize ────────────────────────────────────────────
    const onResize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(mount);

    // start tilted
    earth.rotation.x = -0.3;
    earth.rotation.y = 0.6;

    // ── animate ───────────────────────────────────────────
    let raf = 0;
    const t0 = performance.now();
    const animate = () => {
      const t = (performance.now() - t0) / 1000;

      // momentum + idle auto-spin
      if (!isDragging) {
        // residual momentum
        rotVelY *= 0.94;
        rotVelX *= 0.94;
        earth.rotation.y += rotVelY;
        earth.rotation.x += rotVelX;
        // auto-spin
        earth.rotation.y += AUTO;
      }

      // pulse rings
      for (let i = 0; i < hotspots.length; i++) {
        const h = hotspots[i];
        const k = (Math.sin(t * 1.6 + h.phase) + 1) / 2; // 0..1
        const s = 1 + k * 1.6;
        h.ring.scale.setScalar(s);
        h.ringMat.opacity = (1 - k) * 0.7;
      }

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };
    animate();

    // hide hint after 6s even without interaction
    const hintT = setTimeout(() => setHintShown(false), 6000);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(hintT);
      ro.disconnect();
      mount.removeEventListener('mousedown', onDown);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      mount.removeEventListener('touchstart', onDown);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
      renderer.dispose();
      shellGeo.dispose(); shellMat.dispose();
      haloGeo.dispose(); haloMat.dispose();
      atmGeo.dispose(); atmMat.dispose();
      wireGeo.dispose(); wireMat.dispose();
      ringGeo.dispose(); hotGeo.dispose();
    };
  }, [pointCount]);

  return (
    <div className="hero-globe-wrap">
      <div className="globe-rings"></div>
      <canvas id="globe-canvas" ref={mountRef}></canvas>
      <div className="globe-overlay-stat gos-1">
        <span className="lbl">Live Feed</span>
        <span className="val"><span className="acc">●</span> 1,247 / sec</span>
      </div>
      <div className="globe-overlay-stat gos-2">
        <span className="lbl">Coverage</span>
        <span className="val">42 cities</span>
      </div>
      <div className="globe-overlay-stat gos-3">
        <span className="lbl">Latency</span>
        <span className="val">87 ms</span>
      </div>
      <div className={`globe-hint ${hintShown ? 'shown' : ''}`}>Drag to rotate</div>
    </div>
  );
};

window.Globe = Globe;
