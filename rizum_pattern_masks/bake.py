"""Bake the stitch ribbons into the hem object's UV space and save 16-bit PNG masks."""

import os
import struct
import time
import zlib

import numpy as np
import bpy
import bmesh

from . import core, grid, lineart
from .i18n import rpt

TMP = "__stitchgen_bake"
FAINT = 0.05             # stitch coverage below this is bake noise, not stitch


def own_layer_mask(rib, tile, res, pad_px=1.5):
    """Texels near the stitch line where it really is in UV. Where two layers of
    the mesh almost touch, the bake rays also hit the stitches from the other
    layer and would print a second, offset line; this keeps only the first."""
    uv, r = rib.line_uv, rib.line_r_uv
    keep = np.zeros((res, res), np.float32)
    if not len(uv):
        return keep + 1.0
    xy = (uv - np.asarray(tile, np.float64)) * res - 0.5
    R = r * res + pad_px
    # fill in between samples (not across UV seams or between lines)
    gap = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    Rs = np.minimum(R[:-1], R[1:])
    n = np.where(gap < 6.0 * Rs, np.ceil(gap / (0.5 * Rs)).astype(np.int64), 1)
    if (n > 1).any():
        i = np.repeat(np.arange(len(gap)), n)
        f = (np.arange(len(i)) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
        xy = np.vstack([xy[i] + f[:, None] * (xy[i + 1] - xy[i]), xy[-1:]])
        R = np.concatenate([R[i] + f * (R[i + 1] - R[i]), R[-1:]])
    inside = (xy[:, 0] > -R - 1) & (xy[:, 0] < res + R) & (xy[:, 1] > -R - 1) & (xy[:, 1] < res + R)
    xy, R = xy[inside], R[inside]
    if not len(xy):
        return keep
    Rm = int(np.ceil(R.max()))
    oy, ox = np.mgrid[-Rm:Rm + 1, -Rm:Rm + 1]
    ox, oy = ox.ravel(), oy.ravel()
    step = 20000                      # samples per batch
    for a in range(0, len(xy), step):
        c, rr = xy[a:a + step], R[a:a + step]
        cx = np.rint(c[:, 0]).astype(np.int64)[:, None] + ox[None]
        cy = np.rint(c[:, 1]).astype(np.int64)[:, None] + oy[None]
        dd = (cx - c[:, 0:1]) ** 2 + (cy - c[:, 1:2]) ** 2
        ok = (dd <= rr[:, None] ** 2) & (cx >= 0) & (cx < res) & (cy >= 0) & (cy < res)
        keep[cy[ok], cx[ok]] = 1.0
    return keep


def write_png16(path, gray, transparent=False):
    """gray: (h, w) float array, row 0 = top. Written atomically, 16 bit.

    transparent=False: grayscale, white stitches on black (Painter masks).
    transparent=True: grayscale + alpha, white everywhere and the stitch
    coverage (soft edges included) as the alpha channel.
    """
    h, w = gray.shape
    a = np.clip(np.rint(gray * 65535.0), 0, 65535).astype(">u2")
    if transparent:
        ga = np.empty((h, w, 2), ">u2")
        ga[..., 0] = 65535
        ga[..., 1] = a
        a = ga
    ch = 2 if transparent else 1
    raw = np.zeros((h, 1 + 2 * ch * w), np.uint8)
    raw[:, 1:] = a.view(np.uint8).reshape(h, 2 * ch * w)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 4 if transparent else 0,
                                        0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6))
           + chunk(b"IEND", b""))
    _save(path, png)


