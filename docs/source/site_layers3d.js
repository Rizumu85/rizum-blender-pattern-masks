// Overview: a small toon skirt that wears every kind of layer. Hovering,
// focusing or tapping a kind in the list turns the camera to it and fades the
// others back; the stitches switch between dashed and zigzag while they are
// shown. Without WebGL the render (the <img>) stays in its place.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.min.js";

// the skirt: a flared tube from the waist down to a scalloped hem
const LOBES = 10, R0 = 0.42, R1 = 0.98, LENGTH = 1.05, SCALLOP = 0.1, TOP = 0.55;
const TAU = Math.PI * 2;
const drop = (u) => LENGTH + SCALLOP * Math.pow(Math.abs(Math.sin(LOBES * u / 2)), 0.6);
const radius = (u, v) => (R0 + (R1 - R0) * Math.pow(v, 0.8)) * (1 - 0.045 * v * Math.cos(LOBES * u));

function surf(u, v, out = new THREE.Vector3()) {
  const r = radius(u, v);
  return out.set(r * Math.cos(u), TOP - v * drop(u), r * Math.sin(u));
}

// colours (sRGB, as in the page)
const C = {
  fabric: 0xF7EFE1, check: 0x7383A3, inside: 0xD9CDBA, band: 0x2E3D5E, bow: 0xEE8E9C,
  stitch: 0xE07A2B, line: 0x22304A,
};

