// The sandboxes: a flat skirt piece and a copy of the add-on's panel, with a
// step-by-step guide on top. Each figure is a small demo of one idea, showing
// only the panel rows that idea needs. A legend (ol.um-keys[data-for=<figure
// id>]) names panel controls: pointing at a line spotlights its control, and
// pointing at a control shows its line there. A figure names its demo in data-sandbox (JSON with
// the demo's name, its step texts and the panel words).
//
// Each layer's pattern is an iso-line of the distance to its edges (marching
// squares over a small grid), like the add-on's: one-sided per edge (the side
// Flip Side picks), cut off square at open ends, round at unmarked corners and
// mitred at marked ones.

// The number on a lit control's corner, moved in where that corner meets the
// veil's edge (the veil clips what lies outside it).
function placeBadge(hole, x, y) {
  const b = hole.firstChild;
  b.style.left = Math.max(-9, 2 - x) + "px";
  b.style.top = Math.max(-9, 2 - y) + "px";
}

(() => {
  const figs = document.querySelectorAll("[data-sandbox]");
  if (!figs.length) return;   // replica panels and screenshots: see the end of this file
  const NS = "http://www.w3.org/2000/svg";
  const MM = 4;                         // view units per millimetre
  // the palette of the overview's 3D skirt
  const THREAD = "#E07A2B", NAVY = "#22304A", CHECK = "#7383A3", FABRIC = "#F7EFE1", PICK = "#2F6FD6";

  // -- the mesh: 4 rows of 5 vertices, four scallops along the hem ----------
  // (the taper is that of a piece that would reach up to y 40; it starts lower,
  // so the demos are wider than tall)
  const ROWS = [150, 260, 350, 430], LAST = ROWS.length - 1;
  const topX = (c) => 175 + 42.5 * c, botX = (c) => 60 + 100 * c;
  const V = [];
  const grid = ROWS.map((y) => [0, 1, 2, 3, 4].map((c) => {
    const t = (y - 40) / 390;
    V.push([topX(c) + (botX(c) - topX(c)) * t, y]);
    return V.length - 1;
  }));
  const E = [];
  function edge(a, b, ref, border) {
    const [ax, ay] = V[a], [bx, by] = V[b];
    const len = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / len, uy = (by - ay) / len;
    let nx = -uy, ny = ux;                               // the side the line goes to
    if (nx * ref[0] + ny * ref[1] < 0) { nx = -nx; ny = -ny; }
    E.push({ a, b, ux, uy, len, nx, ny, border });
    return E.length - 1;
  }
  const waist = [], hem = [], scallops = [], rows = {}, hemPts = [grid[LAST][0]];
  for (let c = 0; c < 4; c++) waist.push(edge(grid[0][c], grid[0][c + 1], [0, 1], true));
  const left = [], right = [];
  for (let r = 0; r < LAST; r++) {
    left.push(edge(grid[r][0], grid[r + 1][0], [1, 0], true));
    right.push(edge(grid[r][4], grid[r + 1][4], [-1, 0], true));
  }
  for (let c = 0; c < 4; c++) {                          // circular scallops, 8 edges each
    const half = 50, sag = 24, R = (half * half + sag * sag) / (2 * sag);
    const mx = (botX(c) + botX(c + 1)) / 2, cy = 430 + sag - R;
    const a0 = Math.atan2(430 - cy, -half), a1 = Math.atan2(430 - cy, half);
    const ids = [grid[LAST][c]];
    for (let k = 1; k < 8; k++) {
      const a = a0 + (a1 - a0) * k / 8;
      V.push([mx + R * Math.cos(a), cy + R * Math.sin(a)]);
      ids.push(V.length - 1);
    }
    ids.push(grid[LAST][c + 1]);
    const run = [];
    for (let k = 0; k < 8; k++) {
      const p = V[ids[k]], q = V[ids[k + 1]];
      run.push(edge(ids[k], ids[k + 1], [mx - (p[0] + q[0]) / 2, cy - (p[1] + q[1]) / 2], true));
    }
    scallops.push(run);
    hem.push(...run);
    hemPts.push(...ids.slice(1));
  }
  for (let r = 1; r < LAST; r++) {
    rows[r] = [];
    for (let c = 0; c < 4; c++) rows[r].push(edge(grid[r][c], grid[r][c + 1], [0, 1], false));
  }
  const cols = [1, 2, 3].map((c) => [...Array(LAST).keys()].map((r) => edge(grid[r][c], grid[r + 1][c], [1, 0], false)));
  // what one click selects: a scallop, the waist, a side, or a whole line inside
  const PIECES = [waist, left, right, ...scallops, ...Object.values(rows), ...cols];
  const pieceOf = [];
  PIECES.forEach((list, i) => list.forEach((e) => { pieceOf[e] = i; }));
  const hips = rows[1];
  const cusps = [grid[LAST][1], grid[LAST][2], grid[LAST][3]];
  const down = [...Array(LAST).keys()].map((r) => r + 1);           // 1 .. LAST
  const outline = [...grid[0], ...down.map((r) => grid[r][4]), ...hemPts.slice().reverse().slice(1),
                   ...down.slice(0, -1).reverse().map((r) => grid[r][0])];

  figs.forEach((fig, inst) => mount(fig, inst));

  function mount(fig, inst) {
  const S = JSON.parse(fig.dataset.sandbox);
  // -- state ----------------------------------------------------------------
  let st, nextId;
  function fresh() {
    nextId = 1;
    st = { layers: [], active: null, sel: new Set(), vsel: new Set(), corners: new Set(), showCorners: true,
           pick: false, menu: false, more: false, bgmenu: false, refmenu: false, pmenu: false, live: true, allMarks: true, step: 0,
           baked: false, view: "model", bg: "black", obj: "Skirt", mat: "Cloth",
           presets: [], star: null, pname: S.presetName || "", applied: false, usedDefault: false };
  }
  const byId = (id) => st.layers.find((l) => l.id === id);
  const activeL = () => byId(st.active);
  const stitchL = () => st.layers.find((l) => l.kind === "stitch");
  const lineL = () => st.layers.find((l) => l.kind === "line");
  const gridL = () => st.layers.find((l) => l.kind === "grid");
  const hasAll = (set, list) => list.every((x) => set.has(x));

  function finalEdges(L, seen = new Set()) {
    const out = new Set();
    if (!L || seen.has(L.id)) return out;
    seen.add(L.id);
    for (const e of finalEdges(byId(L.ref), seen)) out.add(e);
    for (const [e, v] of L.own) v > 0 ? out.add(e) : out.delete(e);
    return out;
  }
  const DEFAULTS = { stitch: { from: 3, width: 1.2, length: 4, gap: 2, height: 3, style: "dash" },
                     line: { from: 0, width: 0.5 }, grid: { from: 0, along: 0, angle: 0, cell: 8 } };
  function addLayer(kind, name) {
    const n = st.layers.filter((l) => l.kind === kind).length, k = n ? " " + (n + 1) : "";
    const L = Object.assign({ kind, color: kind === "stitch" ? THREAD : kind === "grid" ? CHECK : NAVY,
      name: name || (kind === "stitch" ? S.stitches + k : kind === "grid" ? S.grid : S.lineArt + k),
      file: "stitch" + (n ? n + 1 : "") },              // a stitch layer's default file name
      DEFAULTS[kind]);
    Object.assign(L, { id: nextId++, own: new Map(), ref: null, marks: true, visible: true, flip: false });
    st.layers.push(L);
    st.active = L.id;
    return L;
  }
  const ensure = (kind) => (kind === "stitch" ? stitchL() : lineL()) || addLayer(kind);
  const refersTo = (L, id) => { for (let q = L, n = 0; q && n < 20; q = byId(q.ref), n++) if (q.id === id) return true; return false; };
  function selVerts() {
    const out = new Set(st.vsel), n = new Map();
    for (const e of st.sel) for (const v of [E[e].a, E[e].b]) n.set(v, (n.get(v) || 0) + 1);
    for (const e of st.sel) {                             // the ends of each selected piece
      const list = PIECES[pieceOf[e]];
      const ends = new Map();
      list.forEach((k) => [E[k].a, E[k].b].forEach((v) => ends.set(v, (ends.get(v) || 0) + 1)));
      for (const [v, c] of ends) if (c === 1) out.add(v);
    }
    return out;
  }
  function pathVerts() {
    const out = new Map();                              // vertex -> edges of all layers there
    const all = new Set();
    for (const L of st.layers) for (const e of finalEdges(L)) all.add(e);
    for (const e of all) for (const v of [E[e].a, E[e].b]) (out.get(v) || out.set(v, []).get(v)).push(e);
    return out;
  }

  // -- the steps ------------------------------------------------------------
  const rowSel = (L) => L ? `[data-act=row][data-id="${L.id}"]` : null;
  // point at the layer (or the add menu if it is gone), then the edges, then the button
  const edgeStep = (L, list, btn) => !L ? ["[data-act=menu]"] : activeL() !== L ? [rowSel(L)]
    : hasAll(st.sel, list) ? [btn] : { edges: list.filter((e) => !st.sel.has(e)) };
  // hem edges outside the left scallop that were taken out by mistake
  const overRemoved = () => {
    const L = lineL();
    return L ? hem.filter((e) => !scallops[0].includes(e) && L.own.get(e) < 0) : [];
  };
  const fullScallop = () => scallops.find((list) => hasAll(st.sel, list));
  // a stitch layer along the hem, tips marked: the starting point of later demos
  const hemStitches = () => { const T = addLayer("stitch"); hem.forEach((e) => T.own.set(e, 1)); cusps.forEach((v) => st.corners.add(v)); return T; };
  const DEMOS = {
    // Start: one demo for the whole first mask, beside the four steps
    flow: { rows: ["add", "edges", "from", "length", "gap", "bake"], view: "40 128 440 346",
      steps: [
        { goal: () => !!stitchL(), hint: () => [st.menu ? "[data-act=add-stitch]" : "[data-act=menu]"],
          skip: () => { addLayer("stitch"); } },
        { goal: () => hem.every((e) => stitchL().own.get(e) > 0),
          hint: () => edgeStep(stitchL(), hem, "[data-act=e-add]"),
          skip: () => { const T = ensure("stitch"); hem.forEach((e) => T.own.set(e, 1)); st.active = T.id; st.sel = new Set(hem); } },
        { fresh: true, goal: () => Math.abs(stitchL().from - 6) <= 1, hint: () => ["[data-k=from]"],
          skip: () => { stitchL().from = 6; } },
        { goal: () => st.baked, hint: () => ["[data-act=bake]"], skip: () => bake() },
      ] },
    // Stitches: the two styles, and what Height and From Edge do to a zigzag
    style: { rows: ["style", "from", "width", "length", "gap", "height"], view: "40 250 440 230",
      preset: () => { hemStitches().marks = false; },
      steps: [
        { goal: () => stitchL().style === "zigzag", hint: () => ["[data-act=style-zigzag]"],
          skip: () => { stitchL().style = "zigzag"; } },
        { goal: () => Math.abs(stitchL().height - 6) <= 1, hint: () => ["[data-k=height]"], skip: () => { stitchL().height = 6; } },
        { goal: () => stitchL().from >= 4.5, hint: () => ["[data-k=from]"], skip: () => { stitchL().from = 5; } },
      ] },
    // Bake and use: every file a bake writes, named from the object, material and layer
    bakeall: { rows: ["names", "bake"], view: "40 128 440 346",
      preset: () => {
        hemStitches().marks = false;
        const L = addLayer("line", "trim"); L.marks = false; L.width = 1.5; L.color = "#8A3A2E"; hem.forEach((e) => L.own.set(e, 1));
        const G = addLayer("grid", "gingham"); G.marks = false; waist.forEach((e) => G.own.set(e, 1));
        st.active = stitchL().id;
      },
      steps: [
        { goal: () => st.baked, hint: () => ["[data-act=bake]"], skip: () => bake() },
        { goal: () => st.obj !== "Skirt" || st.mat !== "Cloth", hint: () => [".pr-names input"],
          skip: () => { st.obj = "Dress"; } },
      ] },
    // Presets: save the settings, apply them, make one the default
    presets: { rows: ["from", "width"], view: "40 250 440 230",
      preset: () => { hemStitches().marks = false; },
      steps: [
        { goal: () => st.presets.length > 0,
          hint: () => [st.pmenu ? (st.pname.trim() ? "[data-act=p-save]" : ".bp-text") : "[data-act=pmenu]"],
          skip: () => { savePreset(st.pname.trim() || S.presetName); } },
        { goal: () => st.applied,
          hint: () => { const p = st.presets[0], A = stitchL();
            return p && p.from === A.from && p.width === A.width ? ["[data-k=from]"]
              : [st.pmenu ? '[data-act=p-apply]' : "[data-act=pmenu]"]; },
          skip: () => { stitchL().from = 7; applyPreset(0); } },
        { goal: () => st.usedDefault,
          hint: () => [!st.pmenu ? "[data-act=pmenu]" : st.star === null ? "[data-act=p-star]" : "[data-act=p-default]"],
          skip: () => { st.star = 0; useDefault(); } },
      ] },
    // Layers: the list and what each part of a row does
    list: { rows: ["add"], view: "40 128 440 346",
      preset: () => {
        const T = hemStitches(); T.marks = false;
        const L = addLayer("line"); L.marks = false; L.width = 1.5; hips.forEach((e) => L.own.set(e, 1));
        st.active = T.id;                   // the first row, so the pins have room above it
      },
      steps: [
        { goal: () => !stitchL().visible, hint: () => [`[data-act=vis][data-id="${stitchL().id}"]`],
          skip: () => { stitchL().visible = false; } },
      ] },
    // Layers and edges: what the Edges row does
    edges: { rows: ["edges"], view: "40 250 440 230",
      preset: () => { addLayer("stitch"); },
      steps: [
        { goal: () => hem.every((e) => stitchL().own.get(e) > 0),
          hint: () => edgeStep(stitchL(), hem, "[data-act=e-add]"),
          skip: () => { hem.forEach((e) => stitchL().own.set(e, 1)); st.sel = new Set(hem); } },
        { fresh: true,
          goal: () => scallops.some((list) => list.every((e) => !stitchL().own.has(e)))
                      && hem.filter((e) => stitchL().own.get(e) > 0).length >= 8,
          hint: () => fullScallop() ? ["[data-act=e-remove]"] : { edges: hem },
          skip: () => { scallops[3].forEach((e) => stitchL().own.delete(e)); st.sel = new Set(scallops[3]); } },
      ] },
    // Reference: take another layer's edges, leave some out, then let go of them
    reference: { rows: ["edges"], view: "40 250 440 230",
      preset: () => { const T = addLayer("stitch"); hem.forEach((e) => T.own.set(e, 1)); addLayer("line"); },
      steps: [
        { goal: () => lineL().ref === stitchL().id,
          hint: () => activeL() !== lineL() ? [rowSel(lineL())] : st.pick ? [rowSel(stitchL())]
        : st.refmenu ? [`[data-act=ref-set][data-id="${stitchL().id}"]`] : ["[data-act=refmenu]"],
          skip: () => { lineL().ref = stitchL().id; st.active = lineL().id; } },
        { fresh: true,
          goal: () => scallops[0].every((e) => lineL().own.get(e) < 0) && !overRemoved().length,
          hint: () => overRemoved().length ? edgeStep(lineL(), overRemoved(), "[data-act=e-add]")
            : edgeStep(lineL(), scallops[0], "[data-act=e-remove]"),
          skip: () => { overRemoved().forEach((e) => lineL().own.delete(e));
                        scallops[0].forEach((e) => lineL().own.set(e, -1)); st.sel = new Set(scallops[0]); } },
        // the menu ticks the layer it follows; Clear Reference lets it go
        { goal: () => lineL().ref == null,
          hint: () => activeL() !== lineL() ? [rowSel(lineL())] : st.refmenu ? ["[data-act=ref-clear]"] : ["[data-act=refmenu]"],
          skip: () => { lineL().ref = null; st.active = lineL().id; } },
      ] },
    // Sharp Corners: mark the tips, then clear two of them
    corners: { rows: ["corners"], view: "40 250 440 230",
      preset: () => { const T = addLayer("stitch"); hem.forEach((e) => T.own.set(e, 1)); },
      steps: [
        { goal: () => cusps.every((v) => st.corners.has(v)),
          hint: () => ["[data-act=c-auto]"],
          skip: () => cusps.forEach((v) => st.corners.add(v)) },
        { fresh: true,
          goal: () => !st.corners.has(cusps[0]) && !st.corners.has(cusps[1]) && st.corners.has(cusps[2]),
          hint: () => hasAll(st.sel, scallops[1]) ? ["[data-act=c-remove]"] : { edges: scallops[1] },
          skip: () => { st.corners.delete(cusps[0]); st.corners.delete(cusps[1]); st.corners.add(cusps[2]); } },
      ] },
    // Flip Side: the selected layer (the hip line) changes side, the hem stitches stay
    flip: { rows: ["flip"], view: "40 128 440 346",
      preset: () => {
        const T = addLayer("stitch"); hem.forEach((e) => T.own.set(e, 1));
        cusps.forEach((v) => st.corners.add(v));
        const L = addLayer("line"); L.width = 1.5; hips.forEach((e) => L.own.set(e, 1));   // wide enough to see it move
      },
      steps: [
        { goal: () => lineL().flip, hint: () => ["[data-act=flip]"], skip: () => { lineL().flip = true; } },
      ] },
  };
  // Line art: From Edge and Width
  DEMOS.lineart = { rows: ["from", "width"], view: "40 250 440 230",
    preset: () => { const L = addLayer("line"); L.marks = false; hem.forEach((e) => L.own.set(e, 1)); cusps.forEach((v) => st.corners.add(v)); },
    steps: [
      { goal: () => Math.abs(lineL().from - 3) <= 1, hint: () => ["[data-k=from]"], skip: () => { lineL().from = 3; } },
      { goal: () => lineL().width >= 4, hint: () => ["[data-k=width]"], skip: () => { lineL().width = 5; } },
    ] };
  // Grid: checks laid from the marked waist
  DEMOS.grid = { rows: ["from", "along", "angle", "cell"], view: "40 128 440 346",
    preset: () => { const G = addLayer("grid"); waist.forEach((e) => G.own.set(e, 1)); },   // the green waist shows where the checks start
    steps: [
      { goal: () => Math.abs(gridL().angle - 45) <= 10, hint: () => ["[data-k=angle]"], skip: () => { gridL().angle = 45; } },
      { goal: () => gridL().along !== 0 || gridL().from !== 0, hint: () => ["[data-k=along]"], skip: () => { gridL().along = 3; } },
    ] };
  // the files a bake writes: <object>_<material>_<layer>.png, a grid twice
  const safe = (t) => t.replace(/[^\p{L}\p{N}\-_.]/gu, "_");
  function files() {
    const base = `${safe(st.obj)}_${safe(st.mat)}_`, out = [];
    for (const L of st.layers) {
      if (!L.visible || !finalEdges(L).size) continue;
      if (L.kind === "stitch") out.push({ id: "s" + L.id, name: base + L.file + ".png", L });
      else if (L.kind === "line") out.push({ id: "l" + L.id, name: base + safe(L.name) + ".png", L });
      else for (const part of ["black", "white"])
        out.push({ id: `g${L.id}${part}`, name: `${base}${safe(L.name)}_${part}.png`, L, part });
    }
    return out;
  }
  const bakeCount = () => st.layers.filter((L) => L.visible && finalEdges(L).size).length;
  function bake() { st.baked = true; const f = files(); st.view = f.length ? f[0].id : "model"; }
  // presets keep the settings this demo shows
  const PKEYS = ["from", "width"];
  function savePreset(name) {
    const A = stitchL(), p = { name };
    PKEYS.forEach((k) => { p[k] = A[k]; });
    const i = st.presets.findIndex((q) => q.name === name);
    if (i >= 0) st.presets[i] = p; else st.presets.push(p);
  }
  function applyPreset(i) {
    const A = stitchL(), p = st.presets[i];
    if (!p) return;
    if (PKEYS.some((k) => A[k] !== p[k])) st.applied = true;
    PKEYS.forEach((k) => { A[k] = p[k]; });
  }
  function useDefault() {
    const A = stitchL();
    if (st.star !== null && st.presets[st.star]) { PKEYS.forEach((k) => { A[k] = st.presets[st.star][k]; }); st.usedDefault = true; }
    else PKEYS.forEach((k) => { A[k] = DEFAULTS.stitch[k]; });
  }
  const CFG = DEMOS[S.demo];
  const STEPS = CFG.steps, ROWS = new Set(CFG.rows);
  function reset() { fresh(); if (CFG.preset) { CFG.preset(); st.sel = new Set(); } }

  // -- distance field and iso-lines ------------------------------------------
  const FX = 30, FY = 20, FC = 2, NX = 231, NY = 228;
  const fieldCache = new Map();
  function field(L) {
    const act = [...finalEdges(L)].sort((a, b) => a - b);
    if (!act.length) return null;
    const verts = new Set();
    act.forEach((k) => { verts.add(E[k].a); verts.add(E[k].b); });
    const key = act.join(",") + "|" + L.flip + "|" + [...st.corners].filter((v) => verts.has(v)).sort().join(",");
    if (fieldCache.has(key)) return fieldCache.get(key);
    const sgn = L.flip ? -1 : 1, at = new Map();
    const G = act.map((k, i) => {
      const e = E[k];
      for (const v of [e.a, e.b]) (at.get(v) || at.set(v, []).get(v)).push(i);
      return { a: e.a, b: e.b, ax: V[e.a][0], ay: V[e.a][1], bx: V[e.b][0], by: V[e.b][1],
               ux: e.ux, uy: e.uy, len: e.len,
               // a border has no cloth on its other side: its line stays on the cloth
               nx: e.border ? e.nx : e.nx * sgn, ny: e.border ? e.ny : e.ny * sgn };
    });
    G.forEach((g, i) => { g.oa = at.get(g.a).filter((j) => j !== i); g.ob = at.get(g.b).filter((j) => j !== i); });
    const val = new Float32Array(NX * NY), ok = new Uint8Array(NX * NY);
    for (let j = 0; j < NY; j++) {
      const py = FY + j * FC;
      for (let i = 0; i < NX; i++) {
        const px = FX + i * FC;
        let best = 1e9, good = 0;
        for (let m = 0; m < G.length; m++) {
          const g = G[m], dx = px - g.ax, dy = py - g.ay, t = dx * g.ux + dy * g.uy;
          let v, fine;
          if (t >= 0 && t <= g.len) {
            // signed, and usable a little past the edge: a line close to the
            // edge (line art at Offset Inward 0) crosses cells that reach past it
            const s = dx * g.nx + dy * g.ny;
            v = s; fine = s >= -2 * FC;
          } else {
            const atA = t < 0, end = atA ? g.a : g.b, others = atA ? g.oa : g.ob;
            const qx = px - (atA ? g.ax : g.bx), qy = py - (atA ? g.ay : g.by);
            v = Math.hypot(qx, qy);
            if (!others.length) fine = false;               // an open end: cut off square
            else {
              fine = qx * g.nx + qy * g.ny >= 0;
              for (const o of others) if (qx * G[o].nx + qy * G[o].ny >= 0) fine = true;
              if (others.length === 1 && st.corners.has(end)) {     // marked: mitre
                const p = G[others[0]], tp = (px - p.ax) * p.ux + (py - p.ay) * p.uy;
                if (end === p.a ? tp < 0 : tp > p.len)
                  v = Math.max(Math.abs(dx * g.nx + dy * g.ny), Math.abs((px - p.ax) * p.nx + (py - p.ay) * p.ny));
              }
            }
          }
          if (Math.abs(v) < Math.abs(best)) { best = v; good = fine ? 1 : 0; }
        }
        val[j * NX + i] = best; ok[j * NX + i] = good;
      }
    }
    const F = { val, ok };
    if (fieldCache.size > 40) fieldCache.clear();
    fieldCache.set(key, F);
    return F;
  }
  function isoLines(F, L) {
    const { val, ok } = F, pos = new Map(), adj = new Map();
    function pt(i, j, o) {
      const key = ((j * NX + i) << 1) | o;
      if (!pos.has(key)) {
        const a = val[j * NX + i] - L, b = (o ? val[(j + 1) * NX + i] : val[j * NX + i + 1]) - L;
        const t = a / (a - b);
        pos.set(key, [FX + (i + (o ? 0 : t)) * FC, FY + (j + (o ? t : 0)) * FC]);
      }
      return key;
    }
    function link(p, q) {
      (adj.get(p) || adj.set(p, []).get(p)).push(q);
      (adj.get(q) || adj.set(q, []).get(q)).push(p);
    }
    for (let j = 0; j < NY - 1; j++) for (let i = 0; i < NX - 1; i++) {
      const k = j * NX + i;
      if (!ok[k] || !ok[k + 1] || !ok[k + NX] || !ok[k + NX + 1]) continue;
      const a = val[k] < L, b = val[k + 1] < L, c = val[k + NX + 1] < L, d = val[k + NX] < L;
      if (a === b && b === c && c === d) continue;
      const T = a !== b ? pt(i, j, 0) : -1, R = b !== c ? pt(i + 1, j, 1) : -1;
      const B = d !== c ? pt(i, j + 1, 0) : -1, Lf = a !== d ? pt(i, j, 1) : -1;
      const xs = [T, R, B, Lf].filter((x) => x >= 0);
      if (xs.length === 2) link(xs[0], xs[1]);
      else {                                               // a saddle: look at the middle
        const mid = (val[k] + val[k + 1] + val[k + NX] + val[k + NX + 1]) / 4 < L;
        if (mid === a) { link(T, R); link(B, Lf); } else { link(T, Lf); link(R, B); }
      }
    }
    const seen = new Set(), out = [];
    function walk(s) {
      const chain = [s];
      seen.add(s);
      let cur = s;
      for (;;) {
        const nxt = (adj.get(cur) || []).find((q) => !seen.has(q));
        if (nxt === undefined) break;
        seen.add(nxt); chain.push(nxt); cur = nxt;
      }
      const closed = chain.length > 2 && (adj.get(cur) || []).includes(s);
      out.push({ pts: chain.map((q) => pos.get(q)), closed });
    }
    for (const [p, n] of adj) if (n.length === 1 && !seen.has(p)) walk(p);
    for (const p of adj.keys()) if (!seen.has(p)) walk(p);
    return out;
  }
  const pathD = (lines) => lines.filter((l) => l.pts.length > 1).map((l) =>
    l.pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join("") + (l.closed ? "Z" : "")).join("");

  // -- drawing --------------------------------------------------------------
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.append(e);
    return e;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const rich = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\{(\w+)\}/g, '<b class="pr-val" data-v="$1"></b>');
  // a value quoted in the coach follows the field while it is dragged
  function liveValues() {
    const A = activeL();
    coach.querySelectorAll(".pr-val").forEach((b) => {
      if (A && b.dataset.v in A) b.textContent = b.dataset.v === "angle" ? `${A.angle}°` : `${A[b.dataset.v]} mm`;
    });
  }

  fig.innerHTML = `<div class="pr-coach" aria-live="polite"></div>
    <div class="pr-body"><div class="pr-stage"><svg class="pr-view" viewBox="0 0 520 480"></svg><div class="pr-tabs"></div>
    <div class="pr-key"></div></div><div class="bp"></div></div>`;
  const coach = fig.querySelector(".pr-coach"), svg = fig.querySelector(".pr-view"), panel = fig.querySelector(".bp");
  const tabs = fig.querySelector(".pr-tabs");     // after a bake: the model or a baked file (not part of the add-on)
  const keyBox = fig.querySelector(".pr-key");     // what the coloured marks in the view are
  const stage = fig.querySelector(".pr-stage");
  if (CFG.rows.includes("names")) {               // object and material names: they name the files
    const bar = document.createElement("div");
    bar.className = "pr-names";
    bar.innerHTML = `<label><span>${esc(S.object)}</span><input data-n="obj" value="Skirt" spellcheck="false"></label>
      <label><span>${esc(S.material)}</span><input data-n="mat" value="Cloth" spellcheck="false"></label>`;
    fig.insertBefore(bar, fig.querySelector(".pr-body"));
    bar.addEventListener("input", (ev) => { st[ev.target.dataset.n] = ev.target.value; render(); });
  }
  const outlineD = outline.map((v, i) => `${i ? "L" : "M"}${V[v][0].toFixed(1)} ${V[v][1].toFixed(1)}`).join("") + "Z";
  const clipId = "pr-clip-" + inst;
  if (CFG.view) svg.setAttribute("viewBox", CFG.view);       // a small demo shows only the part it is about
  el("path", { d: outlineD }, el("clipPath", { id: clipId }, el("defs", {}, svg)));
  // a transparent PNG shown on a dark checkerboard
  el("rect", { width: 12, height: 12, fill: "#3A3A3A" }, el("pattern", { id: `pr-chk-${inst}`, width: 24, height: 24,
    patternUnits: "userSpaceOnUse" }, svg.querySelector("defs") || el("defs", {}, svg)));
  svg.querySelector(`#pr-chk-${inst}`).insertAdjacentHTML("afterbegin", '<rect width="24" height="24" fill="#2A2A2A"/>');
  svg.querySelector(`#pr-chk-${inst}`).insertAdjacentHTML("beforeend", '<rect x="12" y="12" width="12" height="12" fill="#3A3A3A"/>');
  const bg = el("rect", { x: -20, y: -20, width: 560, height: 520, fill: "none" }, svg);
  const shade = el("path", { d: outlineD, fill: "#22304A", opacity: 0.16, transform: "translate(0 10)" }, svg);
  const cloth = el("path", { d: outlineD, fill: FABRIC }, svg);
  const gPat = el("g", { "clip-path": `url(#${clipId})` }, svg);
  const gWire = el("g", {}, svg), gMarks = el("g", {}, svg), gHint = el("g", {}, svg);
  const gSel = el("g", {}, svg), gVerts = el("g", {}, svg), gHover = el("g", {}, svg);
  const segD = (k) => `M${V[E[k].a][0]} ${V[E[k].a][1]}L${V[E[k].b][0]} ${V[E[k].b][1]}`;
  E.forEach((e, k) => el("path", { d: segD(k), stroke: e.border ? "#9C8768" : "#DCCFBA",
    "stroke-width": e.border ? 1.8 : 1, fill: "none" }, gWire));
  let hintEdges = [], hover = null;            // hover: a piece index

  // checks laid from the layer's first marked edge: From Edge moves them off
  // the edge, Along Edge along it, Angle turns them (a flat piece, so no forks)
  function drawGrid(L, paint, part) {
    const fin = [...finalEdges(L)].sort((a, b) => a - b);
    if (!fin.length) return;
    const e = E[fin[0]], [ax, ay] = V[e.a], c = L.cell * MM;
    const ox = ax + e.nx * L.from * MM + e.ux * L.along * MM, oy = ay + e.ny * L.from * MM + e.uy * L.along * MM;
    const deg = Math.atan2(e.uy, e.ux) * 180 / Math.PI + L.angle, id = `pr-grid-${inst}-${L.id}`;
    const pat = el("pattern", { id, patternUnits: "userSpaceOnUse", width: 2 * c, height: 2 * c,
      patternTransform: `translate(${ox.toFixed(1)} ${oy.toFixed(1)}) rotate(${deg.toFixed(1)})` }, gPat);
    const cells = part === "white" ? [[c, 0], [0, c]] : [[0, 0], [c, c]];     // the other half of the checks
    cells.forEach(([x, y]) => el("rect", { x, y, width: c, height: c, fill: paint }, pat));
    el("rect", { x: 0, y: 0, width: 520, height: 480, fill: `url(#${id})` }, gPat);
  }
  // a zigzag across an iso-line: legs of half the length, swinging height/2 to each side
  function zigzag(pts, closed, len, h) {
    const P = closed ? pts.concat([pts[0]]) : pts, acc = [0];
    for (let i = 1; i < P.length; i++) acc.push(acc[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]));
    const total = acc[acc.length - 1], half = len / 2;
    if (total < half) return "";
    const n = Math.floor(total / half), out = [];
    let j = 1;
    for (let k = 0; k <= n; k++) {
      const d = k * half;
      while (j < P.length - 1 && acc[j] < d) j++;
      const a = P[j - 1], b = P[j], t = (d - acc[j - 1]) / Math.max(acc[j] - acc[j - 1], 1e-6);
      const tx = b[0] - a[0], ty = b[1] - a[1], l = Math.hypot(tx, ty) || 1, side = k % 2 ? -1 : 1;
      out.push([a[0] + tx * t - ty / l * h / 2 * side, a[1] + ty * t + tx / l * h / 2 * side]);
    }
    return out.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join("");
  }
  function drawLayer(L, paint, part) {
    const n = gPat.childElementCount;
    drawLayer2(L, paint, part);
    [...gPat.children].slice(n).forEach((x) => x.setAttribute("data-l", L.id));
  }
  function drawLayer2(L, paint, part) {
    if (L.kind === "grid") { drawGrid(L, paint, part); return; }
    const F = field(L);
    if (!F) return;
    const w = L.width * MM;
    const lines = isoLines(F, L.kind === "stitch" ? L.from * MM : L.from * MM + w / 2);
    if (L.kind === "stitch" && L.style === "zigzag") {
      const d = lines.filter((l) => l.pts.length > 1).map((l) => zigzag(l.pts, l.closed, L.length * MM, L.height * MM)).join("");
      if (d) el("path", { d, fill: "none", stroke: paint, "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" }, gPat);
      return;
    }
    const d = pathD(lines);
    if (!d) return;
    if (L.kind === "stitch")                // round caps add w to each stitch
      el("path", { d, fill: "none", stroke: paint, "stroke-width": w, "stroke-linecap": "round",
        "stroke-linejoin": "round", "stroke-dasharray": `${Math.max(L.length * MM - w, 0.1)} ${L.gap * MM + w}` }, gPat);
    else
      el("path", { d, fill: "none", stroke: paint, "stroke-width": w, "stroke-linejoin": "miter", "stroke-miterlimit": 8 }, gPat);
  }
  function drawView() {
    const file = st.view === "model" ? null : files().find((f) => f.id === st.view);
    if (!file && st.view !== "model") st.view = "model";
    const clear = file && st.bg === "clear", white = file && st.bg === "white";
    bg.setAttribute("fill", !file ? "none" : clear ? `url(#pr-chk-${inst})` : white ? "#fff" : "#000");
    cloth.setAttribute("fill", !file ? FABRIC : clear ? "none" : white ? "#fff" : "#000");
    for (const g of [shade, gWire, gMarks, gHint, gSel, gVerts, gHover]) g.style.display = file ? "none" : "";
    gPat.innerHTML = "";
    if (file) drawLayer(file.L, white ? "#000" : "#fff", file.part);
    else {
      // as in the add-on: a layer higher in the list is drawn over the ones below
      [...st.layers].reverse().forEach((L) => { if (L.visible) drawLayer(L, L.color); });
    }
    gMarks.innerHTML = "";
    const A = activeL();
    const showA = A && A.marks && st.allMarks;
    const mine = showA ? [...finalEdges(A)] : [], out = showA ? [...A.own].filter(([, v]) => v < 0) : [];
    mine.forEach((k) => el("path", { d: segD(k), class: "pr-mine" }, gMarks));
    out.forEach(([k]) => el("path", { d: segD(k), class: "pr-out" }, gMarks));
    gHint.innerHTML = "";
    for (const k of hintEdges) el("path", { d: segD(k), class: "pr-glow" }, gHint);
    gSel.innerHTML = "";
    for (const k of st.sel) el("path", { d: segD(k), class: "pr-sel-halo" }, gSel);
    for (const k of st.sel) el("path", { d: segD(k), class: "pr-sel" }, gSel);
    gVerts.innerHTML = "";
    const sv = selVerts();
    V.forEach((p, v) => el("circle", { cx: p[0], cy: p[1], r: sv.has(v) ? 3 : 1.8,
      fill: sv.has(v) ? PICK : "#A39478" }, gVerts));
    if (st.showCorners && st.allMarks) for (const v of st.corners) el("rect", { x: V[v][0] - 5, y: V[v][1] - 5, width: 10, height: 10,
      class: "pr-corner", fill: "#F2C230", stroke: "#3a2a05", "stroke-width": 1.5 }, gVerts);
    gHover.innerHTML = "";
    if (hover != null) for (const k of PIECES[hover]) el("path", { d: segD(k), class: "pr-hover" }, gHover);
    // the key: name each kind of mark that is on screen
    const drawn = file ? [] : st.layers.filter((L) => L.visible && finalEdges(L).size);
    const keys = file ? [] : drawn.map((L) => [`L${L.id}`, L.name, L.color, L.kind]).concat([
      mine.length && ["mine", S.keyEdges], out.length && ["out", S.keyOut],
      st.showCorners && st.allMarks && st.corners.size && ["corner", S.keyCorners], st.sel.size && ["sel", S.keySel]]).filter(Boolean);
    const sig = keys.map((k) => k[0]).join();
    if (keyBox.dataset.sig !== sig) {
      keyBox.dataset.sig = sig;
      keyBox.innerHTML = keys.map(([k, t, color, kind]) => color
        ? `<span data-key="${k}"><i class="k-layer k-${kind}" style="--c:${color}"></i>${esc(t)}</span>`
        : `<span data-key="${k}"><i class="k-${k}"></i>${esc(t)}</span>`).join("");
    }
  }

  // -- the panel ------------------------------------------------------------
  const I = {
    add: '<path d="M8 3v10M3 8h10"/>',
    remove: '<path d="M3 8h10"/>',
    select: '<path d="M4.5 2.5v10l2.6-2.4 1.8 4 1.6-.7-1.8-3.9 3.6-.3z" fill="currentColor" stroke="none"/>',
    clear: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    pick: '<path d="M10.5 2.8l2.7 2.7-1.6 1.6-2.7-2.7zM9.4 5.5l1.1 1.1-5.6 5.6-1.9.5.5-1.9z"/>',
    stitch: '<path d="M2 13l2-2M6 9l2-2M10 5l2-2"/>',
    line: '<path d="M2.5 13.5l11-11"/>',
    grid: '<path d="M2.5 2.5h11v11h-11zM2.5 8h11M8 2.5v11"/>',
    link: '<path d="M6 11H5.2a3 3 0 0 1 0-6H6M10 5h.8a3 3 0 0 1 0 6H10M5.6 8h4.8" stroke-width="1.8"/>',
    marks: '<g fill="currentColor" stroke="none"><rect x="7.4" y="1.2" width="4.6" height="7.6" rx="1.1" transform="rotate(45 9.7 5)"/><path d="M5.3 8.2l2.5 2.5-1.2 1-2.6.3.3-2.6z"/><rect x="2.4" y="13" width="5.2" height="1.8" rx=".9"/></g>',
    corner: '<path d="M2.8 11.4L8 6.2l5.2 5.2"/><circle cx="8" cy="6.2" r="1.9" fill="currentColor" stroke="none"/>',
    check: '<path d="M3.2 8.6l3 3 6.6-6.8"/>',
    down: '<path d="M4.5 6.5L8 10l3.5-3.5"/>',
    moveUp: '<path d="M8 4.8l4.2 6.2H3.8z" fill="currentColor" stroke="none"/>',
    moveDown: '<path d="M8 11.2L3.8 5h8.4z" fill="currentColor" stroke="none"/>',
    eye: '<path d="M1.5 8s2.4-4.3 6.5-4.3S14.5 8 14.5 8s-2.4 4.3-6.5 4.3S1.5 8 1.5 8z"/><circle cx="8" cy="8" r="1.8"/>',
    shut: '<path d="M1.5 7s2.4 3.3 6.5 3.3S14.5 7 14.5 7M4 9.8l-1 1.6M8 10.3v1.9M12 9.8l1 1.6"/>',
    skip: '<path d="M2.5 4l5 4-5 4zM8.5 4l5 4-5 4z"/>',
    play: '<path d="M5 3.5l7 4.5-7 4.5z"/>',
    refresh: '<path d="M12.5 8a4.5 4.5 0 1 1-1.3-3.2M12.5 2.5v3h-3"/>',
    preset: '<path d="M4.8 2.2h6.4a1 1 0 0 1 1 1v10.6L8 11.2l-4.2 2.6V3.2a1 1 0 0 1 1-1z" fill="currentColor" stroke="none"/>',
    star: '<path d="M8 2.2l1.8 3.7 4 .6-2.9 2.8.7 4L8 11.4l-3.6 1.9.7-4L2.2 6.5l4-.6z"/>',
    starOn: '<path d="M8 2.2l1.8 3.7 4 .6-2.9 2.8.7 4L8 11.4l-3.6 1.9.7-4L2.2 6.5l4-.6z" fill="currentColor"/>',
    vert: '<rect x="5" y="5" width="6" height="6" fill="currentColor" stroke="none"/><path d="M2 8h3M11 8h3M8 2v3M8 11v3"/>',
    file: '<path d="M4 1.8h5l3 3v9.4H4zM9 1.8v3h3"/>',
    restart: '<path d="M3.5 8a4.5 4.5 0 1 0 1.4-3.3M4.5 2v3h3"/>',
  };
  const icon = (n) => `<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${I[n]}</svg>`;
  const btn = (act, ic, label, extra = "") => `<button type="button" data-act="${act}" ${extra} aria-label="${esc(label)}" title="${esc(label)}">${ic}</button>`;

  const shown = (v, unit) => unit === "°" ? `${v}°` : `${v} ${unit}`;
  function num(k, L, lo, hi, step, unit = "mm") {
    const v = L[k], f = (v - lo) / (hi - lo) * 100;
    return `<div class="bp-num" data-k="${k}" data-lo="${lo}" data-hi="${hi}" data-step="${step}" data-unit="${unit}"
      role="slider" tabindex="0" aria-valuemin="${lo}" aria-valuemax="${hi}" aria-valuenow="${v}">
      <i style="width:${f}%"></i><span>${shown(v, unit)}</span></div>`;
  }
  function drawPanel() {
    const A = activeL(), at = st.layers.indexOf(A);
    const items = st.layers.map((L) => `<div class="bp-item${L.id === st.active ? " on" : ""}" data-act="row" data-id="${L.id}">
        ${icon(L.kind)}<span class="nm">${esc(L.name)}</span>${byId(L.ref) ? `<span class="lk">${icon("link")}</span>` : ""}<span class="sw" style="background:${L.color}"></span>
        ${btn("marks", icon("marks"), S.showEdges, `data-id="${L.id}" class="t${L.marks ? "" : " off"}"`)}
        ${btn("vis", icon(L.visible ? "eye" : "shut"), S.visible, `data-id="${L.id}" class="t${L.visible ? "" : " off"}"`)}
      </div>`).join("");
    const title = ROWS.has("add") ? `<div class="bp-title"><span>${esc(S.panelName)}</span><span class="tail">
        ${btn("allmarks", icon("marks"), S.allMarks, `class="tg${st.allMarks ? " on" : ""}"`)}
        ${st.layers.length ? (st.live ? "" : btn("rebuild", icon("refresh"), S.rebuild, 'class="tg"'))
          + btn("live", icon("play"), S.live, `class="tg${st.live ? " on" : ""}"`) : ""}</span></div>` : "";
    const pickNote = st.pick ? `<div class="bp-picknote">${icon("pick")}${esc(S.clickLayer)}</div>` : "";
    let h = `${title}<div class="bp-top"><div class="bp-list${st.pick ? " picking" : ""}">${items}${pickNote}</div>
      ${ROWS.has("add") ? `<div class="bp-side">${btn("menu", icon("add"), S.add, st.menu ? 'class="on"' : "")}
        ${btn("remove-layer", icon("remove"), S.remove, A ? "" : "disabled")}
        <i class="gap"></i>${btn("more", icon("down"), S.more, st.more ? 'class="on"' : "")}
        <i class="gap"></i><div class="bp-mv">${btn("move-up", icon("moveUp"), S.moveUp, at > 0 ? "" : "disabled")}
        ${btn("move-down", icon("moveDown"), S.moveDown, A && at < st.layers.length - 1 ? "" : "disabled")}</div>
        ${st.more ? `<div class="bp-menu more"><button type="button" data-act="clear-all"${st.layers.length ? "" : " disabled"}>${icon("clear")}${esc(S.clearAll)}</button></div>` : ""}
        ${st.menu ? `<div class="bp-menu">
          <button type="button" data-act="add-stitch">${icon("stitch")}${esc(S.stitches)}</button>
          <button type="button" data-act="add-line">${icon("line")}${esc(S.lineArt)}</button>
          <button type="button" data-act="add-grid">${icon("grid")}${esc(S.grid)}</button></div>` : ""}
      </div>` : ""}</div>`;
    const NUMS = new Set(["from", "along", "angle", "cell", "width", "length", "gap", "height"]);
    const LAYER_ROWS = ["edges", "corners", "flip", "from", "along", "angle", "cell", "style", "width", "length", "gap", "height"];
    if (A && LAYER_ROWS.some((k) => ROWS.has(k))) {
      // Reference: a link menu at the end of the Edges row, pressed while a
      // layer is followed; no rows come and go, so the rows below stay put
      const R0 = byId(A.ref);
      const refItems = st.layers.filter((L) => L !== A).map((L) =>
        `<button type="button" data-act="ref-set" data-id="${L.id}"${refersTo(L, A.id) ? " disabled" : ""}>${icon(L === R0 ? "check" : L.kind)}${esc(L.name)}</button>`).join("");
      const refMenu = st.refmenu ? `<div class="bp-menu ref">
          <button type="button" data-act="pick">${icon("pick")}${esc(S.pickInList)}</button><hr>${refItems}
          ${R0 ? `<hr><button type="button" data-act="ref-clear">${icon("clear")}${esc(S.clearRef)}</button>` : ""}</div>` : "";
      const refTitle = R0 ? S.refOf.replace("{}", R0.name) : S.reference;
      const zig = A.style === "zigzag";
      const R = {
        edges: `<div class="bp-row"><span class="lb">${esc(S.edges)}</span><div class="grp">
          ${btn("e-add", icon("add"), S.add)}${btn("e-remove", icon("remove"), S.remove)}
          ${btn("e-select", icon("select"), S.select)}${btn("e-clear", icon("clear"), S.clear)}</div>
          <div class="tail">${btn("refmenu", icon("link"), refTitle, `class="${R0 ? "tg on" : "t" + (st.refmenu ? " on" : "")}"`)}</div>${refMenu}</div>`,
        corners: `<div class="bp-row"><span class="lb">${esc(S.corners)}</span><div class="grp">
          ${btn("c-add", icon("add"), S.add)}${btn("c-remove", icon("remove"), S.remove)}
          ${btn("c-select", icon("select"), S.select)}<button type="button" data-act="c-auto" class="txt">${esc(S.auto)}</button></div>
          <div class="tail">${btn("c-marks", icon("corner"), S.showCorners, `class="t${st.showCorners ? "" : " off"}"`)}</div></div>`,
        flip: A.kind === "grid" ? "" : `<div class="bp-row"><span></span><label class="chk" data-act="flip"><input type="checkbox"${A.flip ? " checked" : ""}>${esc(S.flip)}</label></div>`,
        from: `<div class="bp-row"><span class="lb">${esc(S.fromEdge)}</span>${num("from", A, 0, 10, 0.5)}</div>`,
        along: `<div class="bp-row"><span class="lb">${esc(S.along)}</span>${num("along", A, -10, 10, 0.5)}</div>`,
        angle: `<div class="bp-row"><span class="lb">${esc(S.angle)}</span>${num("angle", A, -90, 90, 5, "°")}</div>`,
        cell: `<div class="bp-row"><span class="lb">${esc(S.cell)}</span>${num("cell", A, 3, 12, 0.5)}</div>`,
        style: A.kind !== "stitch" ? "" : `<div class="bp-row"><span class="lb">${esc(S.style)}</span><div class="seg">
          <button type="button" data-act="style-dash"${zig ? "" : ' class="on"'}>${esc(S.dashed)}</button><button type="button" data-act="style-zigzag"${zig ? ' class="on"' : ""}>${esc(S.zigzag)}</button></div></div>`,
        width: `<div class="bp-row"><span class="lb">${esc(S.width)}</span>${A.kind === "stitch" ? num("width", A, 0.5, 3, 0.1) : num("width", A, 0.5, 6, 0.5)}</div>`,
        length: `<div class="bp-row"><span class="lb">${esc(S.length)}</span>${num("length", A, 1, 10, 0.5)}</div>`,
        gap: zig ? "" : `<div class="bp-row"><span class="lb">${esc(S.gap)}</span>${num("gap", A, 1, 6, 0.5)}</div>`,
        height: !zig ? "" : `<div class="bp-row"><span class="lb">${esc(S.height)}</span>${num("height", A, 1, 8, 0.5)}</div>`,
      };
      const pm = st.pmenu ? `<div class="bp-menu pre">
          <button type="button" data-act="p-default">${esc(S.preDefault)}</button>
          ${st.presets.length ? "<hr>" + st.presets.map((p, i) => `<div class="pre-row">
            <button type="button" data-act="p-apply" data-id="${i}">${esc(p.name)}</button>
            ${btn("p-star", icon(st.star === i ? "starOn" : "star"), S.preStar, `data-id="${i}" class="t${st.star === i ? " on" : ""}"`)}
            ${btn("p-del", icon("remove"), S.remove, `data-id="${i}" class="t"`)}</div>`).join("") : ""}
          <hr><div class="pre-add"><input class="bp-text" value="${esc(st.pname)}" spellcheck="false" aria-label="${esc(S.preName)}">
          ${btn("p-save", icon("add"), S.add)}</div></div>` : "";
      // in the add-on's order, whichever rows this demo shows
      h += `<div class="bp-head">${icon(A.kind)}<span>${esc(A.name)}</span>
          ${btn("pmenu", icon("preset"), S.presets, `class="t${st.pmenu ? " on" : ""}"`)}${pm}</div>`
        + LAYER_ROWS.filter((k) => ROWS.has(k) && (!NUMS.has(k) || A[k] !== undefined)).map((k) => R[k]).join("");
    }
    if (ROWS.has("bake") && st.layers.length) {      // as in the add-on: nothing below the list until there is a layer
      const n = bakeCount();
      const BGS = [["black", S.black], ["white", S.white], ["clear", S.transparent]];
      h += `<div class="bp-head bake">${esc(S.bakeHead)}</div>
        <div class="bp-row"><span class="lb">${esc(S.background)}</span><div class="bp-dd">
          <button type="button" data-act="bgmenu"${st.bgmenu ? ' class="on"' : ""}>${esc(BGS.find(([v]) => v === st.bg)[1])}<i class="dd"></i></button>
          ${st.bgmenu ? `<div class="bp-menu bg">${BGS.map(([v, t]) =>
            `<button type="button" data-act="bg-${v}"${v === st.bg ? ' class="on"' : ""}>${esc(t)}</button>`).join("")}</div>` : ""}</div></div>
        <button type="button" class="bp-bake" data-act="bake"${n ? "" : " disabled"}>${esc((n === 1 ? S.bake1 : S.bakeN).replace("{}", n))}</button>`;
    }
    panel.innerHTML = h;
  }

  function drawCoach(advanced) {
    const n = STEPS.length, done = st.step >= n;
    // what the step just finished did, above what to do next
    const result = st.step > 0 ? `<p class="pr-result">${rich(S.results[st.step - 1])}</p>` : "";
    coach.innerHTML = `<span class="pr-count">${done ? "✓" : n > 1 ? `${st.step + 1}/${n}` : ""}</span>
      <div class="pr-msg">${result}${(done ? S.done : S.steps[st.step]) ? `<p class="pr-text">${rich(done ? S.done : S.steps[st.step])}</p>` : ""}</div>
      ${done ? "" : `<button type="button" data-coach="skip" aria-label="${esc(S.skip)}" title="${esc(S.skip)}">${icon("skip")}</button>`}
      <button type="button" data-coach="restart" aria-label="${esc(S.restart)}" title="${esc(S.restart)}">${icon("restart")}</button>`;
    liveValues();
    if (advanced) { coach.classList.remove("pr-advance"); void coach.offsetWidth; coach.classList.add("pr-advance"); }
  }

  function render() {
    const before = st.step;
    while (st.step < STEPS.length && STEPS[st.step].goal()) {
      st.step++;
      st.menu = st.refmenu = st.pmenu = false;
      if (STEPS[st.step] && STEPS[st.step].fresh) { st.sel = new Set(); st.vsel = new Set(); }
    }
    const focusK = document.activeElement && document.activeElement.closest && fig.contains(document.activeElement)
      && document.activeElement.closest(".bp-num") ? document.activeElement.dataset.k : null;
    drawPanel();
    if (focusK) { const b = panel.querySelector(`[data-k="${focusK}"]`); if (b) b.focus(); }
    const h = st.step < STEPS.length ? STEPS[st.step].hint() : [];
    hintEdges = Array.isArray(h) ? [] : h.edges;
    fig.querySelectorAll(".hint").forEach((x) => x.classList.remove("hint"));
    if (Array.isArray(h)) h.filter(Boolean).forEach((sel) => fig.querySelectorAll(sel).forEach((x) => x.classList.add("hint")));
    drawView();
    tabs.innerHTML = st.baked ? [`<button type="button" data-tab="model"${st.view === "model" ? ' class="on"' : ""}>${esc(S.model)}</button>`]
      .concat(files().map((f) => `<button type="button" data-tab="${f.id}"${st.view === f.id ? ' class="on"' : ""}>${icon("file")}<span>${esc(f.name)}</span></button>`)).join("") : "";
    relight();
    const flowBox = fig.closest(".flow");
    if (flowBox) flowBox.querySelectorAll("[data-step]").forEach((sec) => {
      sec.classList.toggle("now", +sec.dataset.step === st.step);
      sec.classList.toggle("done", +sec.dataset.step < st.step);
    });
    if (!STEPS.length) coach.hidden = true;
    else if (st.step !== before || !coach.firstChild) drawCoach(st.step !== before);
  }

  // -- legends: point at a line to spotlight its control, at a control to read its line
  const legends = [...document.querySelectorAll(`ol.um-keys[data-for="${fig.id}"]`)];
  const TARGET = {
    add: "[data-act=menu]", remove: "[data-act=remove-layer]", play: "[data-act=live]", refresh: "[data-act=rebuild]",
    name: ".bp-item.on .nm", color: ".bp-item.on .sw", marks: ".bp-item.on [data-act=marks]", eye: ".bp-item.on [data-act=vis]",
    "e-add": "[data-act=e-add]", "e-remove": "[data-act=e-remove]", "e-select": "[data-act=e-select]",
    "e-clear": "[data-act=e-clear]", link: "[data-act=refmenu]", allmarks: "[data-act=allmarks]", more: "[data-act=more]",
    move: ".bp-mv",
    "c-add": "[data-act=c-add]", "c-remove": "[data-act=c-remove]", "c-select": "[data-act=c-select]",
    "c-auto": "[data-act=c-auto]", "c-marks": "[data-act=c-marks]", style: ".seg", bake: "[data-act=bake]",
    background: "[data-act=bgmenu]", "p-button": "[data-act=pmenu]", "p-default": "[data-act=p-default]",
    "p-name": ".pre-add .bp-text", "p-save": "[data-act=p-save]", "p-star": "[data-act=p-star]", "p-del": "[data-act=p-del]",
    names: ".pr-names",
  };
  const IN_PMENU = new Set(["p-default", "p-name", "p-save", "p-star", "p-del"]);
  const items = legends.flatMap((ol) => [...ol.children]);
  const body = fig.querySelector(".pr-body");
  const veil = document.createElement("div"), tip = document.createElement("div");
  veil.className = "um-veil"; tip.className = "um-tip";
  veil.innerHTML = '<span class="um-hole"><b></b></span>';
  if (items.length) { body.append(veil, tip); fig.classList.add("keyed"); }
  let lit = null, locked = null, fromPanel = false;
  const targetOf = (li) => {
    const t = li.dataset.t;
    return (fig.querySelector(TARGET[t] || `[data-k="${t}"]`));
  };
  function light(li, panelSide) {
    lit = li; fromPanel = !!panelSide;
    items.forEach((x) => x.classList.toggle("lit", x === li));
    relight();
  }
  function relight() {
    if (!items.length) return;
    let x = lit && targetOf(lit);
    if (lit && !x && IN_PMENU.has(lit.dataset.t) && !st.pmenu) { st.pmenu = true; drawPanel(); x = targetOf(lit); }
    fig.classList.toggle("spot", !!x);
    fig.classList.toggle("from-panel", !!x && fromPanel);
    tip.classList.toggle("on", !!x && fromPanel);
    if (!x) return;
    const box = body.getBoundingClientRect(), r = x.getBoundingClientRect(), p = panel.getBoundingClientRect();
    const inPanel = panel.contains(x), area = inPanel ? p : stage.getBoundingClientRect();
    Object.assign(veil.style, { left: area.left - box.left + "px", top: area.top - box.top + "px",
      width: area.width + "px", height: area.height + "px" });
    const hole = veil.firstChild;
    Object.assign(hole.style, { left: r.left - area.left - 3 + "px", top: r.top - area.top - 3 + "px",
      width: r.width + 6 + "px", height: r.height + 6 + "px" });
    placeBadge(hole, r.left - area.left - 3, r.top - area.top - 3);
    hole.firstChild.textContent = lit.querySelector(".um-n").textContent;
    if (fromPanel) {
      tip.innerHTML = lit.querySelector(".um-d").innerHTML;
      // beside the panel, over the skirt, when they sit side by side; above the control otherwise
      const side = p.left - box.left > 200;
      const tw = side ? Math.min(240, p.left - box.left - 20) : Math.min(240, box.width - 16);
      tip.style.maxWidth = tw + "px";
      tip.classList.toggle("side", side);
      tip.style.left = (side ? p.left - box.left - 12 - tw : Math.max(8, Math.min(r.left - box.left + r.width / 2 - tw / 2, box.width - tw - 8))) + "px";
      tip.style.width = side ? tw + "px" : "";
      tip.style.top = (side ? stage.getBoundingClientRect().top - box.top + 10 : r.top - box.top - 8) + "px";
    }
  }
  if (items.length) {
    items.forEach((li) => {
      li.tabIndex = 0;
      li.addEventListener("mouseenter", () => { if (!locked) light(li); });
      li.addEventListener("focus", () => light(li));
      li.addEventListener("click", () => { locked = locked === li ? null : li; light(locked); });
    });
    legends.forEach((ol) => ol.addEventListener("mouseleave", () => { if (!locked) light(null); }));
    // the same names in the text around a legend point at their controls too
    const names = new Map(items.map((li) => [li.querySelector(".um-k").textContent.trim(), li]));
    const scopes = new Set(legends.map((ol) => ol.closest(".flow, section")).filter(Boolean));
    const hook = (strong) => {
      const li = names.get(strong.textContent.trim());
      if (!li || strong.closest("ol.um-keys")) return;
      strong.classList.add("um-ref");
      strong.addEventListener("mouseenter", () => { if (!locked) light(li); });
      strong.addEventListener("mouseleave", () => { if (!locked) light(null); });
    };
    scopes.forEach((sc) => sc.querySelectorAll("p strong, li strong").forEach(hook));
    new MutationObserver(() => coach.querySelectorAll("strong:not(.um-ref)").forEach(hook)).observe(coach, { childList: true, subtree: true });
    fig.addEventListener("mouseover", (ev) => {
      if (locked) return;
      const li = items.find((x) => { const t = targetOf(x); return t && t.contains(ev.target); });
      if (li) light(li, true);
      else if (lit && fromPanel) light(null);
    });
    fig.addEventListener("mouseleave", () => { if (!locked) light(null); });
    document.addEventListener("pointerdown", (ev) => {
      if (locked && !ev.target.closest("ol.um-keys")) { locked = null; light(null); }
    });
    addEventListener("resize", relight);
  }
  // the key under the view: point at a kind of mark to make it stand out
  // a layer: the others fade; a kind of mark: it pulses
  keyBox.addEventListener("mouseover", (ev) => {
    const k = ev.target.closest("[data-key]"), key = k ? k.dataset.key : "";
    svg.dataset.emph = key;
    gPat.querySelectorAll("[data-l]").forEach((x) => { x.style.opacity = key[0] === "L" && "L" + x.dataset.l !== key ? .15 : ""; });
  });
  keyBox.addEventListener("mouseleave", () => { svg.dataset.emph = ""; gPat.querySelectorAll("[data-l]").forEach((x) => { x.style.opacity = ""; }); });

  // -- panel actions --------------------------------------------------------
  function act(a, id) {
    const A = activeL();
    if (a !== "menu") st.menu = false;
    if (a !== "more") st.more = false;
    if (a !== "bgmenu") st.bgmenu = false;
    if (a !== "refmenu") st.refmenu = false;
    if (!a.startsWith("p")) st.pmenu = false;
    switch (a) {
      case "menu": st.menu = !st.menu; break;
      case "more": st.more = !st.more; break;
      case "clear-all": st.layers = []; st.active = null; st.corners = new Set(); break;
      case "allmarks": st.allMarks = !st.allMarks; break;
      case "add-stitch": addLayer("stitch"); break;
      case "add-line": addLayer("line"); break;
      case "add-grid": addLayer("grid"); break;
      case "remove-layer":
        if (A) {
          st.layers = st.layers.filter((L) => L !== A);
          st.layers.forEach((L) => { if (L.ref === A.id) L.ref = null; });
          st.active = st.layers.length ? st.layers[st.layers.length - 1].id : null;
        }
        break;
      case "move-up": case "move-down": {
        const i = st.layers.indexOf(A), j = i + (a === "move-up" ? -1 : 1);
        if (A && st.layers[j]) [st.layers[i], st.layers[j]] = [st.layers[j], A];
        break;
      }
      case "row": {
        const L = byId(id);
        if (st.pick && A && L && L !== A) {
          if (!refersTo(L, A.id)) A.ref = L.id;
          st.pick = false;
        } else st.active = id;
        break;
      }
      case "marks": byId(id).marks = !byId(id).marks; break;
      case "vis": byId(id).visible = !byId(id).visible; break;
      case "pick": st.pick = !st.pick; break;
      case "refmenu": st.refmenu = !st.refmenu; break;
      case "ref-set": { const L = byId(id); if (A && L && L !== A && !refersTo(L, A.id)) A.ref = L.id; break; }
      case "ref-clear": if (A) A.ref = null; break;
      case "flip": if (A) A.flip = !A.flip; break;
      case "bake": bake(); break;
      case "bgmenu": st.bgmenu = !st.bgmenu; break;
      case "bg-black": st.bg = "black"; break;
      case "bg-clear": st.bg = "clear"; break;
      case "bg-white": st.bg = "white"; break;
      case "c-marks": st.showCorners = !st.showCorners; break;
      case "pmenu": st.pmenu = !st.pmenu; break;
      case "p-save": if (st.pname.trim()) savePreset(st.pname.trim()); break;
      case "p-apply": applyPreset(id); break;
      case "p-star": st.star = st.star === id ? null : id; break;
      case "p-del":
        st.presets.splice(id, 1);
        if (st.star === id) st.star = null; else if (st.star > id) st.star--;
        break;
      case "p-default": useDefault(); break;
      case "live": st.live = !st.live; break;
      case "c-add": { const pv = pathVerts(); selVerts().forEach((v) => { if (pv.has(v)) st.corners.add(v); }); st.sel = new Set(); st.vsel = new Set(); break; }
      case "c-remove": selVerts().forEach((v) => st.corners.delete(v)); st.sel = new Set(); st.vsel = new Set(); break;
      case "c-select": st.sel = new Set(); st.vsel = new Set(st.corners); break;
      case "c-auto":
        for (const [v, es] of pathVerts()) {
          st.corners.delete(v);
          if (es.length !== 2) continue;
          const d = es.map((k) => { const o = E[k].a === v ? E[k].b : E[k].a; return [V[o][0] - V[v][0], V[o][1] - V[v][1]]; });
          const cos = (d[0][0] * d[1][0] + d[0][1] * d[1][1]) / Math.hypot(...d[0]) / Math.hypot(...d[1]);
          if (180 - Math.acos(Math.max(-1, Math.min(1, cos))) * 180 / Math.PI > 30) st.corners.add(v);
        }
        break;
    }
    if (A) switch (a) {
      case "e-add": st.sel.forEach((e) => A.own.set(e, 1)); st.sel = new Set(); st.allMarks = true; break;
      case "e-remove": {
        const fromRef = finalEdges(byId(A.ref));
        st.sel.forEach((e) => fromRef.has(e) ? A.own.set(e, -1) : A.own.delete(e));
        st.sel = new Set();
        break;
      }
      case "e-select": st.sel = finalEdges(A); st.vsel = new Set(); break;
      case "e-clear": A.own.clear(); break;
      case "style-dash": A.style = "dash"; break;
      case "style-zigzag": A.style = "zigzag"; break;
    }
    render();
  }
  panel.addEventListener("click", (ev) => {
    const t = ev.target.closest("[data-act]");
    if (!t || t.disabled || t.matches("input")) return;
    if (t.dataset.act === "flip") ev.preventDefault();      // the label would toggle the box itself
    act(t.dataset.act, t.dataset.id ? +t.dataset.id : undefined);
  });
  panel.addEventListener("input", (ev) => { if (ev.target.matches(".bp-text")) st.pname = ev.target.value; });
  panel.addEventListener("keydown", (ev) => {
    if (ev.target.matches(".bp-text") && ev.key === "Enter") { act("p-save"); panel.querySelector(".bp-text")?.focus(); }
  });
  // number fields: drag across, or arrow keys
  function setNum(box, v) {
    const A = activeL(), k = box.dataset.k, lo = +box.dataset.lo, hi = +box.dataset.hi, step = +box.dataset.step;
    v = Math.min(hi, Math.max(lo, Math.round(v / step) * step));
    v = +v.toFixed(2);
    if (!A || A[k] === v) return;
    A[k] = v;
    box.querySelector("i").style.width = (v - lo) / (hi - lo) * 100 + "%";
    box.querySelector("span").textContent = shown(v, box.dataset.unit);
    box.setAttribute("aria-valuenow", v);
    drawView();
    liveValues();
  }
  panel.addEventListener("pointerdown", (ev) => {
    const box = ev.target.closest(".bp-num"), A = activeL();
    if (!box || !A) return;
    const x0 = ev.clientX, v0 = A[box.dataset.k], step = +box.dataset.step;
    box.setPointerCapture(ev.pointerId);
    box.classList.add("drag");
    box.onpointermove = (e) => setNum(box, v0 + Math.round((e.clientX - x0) / 8) * step);    // one step per 8 px
    box.onpointerup = () => { box.onpointermove = box.onpointerup = null; box.classList.remove("drag"); render(); };
  });
  panel.addEventListener("keydown", (ev) => {
    const box = ev.target.closest(".bp-num"), A = activeL();
    if (!box || !A) return;
    const d = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[ev.key];
    if (d) { ev.preventDefault(); setNum(box, A[box.dataset.k] + d * +box.dataset.step); render(); }
  });
  tabs.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-tab]");
    if (b) { st.view = b.dataset.tab; render(); }
  });
  coach.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-coach]");
    if (!b) return;
    if (b.dataset.coach === "restart") { reset(); coach.innerHTML = ""; }
    else { STEPS[st.step].skip(); st.menu = false; st.refmenu = false; st.pick = false; }
    const names = fig.querySelector(".pr-names");
    if (names) names.querySelectorAll("input").forEach((x) => { x.value = st[x.dataset.n]; });
    render();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && (st.pick || st.menu || st.more || st.bgmenu || st.refmenu || st.pmenu)) { st.pick = st.menu = st.more = st.bgmenu = st.refmenu = st.pmenu = false; render(); }
  });
  document.addEventListener("pointerdown", (ev) => {
    if ((st.menu || st.more) && !ev.target.closest(".bp-side")) { st.menu = st.more = false; render(); }
    if (st.refmenu && !ev.target.closest(".bp-menu.ref, [data-act=refmenu]")) { st.refmenu = false; render(); }
    if (st.pmenu && !ev.target.closest(".bp-menu.pre, [data-act=pmenu], ol.um-keys")) { st.pmenu = false; render(); }
    if (st.bgmenu && !ev.target.closest(".bp-dd")) { st.bgmenu = false; render(); }
  });

  // -- the viewport: a click toggles a whole piece ---------------------------
  function toView(ev) {
    const p = svg.createSVGPoint();
    p.x = ev.clientX; p.y = ev.clientY;
    const m = svg.getScreenCTM();
    return { p: p.matrixTransform(m.inverse()), scale: m.a };
  }
  function hit(ev) {
    const { p, scale } = toView(ev);
    let best = null, bd = Math.max(12, 18 / scale);
    E.forEach((e, k) => {
      const [ax, ay] = V[e.a], t = Math.max(0, Math.min(e.len, (p.x - ax) * e.ux + (p.y - ay) * e.uy));
      const d = Math.hypot(ax + e.ux * t - p.x, ay + e.uy * t - p.y);
      if (d < bd) { bd = d; best = pieceOf[k]; }
    });
    return best;
  }
  svg.addEventListener("click", (ev) => {
    const i = hit(ev);
    st.pick = false;
    st.vsel = new Set();
    if (i == null) st.sel = new Set();
    else if (hasAll(st.sel, PIECES[i])) PIECES[i].forEach((e) => st.sel.delete(e));
    else PIECES[i].forEach((e) => st.sel.add(e));
    render();
  });
  svg.addEventListener("pointermove", (ev) => {
    if (ev.pointerType === "touch") return;
    const i = hit(ev);
    if (i !== hover) { hover = i; drawView(); }
  });
  svg.addEventListener("pointerleave", () => { if (hover != null) { hover = null; drawView(); } });

  reset();
  render();
  }
})();


