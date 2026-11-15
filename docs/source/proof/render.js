// The README proof board's 3D shots: the docs overview's toon skirt
// (site_layers3d.js) with fixed cameras, saved through serve.py. Differences
// from the docs copy: the stitch line rounds the scallop points, and the zigzag
// goes across the thread. Run shots() in the console, then compose.py.
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
  fabric: 0xF7EFE1, check: 0x7383A3, inside: 0xD9CDBA, band: 0x2E3D5E,
  stitch: 0xE07A2B, line: 0x22304A,
};

function start(root) {
  const stage = root.querySelector(".l3d-stage");
  const canvas = stage.querySelector("canvas");
  const items = [...root.querySelectorAll(".l3d-list li")];
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  } catch (e) {
    return;                                              // the render stays
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // placed here too, not only in the stylesheet: a canvas left in the flow
  // would make the stage grow with every resize
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
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

  // -- the waistband
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
  // the stitch line rounds the scallop points (as the add-on's smoothing does)
  const soft = (u) => { let t = 0; for (let k = -6; k <= 6; k++) t += drop(u + k * 0.011); return t / 13; };
  const sc = curve((u) => Math.min(0.995, (soft(u) - 0.085) / drop(u)), 0.012);
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
  const ZSTEP = 0.04, ZH = 0.03;
  const nZig = Math.round(sc.total / ZSTEP) & ~1;       // even, so the loop closes
  const zpts = [];
  const up = new THREE.Vector3();
  for (let i = 0; i < nZig; i++) {
    const s0 = i * sc.total / nZig;
    const pt = sc.at(s0, new THREE.Vector3(), up);
    const t = sc.at(s0 + 0.004).sub(sc.at(s0 - 0.004)).normalize();
    up.addScaledVector(t, -up.dot(t)).normalize();        // across the thread, on the cloth
    zpts.push(pt.addScaledVector(up, (i % 2 ? 1 : -1) * ZH / 2));
  }
  const zig_ = new THREE.Group();
  const bars = new THREE.InstancedMesh(new THREE.CylinderGeometry(TH * 0.8, TH * 0.8, 1, 8), stitchMat, nZig);
  const joints = new THREE.InstancedMesh(new THREE.SphereGeometry(TH * 0.8, 8, 6), stitchMat, nZig);
  for (let i = 0; i < nZig; i++) {
    placeSegment(bars, i, zpts[i], zpts[(i + 1) % nZig], true);
    joints.setMatrixAt(i, new THREE.Matrix4().makeTranslation(zpts[i].x, zpts[i].y, zpts[i].z));
  }
  zig_.add(bars, joints);
  zig_.visible = false;
  skirt.add(zig_);

  // line art: a trim along the hem and a line a little below the waistband
  const lineMat = toon(C.line);
  for (const c of [curve(() => 1, 0.004), curve(() => 0.14, 0.01)]) {   // the hem line on the edge itself
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

  // -- stills for the README: a fixed camera per shot, saved through the server
  const LOBE = TAU / LOBES;
  const fabric = new THREE.Color(C.fabric);
  window.shot = async ({ name, w, h, dpr = 2, pos, look, fov = 28, lobe = 0, turn = 0, zig = false,
                         focus = null, shadowOn = true }) => {
    renderer.setPixelRatio(dpr);
    stage.style.width = w + "px"; stage.style.height = h + "px";
    renderer.setSize(w, h, false);
    camera.fov = fov; camera.aspect = w / h; camera.updateProjectionMatrix();
    skirt.rotation.y = lobe * LOBE + turn;
    camera.position.set(...pos); camera.lookAt(new THREE.Vector3(...look));
    const tone = { stitch: 1, line: 1, grid: 1 };
    if (focus) for (const k in tone) tone[k] = k === focus ? 1 : 0;
    clothMat.uniforms.uGrid.value = 0.12 + 0.88 * tone.grid;
    stitchMat.color.set(C.stitch).lerp(fabric, 0.78 * (1 - tone.stitch));
    lineMat.color.set(C.line).lerp(fabric, 0.8 * (1 - tone.line));
    dashes.visible = !zig; zig_.visible = zig;
    shadow.visible = shadowOn;
    renderer.render(scene, camera);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
    const res = await fetch("/save?name=" + encodeURIComponent(name), { method: "POST", body: blob });
    return res.status + " " + name + " " + canvas.width + "x" + canvas.height;
  };
  window.shots = async () => {
    const close = { w: 756, h: 378, turn: Math.PI / 2, pos: [0.3, -0.15, 3.0], look: [0.05, -0.47, 0.8], fov: 15 };
    return [
      await shot({ name: "P_all", w: 948, h: 780, pos: [0, 0.75, 4.75], look: [0, -0.05, 0], fov: 24, turn: 0.35 }),
      await shot({ ...close, name: "P_dash" }),
      await shot({ ...close, name: "P_zig", zig: true }),
      // the featured image's skirt (docs/source/featured.html)
      await shot({ name: "F_skirt", w: 1080, h: 1000, pos: [0, 0.7, 4.6], look: [0, -0.16, 0], fov: 32,
                   turn: 0.35 }),
    ];
  };
}

const root = document.querySelector(".l3d");
if (root) start(root);