function start(root) {
  const stage = root.querySelector(".l3d-stage");
  const canvas = stage.querySelector("canvas");
  const items = [...root.querySelectorAll(".l3d-list li")];
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (e) {
    return;                                              // the render stays
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 50);
  const LIGHT = new THREE.Vector3(0.45, 0.6, 0.66).normalize();
  scene.add(new THREE.AmbientLight(0xffffff, 1.5));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.copy(LIGHT).multiplyScalar(5);
  scene.add(sun);

  const ramp = new THREE.DataTexture(new Uint8Array([120, 190, 255]), 3, 1, THREE.RedFormat);
  ramp.minFilter = ramp.magFilter = THREE.NearestFilter;
  ramp.needsUpdate = true;
  const toon = (hex) => new THREE.MeshToonMaterial({ color: hex, gradientMap: ramp });

  const skirt = new THREE.Group();
  scene.add(skirt);

  // -- the cloth: checks drawn in the shader, columns around and rows down
  const U = 320, V = 64;
  const pos = [], vs = [], idx = [];
  const p = new THREE.Vector3();
  for (let j = 0; j <= V; j++) {
    for (let i = 0; i < U; i++) {
      surf(i / U * TAU, j / V, p);
      pos.push(p.x, p.y, p.z);
      vs.push(j / V);
    }
  }
  for (let j = 0; j < V; j++) {
    for (let i = 0; i < U; i++) {
      const a = j * U + i, b = j * U + (i + 1) % U, c = a + U, d = b + U;
      idx.push(a, b, c, b, d, c);
    }
  }
  const cloth = new THREE.BufferGeometry();
  cloth.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  cloth.setAttribute("aV", new THREE.Float32BufferAttribute(vs, 1));
  cloth.setIndex(idx);
  cloth.computeVertexNormals();
  const n0 = new THREE.Vector3().fromBufferAttribute(cloth.attributes.normal, U * (V >> 1));
  const p0 = new THREE.Vector3().fromBufferAttribute(cloth.attributes.position, U * (V >> 1));
  if (n0.x * p0.x + n0.z * p0.z < 0) {                   // wind the faces outward
    for (let k = 0; k < idx.length; k += 3) [idx[k + 1], idx[k + 2]] = [idx[k + 2], idx[k + 1]];
    cloth.setIndex(idx);
    cloth.computeVertexNormals();
  }
  const clothMat = new THREE.ShaderMaterial({
    side: THREE.DoubleSide,
    uniforms: {
      uFabric: { value: new THREE.Color(C.fabric) }, uCheck: { value: new THREE.Color(C.check) },
      uInside: { value: new THREE.Color(C.inside) }, uLight: { value: LIGHT },
      uGrid: { value: 1 }, uCols: { value: 28 }, uRows: { value: 7 },
    },
    vertexShader: `
      attribute float aV;
      varying float vV; varying vec3 vObj; varying vec3 vN;
      void main() {
        vV = aV; vObj = position; vN = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 uFabric, uCheck, uInside, uLight;
      uniform float uGrid, uCols, uRows;
      varying float vV; varying vec3 vObj; varying vec3 vN;
      float checks(vec2 q, vec2 w) {               // box-filtered, so it doesn't shimmer
        w = max(w, vec2(1e-4));
        vec2 i = 2.0 * (abs(fract((q - 0.5 * w) * 0.5) - 0.5) - abs(fract((q + 0.5 * w) * 0.5) - 0.5)) / w;
        return 0.5 - 0.5 * i.x * i.y;
      }
      void main() {
        float a = atan(vObj.z, vObj.x) / 6.2831853;
        float a1 = fract(a), wa = min(fwidth(a1), fwidth(fract(a + 0.5)));
        vec2 q = vec2(a1 * uCols, vV * uRows);
        float c = checks(q, vec2(wa * uCols, fwidth(q.y)));
        vec3 n = normalize(vN);
        vec3 base = mix(uFabric, uCheck, c * uGrid);
        if (!gl_FrontFacing) { n = -n; base = uInside; }
        float d = dot(n, uLight);
        float t = d > 0.42 ? 1.0 : d > -0.12 ? 0.86 : 0.72;
        gl_FragColor = vec4(base * t, 1.0);
        #include <colorspace_fragment>
      }`,
  });
  skirt.add(new THREE.Mesh(cloth, clothMat));

  // -- the waistband and a bow at the front
  const band = toon(C.band);
  const bandH = 0.15, bandR = R0 * 1.035;
  const tube = new THREE.Mesh(new THREE.CylinderGeometry(bandR, bandR * 1.01, bandH, 96, 1, true), band);
  tube.material.side = THREE.DoubleSide;
  tube.position.y = TOP + bandH / 2 - 0.01;
  skirt.add(tube);
  const rim = new THREE.Mesh(new THREE.TorusGeometry(bandR, 0.018, 8, 96), band);
  rim.rotation.x = Math.PI / 2;
  rim.position.y = TOP + bandH - 0.01;
  skirt.add(rim);
  const bow = new THREE.Group();
  const bowMat = toon(C.bow);
  for (const s of [-1, 1]) {
    const loop = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), bowMat);
    loop.scale.set(0.105, 0.07, 0.04);
    loop.position.set(s * 0.095, 0.012, 0);
    loop.rotation.z = s * 0.35;
    bow.add(loop);
    const tail = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), bowMat);
    tail.scale.set(0.03, 0.085, 0.022);
    tail.position.set(s * 0.045, -0.085, 0.005);
    tail.rotation.z = s * 0.4;
    bow.add(tail);
  }
  const knot = new THREE.Mesh(new THREE.SphereGeometry(0.038, 16, 12), bowMat);
  knot.position.z = 0.02;
  bow.add(knot);
  bow.position.set(0, TOP + bandH / 2 - 0.01, bandR + 0.035);
  skirt.add(bow);

  // -- curves on the cloth: v as a function of u, lifted off it a little
  const E = 1e-4;
  function curve(vOf, lift) {
    const M = 1600, pts = [], ups = [], cum = [0];
    const a = new THREE.Vector3(), b = new THREE.Vector3(), du = new THREE.Vector3(), dv = new THREE.Vector3();
    for (let i = 0; i < M; i++) {
      const u = i / M * TAU, v = vOf(u);
      const pt = surf(u, v);
      du.subVectors(surf(u + E, v, a), surf(u - E, v, b));
      dv.subVectors(surf(u, Math.min(1, v + E), a), surf(u, Math.max(0, v - E), b));
      const n = new THREE.Vector3().crossVectors(dv, du).normalize();
      if (n.x * pt.x + n.z * pt.z < 0) n.negate();
      pts.push(pt.addScaledVector(n, lift));
      ups.push(dv.clone().negate().normalize());
      if (i) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
    }
    const total = cum[M - 1] + pts[0].distanceTo(pts[M - 1]);
    function at(s, out = new THREE.Vector3(), up) {      // the point s along it
      s = ((s % total) + total) % total;
      let lo = 0, hi = M - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (cum[mid] <= s) lo = mid; else hi = mid - 1; }
      const nx = (lo + 1) % M, seg = (nx ? cum[nx] : total) - cum[lo], t = seg ? (s - cum[lo]) / seg : 0;
      if (up) up.lerpVectors(ups[lo], ups[nx], t).normalize();
      return out.lerpVectors(pts[lo], pts[nx], t);
    }
    return { pts, total, at };
  }
  const near = (inset) => (u) => 1 - inset / (drop(u) * 1.12);

  const Y = new THREE.Vector3(0, 1, 0);
  function placeSegment(m, i, a, b, scaleY) {
    const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
    const dir = new THREE.Vector3().subVectors(b, a);
    const len = dir.length();
    const q = new THREE.Quaternion().setFromUnitVectors(Y, dir.normalize());
    m.setMatrixAt(i, new THREE.Matrix4().compose(mid, q, new THREE.Vector3(1, scaleY ? len : 1, 1)));
  }

  // stitches: dashes, or one zigzag thread
  const stitchMat = toon(C.stitch);
  const sc = curve(near(0.09), 0.012);
  const DASH = 0.06, GAP = 0.036, TH = 0.013;
  const nDash = Math.floor(sc.total / (DASH + GAP));
  const step = sc.total / nDash;
  const dashes = new THREE.InstancedMesh(new THREE.CapsuleGeometry(TH, DASH - 2 * TH, 4, 8), stitchMat, nDash);
  const A = new THREE.Vector3(), B = new THREE.Vector3();
  for (let i = 0; i < nDash; i++) {
    sc.at(i * step, A); sc.at(i * step + DASH, B);
    placeSegment(dashes, i, A, B, false);
  }
  skirt.add(dashes);
  const ZSTEP = 0.05, ZH = 0.034;
  const nZig = Math.round(sc.total / ZSTEP) & ~1;       // even, so the loop closes
  const zpts = [];
  const up = new THREE.Vector3();
  for (let i = 0; i < nZig; i++) {
    const pt = sc.at(i * sc.total / nZig, new THREE.Vector3(), up);
    zpts.push(pt.addScaledVector(up, (i % 2 ? 1 : -1) * ZH / 2));
  }
  const zig = new THREE.Group();
  const bars = new THREE.InstancedMesh(new THREE.CylinderGeometry(TH * 0.8, TH * 0.8, 1, 8), stitchMat, nZig);
  const joints = new THREE.InstancedMesh(new THREE.SphereGeometry(TH * 0.8, 8, 6), stitchMat, nZig);
  for (let i = 0; i < nZig; i++) {
    placeSegment(bars, i, zpts[i], zpts[(i + 1) % nZig], true);
    joints.setMatrixAt(i, new THREE.Matrix4().makeTranslation(zpts[i].x, zpts[i].y, zpts[i].z));
  }
  zig.add(bars, joints);
  zig.visible = false;
  skirt.add(zig);

  // line art: a trim along the hem and a line a little below the waistband
  const lineMat = toon(C.line);
  for (const c of [curve(near(0.022), 0.01), curve(() => 0.14, 0.01)]) {
    const path = new THREE.CatmullRomCurve3(c.pts, true, "centripetal");
    skirt.add(new THREE.Mesh(new THREE.TubeGeometry(path, 1600, 0.014, 6, true), lineMat));
  }

  // a soft shadow under it
  const g = document.createElement("canvas");
  g.width = g.height = 128;
  const ctx = g.getContext("2d");
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 62);
  grad.addColorStop(0, "rgba(20,24,36,0.42)");
  grad.addColorStop(1, "rgba(20,24,36,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.5, 2.5),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(g), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = TOP - LENGTH - SCALLOP - 0.06;
  scene.add(shadow);

  // -- focus: where the camera goes, and what stays bright
  const VIEWS = {
    all: { pos: [0, 0.85, 4.75], look: [0, -0.02, 0] },
    stitch: { pos: [0.42, -0.3, 1.95], look: [0.05, -0.52, 0.72] },
    line: { pos: [-0.35, 0.5, 3.0], look: [0, 0.0, 0.25] },
    grid: { pos: [0, 0.55, 3.4], look: [0, -0.04, 0] },
  };
  const camPos = new THREE.Vector3(...VIEWS.all.pos), camLook = new THREE.Vector3(...VIEWS.all.look);
  const goPos = camPos.clone(), goLook = camLook.clone();
  camera.position.copy(camPos);
  camera.lookAt(camLook);
  const fabric = new THREE.Color(C.fabric);
  const tone = { stitch: 1, line: 1, grid: 1 };          // 1 shown, 0 faded back
  let focus = null, zigOn = false, zigClock = 0;

  function setFocus(k) {
    if (k === focus) return;
    focus = k;
    const v = VIEWS[k || "all"];
    goPos.set(...v.pos);
    goLook.set(...v.look);
    items.forEach((li) => li.classList.toggle("on", li.dataset.k === k));
    zigClock = 0;
    if (k !== "stitch") zigOn = false;
  }

  let touched = false;
  for (const li of items) {
    li.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") setFocus(li.dataset.k); });
    li.addEventListener("focus", () => { if (!touched) setFocus(li.dataset.k); });
    li.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse") return;
      touched = true;
      setFocus(focus === li.dataset.k ? null : li.dataset.k);
      setTimeout(() => { touched = false; }, 400);
    });
  }
  root.querySelector(".l3d-list").addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") setFocus(null); });
  root.addEventListener("focusout", (e) => { if (!root.contains(e.relatedTarget)) setFocus(null); });
  document.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse" && !root.contains(e.target)) setFocus(null); });

  // -- size, and drawing only while on screen
  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const LOBE = TAU / LOBES;
  let rot = 0.35, last = 0, running = false, time = 0;

  function frame(now) {
    if (!running) return;
    const dt = Math.min(0.1, last ? (now - last) / 1000 : 0);
    last = now;
    time += dt;
    const k = still.matches ? 1 : 1 - Math.exp(-dt * 4.5);
    // turn while idle; when focused, come to rest with a scallop in front
    if (!focus && !still.matches) rot += dt * 0.32;
    else if (focus) rot += (Math.round(rot / LOBE) * LOBE - rot) * k;
    skirt.rotation.y = rot;
    skirt.position.y = still.matches ? 0 : Math.sin(time * 1.7) * 0.012;
    camPos.lerp(goPos, k);
    camLook.lerp(goLook, k);
    camera.position.copy(camPos);
    camera.lookAt(camLook);
    for (const name of ["stitch", "line", "grid"]) {
      tone[name] += ((!focus || focus === name ? 1 : 0) - tone[name]) * k;
    }
    clothMat.uniforms.uGrid.value = 0.12 + 0.88 * tone.grid;
    stitchMat.color.set(C.stitch).lerp(fabric, 0.78 * (1 - tone.stitch));
    lineMat.color.set(C.line).lerp(fabric, 0.8 * (1 - tone.line));
    if (focus === "stitch") {                            // the two kinds, in turn
      zigClock += dt;
      if (zigClock > 1.8) { zigClock = 0; zigOn = !zigOn; }
    }
    dashes.visible = !zigOn;
    zig.visible = zigOn;
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  function run(on) {
    if (on === running) return;
    running = on;
    last = 0;
    if (on) requestAnimationFrame(frame);
  }
  let seen = false;
  new IntersectionObserver(([e]) => { seen = e.isIntersecting; run(seen && !document.hidden); }).observe(stage);
  document.addEventListener("visibilitychange", () => run(seen && !document.hidden));
  renderer.render(scene, camera);
  stage.classList.add("live");
}

const root = document.querySelector(".l3d");
if (root) start(root);