// Replica settings panels and annotated screenshots: no sandbox, but the same
// pointing. A replica's Style and Layout switch like the add-on's (Style also
// swaps the rows it shows); a screenshot's legend spotlights its marked areas.
(() => {
  document.querySelectorAll(".refpanel").forEach((fig) => {
    const show = (v) => fig.querySelectorAll(".rp-row[data-show]").forEach((r) => { r.hidden = r.dataset.show !== v; });
    const style = fig.querySelector('.rp-row[data-r="style"] .rp-seg button.on');
    if (style) show(style.dataset.v);
    fig.addEventListener("click", (ev) => {
      const b = ev.target.closest(".rp-seg button");
      if (!b) return;
      b.parentNode.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      if (b.closest('.rp-row[data-r="style"]')) show(b.dataset.v);
    });
  });
  document.querySelectorAll("ol.um-keys").forEach((ol) => {
    const fig = document.getElementById(ol.dataset.for);
    if (!fig || fig.dataset.sandbox !== undefined) return;
    const box = fig.querySelector(".shot-box") || fig;
    const veil = document.createElement("div");
    veil.className = "um-veil";
    veil.innerHTML = '<span class="um-hole"><b></b></span>';
    box.append(veil);
    const items = [...ol.children];
    let locked = null;
    function light(li) {
      items.forEach((x) => x.classList.toggle("lit", x === li));
      const x = li && box.querySelector(`[data-hs="${li.dataset.t}"]`);
      fig.classList.toggle("spot", !!x);
      if (!x) return;
      const b = box.getBoundingClientRect(), r = x.getBoundingClientRect(), hole = veil.firstChild;
      Object.assign(veil.style, { left: 0, top: 0, width: b.width + "px", height: b.height + "px" });
      Object.assign(hole.style, { left: r.left - b.left + "px", top: r.top - b.top + "px", width: r.width + "px", height: r.height + "px" });
      placeBadge(hole, r.left - b.left, r.top - b.top);
      hole.firstChild.textContent = li.querySelector(".um-n").textContent;
    }
    items.forEach((li) => {
      li.tabIndex = 0;
      li.addEventListener("mouseenter", () => { if (!locked) light(li); });
      li.addEventListener("focus", () => light(li));
      li.addEventListener("click", () => { locked = locked === li ? null : li; light(locked); });
    });
    ol.addEventListener("mouseleave", () => { if (!locked) light(null); });
    box.addEventListener("mouseover", (ev) => {
      if (locked) return;
      const hs = ev.target.closest("[data-hs]");
      light(hs ? items.find((li) => li.dataset.t === hs.dataset.hs) : null);
    });
    box.addEventListener("mouseleave", () => { if (!locked) light(null); });
    document.addEventListener("pointerdown", (ev) => {
      if (locked && !ev.target.closest("ol.um-keys")) { locked = null; light(null); }
    });
  });
})();
