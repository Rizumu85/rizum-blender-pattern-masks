"""Crops of the stitch line drawn in true 3D shape (projected onto the local
tangent plane), around corners, line ends or given mm positions.

blender -b <file> -P tiles3d.py -- <object> <out.png> [corners|ends|<mm,mm,...>] [radius_mm] [max]

Blender has no PIL: the primitives are saved next to the PNG path (.npy) and
drawn by running this file with plain Python:  python tiles3d.py <out.png>
"""
import os
import sys

import numpy as np

try:
    import bpy
    import bmesh
except ImportError:
    bpy = None



def draw(out_png):
    from PIL import Image, ImageDraw
    tiles = np.load(out_png + ".npy", allow_pickle=True)
    S = 300
    ims = []
    for t in tiles:
        im = Image.new('RGB', (S, S), 'black')
        d = ImageDraw.Draw(im)
        for a, b in t["wire"]:
            d.line([a, b], fill=(55, 55, 55))
        for a, b in t["path"]:
            d.line([a, b], fill=(200, 60, 200), width=2)
        for x, y in t["marked"]:
            d.rectangle([x - 2, y - 2, x + 2, y + 2], outline=(200, 60, 200))
        for a, b in t["line"]:
            d.line([a, b], fill=(80, 220, 255), width=1)
        for x, y in t["corner"]:
            d.ellipse([x - 3, y - 3, x + 3, y + 3], outline=(255, 210, 0))
        d.text((4, 4), t["label"], fill='white')
        ims.append(im)
    cols = 4
    rows = max(1, (len(ims) + cols - 1) // cols)
    g = Image.new('RGB', (S * cols, S * rows))
    for i, t in enumerate(ims):
        g.paste(t, ((i % cols) * S, (i // cols) * S))
    g.save(out_png)


if bpy is None:
    draw(sys.argv[1])
else:
    args = sys.argv[sys.argv.index("--") + 1:]
    obj_name, out_png = args[0], args[1]
    mode = args[2] if len(args) > 2 else "corners"
    R = float(args[3]) / 1000 if len(args) > 3 else 0.008
    mx = int(args[4]) if len(args) > 4 else 12
    pkg = os.environ.get("STITCH_PKG", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, pkg)
    import rizum_pattern_masks as sg  # noqa: E402
    from rizum_pattern_masks import core  # noqa: E402

    sg.register()
    ob = bpy.data.objects[obj_name]
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    s = ob.stitch_gen
    s.live = False
    if ob.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if core.PATH_ATTR not in ob.data.attributes:
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(ob.data)
        for e in bm.edges:
            e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.stitch_gen.path_add()
        bpy.ops.object.mode_set(mode='OBJECT')
        s.inset, s.smooth, s.length, s.gap, s.width, s.corner_inset = 4.0, 2.0, 4.0, 2.5, 1.2, 1.0
    if os.environ.get("STITCH_SMOOTH"):
        s.smooth = float(os.environ["STITCH_SMOOTH"])
    core.drop_cache()
    sg.regenerate(ob)
    e = dict(core._cache[ob.name_full], cls=next(iter(core._cache[ob.name_full]["stitch"].values()))["cls"])
    topo = e["topo"]
    cls = e["cls"]

    centres = []
    if mode == "corners":
        for cl in cls:
            for c in cl.corners:
                q, _, _ = cl.sample(np.array([c]))
                centres.append(("corner", q[0]))
    elif mode == "ends":
        for i, cl in enumerate(cls):
            if not cl.closed:
                centres += [("line %d start" % i, cl.P[0]), ("line %d end" % i, cl.P[-1])]
            else:
                centres.append(("loop %d %dmm" % (i, round(cl.length * 1000)), cl.P[0]))
    else:
        acc = 0.0
        spots = [float(x) / 1000 for x in mode.split(",")]
        for cl in cls:
            for mm in spots:
                if acc <= mm < acc + cl.length:
                    q, _, _ = cl.sample(np.array([mm - acc]))
                    centres.append(("%d mm" % round(mm * 1000), q[0]))
            acc += cl.length

    pairs = core.read_path_edges(ob.data)
    mw = np.array(ob.matrix_world)
    vco = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    path = [(vco[a], vco[b]) for a, b in pairs.tolist()]
    wire = [(vco[ed.vertices[0]], vco[ed.vertices[1]]) for ed in ob.data.edges]
    marked = vco[core.read_corner_verts(ob.data)] if len(core.read_corner_verts(ob.data)) else np.zeros((0, 3))
    corner_pts = []
    for cl in cls:
        for c in cl.corners:
            corner_pts.append(cl.sample(np.array([c]))[0][0])

    line_pts = [cl.P if not cl.closed else np.vstack([cl.P, cl.P[:1]]) for cl in cls]
    if os.environ.get("STITCH_RAW"):
        from rizum_pattern_masks import contour
        pr = sg._params(s, bpy.context.scene)
        hh = max(abs(pr["inset"]) / 5.0, topo.mean_edge / 48.0, topo.span * 1e-5)
        raw, _ = contour.inset_lines(topo, e["chains"], pr["inset"], pr["flip"], e["corners"],
                                     max(pr.get("corner_inset", 0.0), 0.0), hh)
        line_pts = [P if not c else np.vstack([P, P[:1]]) for P, _, c in raw]
    S = 300
    tiles = []
    for label, c in centres[:mx]:
        dd = np.linalg.norm(topo.centroid - c, axis=1)
        n = topo.n_o[int(dd.argmin())]
        u = np.cross(n, [0, 0, 1.0])
        if np.linalg.norm(u) < 1e-3:
            u = np.cross(n, [1.0, 0, 0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)

        def f(p):
            x, y = np.dot(p - c, u), np.dot(p - c, v)
            return ((x + R) / (2 * R) * S, (R - y) / (2 * R) * S)

        def near(p):
            return np.linalg.norm(p - c) < 2.5 * R

        prim = {"label": "%s  (%.0f mm wide)" % (label, 2 * R * 1000), "wire": [], "path": [],
                "marked": [], "line": [], "corner": []}
        for a, b in wire:
            if near(a) or near(b):
                prim["wire"].append((f(a), f(b)))
        for a, b in path:
            if near(a) or near(b):
                prim["path"].append((f(a), f(b)))
        for q in marked:
            if near(q):
                prim["marked"].append(f(q))
        for P in line_pts:
            for p, q in zip(P[:-1], P[1:]):
                if near(p):
                    prim["line"].append((f(p), f(q)))
        for q in corner_pts:
            if near(q):
                prim["corner"].append(f(q))
        tiles.append(prim)
    np.save(out_png + ".npy", np.array(tiles, dtype=object), allow_pickle=True)
    print("TILES3D", len(tiles), [round(cl.length * 1000) for cl in cls])