def _save(path, data):
    """Write ``data`` to ``path``: to a temporary file, then swapped in, so a
    reader never sees half a file. A file another program has open can't be
    replaced: wait a moment (OneDrive syncing lets go quickly), then try to
    overwrite it in place, then give a clear message."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    err = None
    for i in range(8):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:
            err = e
            time.sleep(0.25)
    try:
        with open(path, "r+b") as f:        # some programs allow writing, not replacing
            f.write(data)
            f.truncate()
        os.remove(tmp)
        return
    except OSError:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise RuntimeError(rpt("{} is open in another program (for example Clip Studio Paint "
                           "or Painter) and can't be replaced. Close it there and bake "
                           "again").format(os.path.basename(path))) from err


def _uv_triangles(me, uv_name):
    """(T,3,2) UV corners and (T,) material index of every loop triangle."""
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tl = np.empty(nt * 3, np.int32)
    tm = np.empty(nt, np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    me.loop_triangles.foreach_get("material_index", tm)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers[uv_name].data.foreach_get("uv", uv)
    return uv.reshape(-1, 2).astype(np.float64)[tl.reshape(-1, 3)], tm


def _island_mask(tris, x0, y0, w, h):
    """Pixels (crop x0,y0,w,h) whose centre lies inside any UV triangle (pixel units)."""
    mask = np.zeros((h, w), bool)
    lo = np.floor(tris.min(1)).astype(int)
    hi = np.ceil(tris.max(1)).astype(int)
    sel = (hi[:, 0] >= x0) & (lo[:, 0] < x0 + w) & (hi[:, 1] >= y0) & (lo[:, 1] < y0 + h)
    for t, a, b in zip(tris[sel], lo[sel], hi[sel]):
        xa, xb = max(a[0], x0), min(b[0], x0 + w - 1)
        ya, yb = max(a[1], y0), min(b[1], y0 + h - 1)
        if xa > xb or ya > yb:
            continue
        X, Y = np.meshgrid(np.arange(xa, xb + 1), np.arange(ya, yb + 1))
        area = (t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[1, 1] - t[0, 1]) * (t[2, 0] - t[0, 0])
        if abs(area) < 1e-12:
            continue
        sgn = 1.0 if area > 0 else -1.0
        inside = np.ones(X.shape, bool)
        for k in range(3):
            A, B = t[k], t[(k + 1) % 3]
            e = (B[0] - A[0]) * (Y - A[1]) - (B[1] - A[1]) * (X - A[0])
            inside &= e * sgn >= -1e-9
        mask[ya - y0:yb - y0 + 1, xa - x0:xb - x0 + 1] |= inside
    return mask


def _bleed(img, known, iters):
    """Spread values from known pixels into unknown ones (UV margin), in place."""
    val = np.where(known, img, 0.0)
    known = known.copy()
    for _ in range(iters):
        vp = np.pad(val, 1)
        kp = np.pad(known.astype(np.float64), 1)
        s = np.zeros_like(val)
        c = np.zeros_like(val)
        h, w = val.shape
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                if dy == 1 and dx == 1:
                    continue
                s += vp[dy:dy + h, dx:dx + w]
                c += kp[dy:dy + h, dx:dx + w]
        new = ~known & (c > 0)
        if not new.any():
            break
        val[new] = s[new] / c[new]
        known |= new
    img[:] = val


def add_margin(gray, tris_uv, band_tris_uv, res, margin):
    """Blender-orientation image; bleed stitches past UV island borders only."""
    if margin <= 0 or not len(band_tris_uv):
        return gray
    px = tris_uv * res - 0.5
    bpx = band_tris_uv * res - 0.5
    x0 = max(0, int(np.floor(bpx[..., 0].min())) - margin - 2)
    y0 = max(0, int(np.floor(bpx[..., 1].min())) - margin - 2)
    x1 = min(res, int(np.ceil(bpx[..., 0].max())) + margin + 3)
    y1 = min(res, int(np.ceil(bpx[..., 1].max())) + margin + 3)
    crop = gray[y0:y1, x0:x1]
    known = _island_mask(px, x0, y0, x1 - x0, y1 - y0)
    _bleed(crop, known, margin)
    return gray


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def output_path(obj, mat_name, tile, folder, kind="stitch"):
    """<object>_<material>_<kind>.png, with a .<UDIM> suffix outside tile 1001."""
    name = f"{_safe(obj.name)}_{_safe(mat_name)}_{_safe(kind)}"
    udim = 1001 + int(tile[0]) + 10 * int(tile[1])
    if udim != 1001:
        name += f".{udim}"
    return os.path.join(folder, name + ".png")


class BakeSession:
    """One bake of all texture sets, split into steps so it can also run as a
    background job (Blender stays usable and shows a progress bar):

        session = BakeSession(context, obj, ribbon, rib, settings)
        session.begin()
        for i in range(len(session.groups)):
            kwargs = session.prepare(i)        # temp object, image, selection
            bpy.ops.object.bake(**kwargs)      # or 'INVOKE_DEFAULT' as a job
            session.finish()                   # margin + PNG, temp removed
        session.end()                          # scene restored
    """

    def __init__(self, context, obj, ribbon, rib, settings):
        if rib is None or rib.dash_count == 0:
            raise RuntimeError(rpt("No stitches to bake"))
        self.folder = bpy.path.abspath(settings.output_dir)
        if settings.output_dir.startswith("//") and not bpy.data.filepath:
            raise RuntimeError(rpt("Save the .blend file first, or pick an absolute output folder"))
        me = obj.data
        uvl = core.pick_uv(me, settings.uv_map)
        uv_name = uvl.name if uvl is not None else ""
        if not uv_name:
            raise RuntimeError(rpt("{} has no UV map").format(obj.name))
        self.context = context
        self.obj, self.ribbon, self.rib, self.settings = obj, ribbon, rib, settings
        self.uv_name = uv_name
        self.res = int(settings.resolution)
        self.margin = max(4, self.res // 256)
        self.extrusion = rib.lift * 2.5
        self.ray = rib.lift * 5.0
        self.written = []
        self._tmp = None
        self.groups = []
        self.state = None
        self.mode_before = 'OBJECT'

    # -- whole session ----------------------------------------------------------

    def begin(self):
        context, obj, s = self.context, self.obj, self.settings
        os.makedirs(self.folder, exist_ok=True)
        if context.mode != 'OBJECT':
            self.mode_before = context.active_object.mode if context.active_object else 'OBJECT'
            bpy.ops.object.mode_set(mode='OBJECT')
        me = obj.data
        # One image per Painter texture set (= material, by name, so two slots with
        # the same material share one image) and per UDIM tile.
        mi = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", mi)
        slot_names = [(sl.material.name if sl.material else f"slot{i}")
                      for i, sl in enumerate(obj.material_slots)] or ["slot0"]
        self.poly_mat = np.array([slot_names[min(m, len(slot_names) - 1)]
                                  for m in mi.tolist()], object)
        self.tri_uv, _ = _uv_triangles(me, self.uv_name)
        self.tri_poly = np.empty(len(me.loop_triangles), np.int32)
        me.loop_triangles.foreach_get("polygon_index", self.tri_poly)
        self.poly_tile = np.zeros((len(me.polygons), 2), np.int64)
        self.poly_tile[self.tri_poly] = np.floor(self.tri_uv.mean(axis=1)).astype(np.int64)
        self.tri_mat = self.poly_mat[self.tri_poly]
        self.tri_tile = self.poly_tile[self.tri_poly]
        self.band = self.rib.band_polys
        self.in_band = np.zeros(len(me.polygons), bool)
        self.in_band[self.band] = True
        self.groups = sorted({(self.poly_mat[p], int(self.poly_tile[p, 0]),
                               int(self.poly_tile[p, 1])) for p in self.band.tolist()})

        scene, vl, ribbon = context.scene, context.view_layer, self.ribbon
        self.state = {
            "engine": scene.render.engine,
            "samples": scene.cycles.samples,
            "device": scene.cycles.device,
            "threads_mode": scene.render.threads_mode,
            "threads": scene.render.threads,
            "active": vl.objects.active,
            "selected": [o for o in vl.objects if o.select_get()],
            "rib_hide_render": ribbon.hide_render,
            "rib_hide": ribbon.hide_get(),
            "rib_hide_vp": ribbon.hide_viewport,
        }
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = s.samples
        use_gpu = False
        if s.device == 'GPU':
            try:
                prefs = context.preferences.addons["cycles"].preferences
                use_gpu = prefs.compute_device_type not in ("", "NONE")
            except Exception:
                use_gpu = False
        scene.cycles.device = 'GPU' if use_gpu else 'CPU'
        # Leave cores for Blender itself so it stays responsive while baking.
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = max(1, round((os.cpu_count() or 4) * s.cpu_usage / 100.0))
        ribbon.hide_render = False
        ribbon.hide_viewport = False
        ribbon.hide_set(False)
        # the preview color lives in the emission shader: bake it white
        self._emit = []
        for mat in ribbon.data.materials:
            if mat is not None and mat.node_tree is not None:
                for n in mat.node_tree.nodes:
                    if n.type == 'EMISSION':
                        self._emit.append((n, tuple(n.inputs["Color"].default_value)))
                        n.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)

    def end(self):
        self._remove_tmp()
        st = self.state
        if st is None:
            return
        scene, vl = self.context.scene, self.context.view_layer
        scene.render.engine = st["engine"]
        scene.cycles.samples = st["samples"]
        scene.cycles.device = st["device"]
        scene.render.threads_mode = st["threads_mode"]
        scene.render.threads = st["threads"]
        for n, col in getattr(self, "_emit", ()):
            try:
                n.inputs["Color"].default_value = col
            except ReferenceError:
                pass
        self._emit = []
        self.ribbon.hide_render = st["rib_hide_render"]
        self.ribbon.hide_viewport = st["rib_hide_vp"]
        self.ribbon.hide_set(st["rib_hide"])
        for o in vl.objects:
            o.select_set(False)
        for o in st["selected"]:
            if o.name in vl.objects:
                o.select_set(True)
        vl.objects.active = st["active"]
        if self.mode_before != 'OBJECT' and st["active"] is not None:
            bpy.ops.object.mode_set(mode=self.mode_before)
        self.state = None

    # -- one texture set ------------------------------------------------------

    def prepare(self, i):
        """Temp copy of this group's faces with an image to bake into; returns
        the arguments for bpy.ops.object.bake."""
        # Blender's own margin treats texels whose ray missed the ribbon as empty
        # and smears stitches into them, so bake without margin and add it later.
        mat_name, tu, tv = self.groups[i]
        tile = np.array([tu, tv])
        sel = (self.poly_mat[self.band] == mat_name) & (self.poly_tile[self.band] == tile).all(1)
        polys = self.band[sel]
        scene, obj, uv_name, res = self.context.scene, self.obj, self.uv_name, self.res
        me = obj.data.copy()
        me.name = TMP
        # Bake in world units: cage extrusion and ray distance are measured in the
        # active object's own space, so an object scaled 0.01 (common for FBX)
        # would shrink them 100x and no ray would reach the stitches.
        mw = obj.matrix_world.copy()
        me.transform(mw)
        if mw.determinant() < 0:
            me.flip_normals()
        tmp = bpy.data.objects.new(TMP, me)
        scene.collection.objects.link(tmp)
        self._tmp = {"obj": tmp, "me": me, "mat": None, "img": None, "group": i, "tile": tile}
        bm = bmesh.new()
        bm.from_mesh(me)
        keep = set(int(p) for p in polys)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES')
        for f in bm.faces:
            f.smooth = False     # rays along each face normal, like the stitch lift
        bm.to_mesh(me)
        bm.free()
        for uvl in list(me.uv_layers):
            if uvl.name != uv_name:
                me.uv_layers.remove(uvl)
        uvl = me.uv_layers[uv_name]
        me.uv_layers.active = uvl
        uvl.active_render = True
        if np.any(tile):                      # shift this UDIM tile back to 0-1
            uv = np.empty(len(me.loops) * 2, np.float32)
            uvl.data.foreach_get("uv", uv)
            uv = uv.reshape(-1, 2) - np.asarray(tile, np.float32)
            uvl.data.foreach_set("uv", uv.ravel())
        me.materials.clear()
        mat = bpy.data.materials.new(TMP)
        self._tmp["mat"] = mat
        if hasattr(mat, "use_nodes") and not mat.use_nodes:
            mat.use_nodes = True
        img = bpy.data.images.new(TMP, res, res, alpha=False, float_buffer=True)
        self._tmp["img"] = img
        img.colorspace_settings.name = "Non-Color"
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        mat.node_tree.nodes.active = node
        me.materials.append(mat)
        me.polygons.foreach_set("material_index", np.zeros(len(me.polygons), np.int32))
        me.update()
        vl = self.context.view_layer
        for o in vl.objects:
            o.select_set(False)
        self.ribbon.select_set(True)
        tmp.select_set(True)
        vl.objects.active = tmp
        return dict(type='EMIT', use_selected_to_active=True, use_cage=False,
                    cage_extrusion=self.extrusion, max_ray_distance=self.ray,
                    margin=0, use_clear=True, target='IMAGE_TEXTURES', uv_layer=uv_name)

    def finish(self):
        """Read the baked image, add the UV margin, write the PNG."""
        t = self._tmp
        res = self.res
        px = np.empty(res * res * 4, np.float32)
        t["img"].pixels.foreach_get(px)
        gray = px.reshape(res, res, 4)[:, :, 0].copy()
        mat_name = self.groups[t["group"]][0]
        tile = t["tile"]
        self._remove_tmp()
        of_group = (self.tri_mat == mat_name) & (self.tri_tile == tile).all(1)
        gray *= own_layer_mask(self.rib, tile, res)
        # Where the fabric folds sharply, bake rays graze the stitch strips and
        # smear their soft edge into faint lines (a few percent grey). Coverage
        # this low is not visible on a real edge either: drop it.
        gray[gray < FAINT] = 0.0
        add_margin(gray, self.tri_uv[of_group] - tile,
                   self.tri_uv[of_group & self.in_band[self.tri_poly]] - tile, res, self.margin)
        path = output_path(self.obj, mat_name, tile, self.folder)
        if path in self.written:     # e.g. "Red/Blue" and "Red_Blue"
            path = path[:-4] + f"_{zlib.crc32(mat_name.encode()) % 10000:04d}.png"
        write_png16(path, gray[::-1], transparent=self.settings.transparent)
        self.written.append(path)
        return path

    def _remove_tmp(self):
        t, self._tmp = self._tmp, None
        if not t:
            return
        for coll, key in ((bpy.data.objects, "obj"), (bpy.data.meshes, "me"),
                          (bpy.data.materials, "mat"), (bpy.data.images, "img")):
            idb = t.get(key)
            if idb is not None:
                try:
                    coll.remove(idb)
                except ReferenceError:
                    pass


def output_folder(settings):
    folder = bpy.path.abspath(settings.output_dir)
    if settings.output_dir.startswith("//") and not bpy.data.filepath:
        raise RuntimeError(rpt("Save the .blend file first, or pick an absolute output folder"))
    return folder


class LineBake:
    """Line art masks: computed per texel from the distance to the edges, one
    PNG per line layer and texture set (material and UDIM tile)."""

    def __init__(self, obj, entry, settings, layers):
        """layers: [(name, offset, width, corner_depth, edge sets followed, smooth,
        edge attribute)] in scene units."""
        self.folder = output_folder(settings)
        self.obj, self.settings = obj, settings
        self.res = int(settings.resolution)
        # Lines often run right along the open edge of the mesh, so a wide bleed
        # would show as a thick halo in a 2D app; a little is enough at UV seams.
        self.margin = 2
        self.topo = topo = entry["topo"]
        if topo.uv is None:
            raise RuntimeError(rpt("{} has no UV map").format(obj.name))
        self.names = _unique_names([l[0] for l in layers])
        # one distance field per set of edges followed
        self.parts = []                      # (layer indices, field, faces)
        faces = []
        for attrs in sorted({tuple(l[4]) for l in layers}):
            idx = [i for i, l in enumerate(layers) if tuple(l[4]) == attrs]
            chains = core.line_chains(entry, attrs)
            if not idx or not chains:
                continue
            sub = [(layers[i][1], layers[i][2], layers[i][3], layers[i][5]) for i in idx]
            field, f = lineart.field_for(topo, chains, entry["corners"], settings.flip, sub)
            if field is not None:
                inner = [lineart.inner_curves(topo, chains, entry["corners"], settings.flip,
                                              *l) if l[3] > 0 else None for l in sub]
                self.parts.append((idx, sub, field, f, inner))
                faces.append(f)
        self.n_layers = len(layers)
        self.faces = np.unique(np.concatenate(faces)) if faces else np.zeros(0, np.int64)
        me = obj.data
        mi = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", mi)
        slot_names = [(sl.material.name if sl.material else f"slot{i}")
                      for i, sl in enumerate(obj.material_slots)] or ["slot0"]
        poly_mat = np.array([slot_names[min(m, len(slot_names) - 1)] for m in mi.tolist()],
                            object)
        self.tri_mat = poly_mat[topo.tri_poly]
        self.tri_tile = np.floor(topo.uv.mean(axis=1)).astype(np.int64)
        self.groups = sorted({(self.tri_mat[t], int(self.tri_tile[t, 0]), int(self.tri_tile[t, 1]))
                              for t in self.faces.tolist()})
        self.written = []

    def step(self, i, taken=()):
        """Bake texture set i for every layer; returns the written paths."""
        mat, tu, tv = self.groups[i]
        tile = np.array([tu, tv])
        of_group = (self.tri_mat == mat) & (self.tri_tile == tile).all(1)
        imgs = [None] * self.n_layers
        for idx, sub, field, f, inner in self.parts:
            for i, img in zip(idx, lineart.raster(self.topo, field, f[of_group[f]], self.res,
                                                  tile, sub, inner)):
                imgs[i] = img
        faces = self.faces[of_group[self.faces]]
        out = []
        for name, gray in zip(self.names, imgs):
            if gray is None:                 # this layer has no edges to follow
                continue
            add_margin(gray, self.topo.uv[of_group] - tile, self.topo.uv[faces] - tile,
                       self.res, self.margin)
            path = output_path(self.obj, mat, tile, self.folder, name)
            used = {p.casefold() for p in list(self.written) + list(taken)}
            k = 2
            base = path[:-4]
            while path.casefold() in used:      # e.g. materials "Red/Blue" and "Red_Blue"
                path = f"{base}_{k}.png"
                k += 1
            os.makedirs(self.folder, exist_ok=True)
            write_png16(path, gray[::-1], transparent=self.settings.transparent)
            self.written.append(path)
            out.append(path)
        return out


class GridBake:
    """Checkerboard masks: computed per texel from the fabric coordinates, two
    PNGs per grid layer and texture set: the black and the white squares."""

    PARTS = ("black", "white")

    def __init__(self, obj, entry, settings, layers):
        """layers: [(name, edge attribute, cell, angle, from edge, along edge,
        wobble, layout, edge sets followed)] in scene units (angle in radians)."""
        self.folder = output_folder(settings)
        self.obj, self.settings = obj, settings
        self.res = int(settings.resolution)
        self.margin = 2
        self.topo = topo = entry["topo"]
        if topo.uv is None:
            raise RuntimeError(rpt("{} has no UV map").format(obj.name))
        self.names = _unique_names([l[0] for l in layers])
        self.layers = [(l, core.grid_coords(entry, l[8]).layout(l[2], l[3], l[7]))
                       for l in layers]
        faces = [c.faces for _, c in self.layers if len(c.faces)]
        self.faces = np.unique(np.concatenate(faces)) if faces else np.zeros(0, np.int64)
        me = obj.data
        mi = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", mi)
        slot_names = [(sl.material.name if sl.material else f"slot{i}")
                      for i, sl in enumerate(obj.material_slots)] or ["slot0"]
        poly_mat = np.array([slot_names[min(m, len(slot_names) - 1)] for m in mi.tolist()],
                            object)
        self.tri_mat = poly_mat[topo.tri_poly]
        self.tri_tile = np.floor(topo.uv.mean(axis=1)).astype(np.int64)
        self.groups = sorted({(self.tri_mat[t], int(self.tri_tile[t, 0]), int(self.tri_tile[t, 1]))
                              for t in self.faces.tolist()})
        self.written = []

    def step(self, i, taken=()):
        """Bake texture set i for every grid layer; returns the written paths."""
        mat, tu, tv = self.groups[i]
        tile = np.array([tu, tv])
        of_group = (self.tri_mat == mat) & (self.tri_tile == tile).all(1)
        out = []
        for name, ((_, attr, cell, _angle, off_y, off_x, wobble, _mode, _attrs), lay) in zip(
                self.names, self.layers):
            f = lay.faces[of_group[lay.faces]]
            if not len(f):
                continue
            black, white = grid.raster(self.topo, lay, f, self.res, tile, cell, off_x, off_y,
                                       grid.Wobble(attr, cell, wobble))
            for part, gray in zip(self.PARTS, (black, white)):
                add_margin(gray, self.topo.uv[of_group] - tile, self.topo.uv[f] - tile,
                           self.res, self.margin)
                path = output_path(self.obj, mat, tile, self.folder, f"{name}_{part}")
                used = {p.casefold() for p in list(self.written) + list(taken) + out}
                k = 2
                base = path[:-4]
                while path.casefold() in used:
                    path = f"{base}_{k}.png"
                    k += 1
                os.makedirs(self.folder, exist_ok=True)
                write_png16(path, gray[::-1], transparent=self.settings.transparent)
                self.written.append(path)
                out.append(path)
        return out


class Chain:
    """Several per-texel bakes run one after another, as one."""

    def __init__(self, bakes):
        self.bakes = bakes
        self.groups = [(b, i) for b in bakes for i in range(len(b.groups))]

    def step(self, i, taken=()):
        b, j = self.groups[i]
        return b.step(j, taken)


def _unique_names(names):
    """File-name parts for the layers, distinct after cleaning and ignoring case
    (Windows file names), e.g. "a/b", "a_b" and "A b" become a_b, a_b_2, A_b_3."""
    out, used = [], set()
    for n in names:
        base = _safe((n or "line").strip() or "line")
        name, k = base, 2
        while name.casefold() in used:
            name = f"{base}_{k}"
            k += 1
        used.add(name.casefold())
        out.append(name)
    return out


def bake_masks(context, obj, ribbon, rib, settings):
    """Bake everything now (blocking). Returns the written file paths."""
    session = BakeSession(context, obj, ribbon, rib, settings)
    session.begin()
    try:
        for i in range(len(session.groups)):
            kwargs = session.prepare(i)
            bpy.ops.object.bake(**kwargs)
            session.finish()
    finally:
        session.end()
    return session.written
