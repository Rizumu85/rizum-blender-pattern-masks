"""What an object's drawn preview shows (preview.geometry), for the tests:
the stitches, line art and grids, as positions and face counts."""
import numpy as np

from rizum_pattern_masks import preview


def _g(ob):
    return preview.geometry(ob) or {"stitches": [], "lines": [], "grids": []}


def stitch_co(ob, attr=None):
    """Corners of the stitches (of one layer, by its edge attribute)."""
    co = [r.co for a, r in _g(ob)["stitches"] if len(r.quads) and attr in (None, a)]
    return np.vstack(co) if co else np.zeros((0, 3))


def stitch_faces(ob):
    return sum(len(r.quads) for _a, r in _g(ob)["stitches"])


def stitch_layers(ob):
    """Edge attributes of the stitch layers the preview shows stitches of."""
    return [a for a, r in _g(ob)["stitches"] if len(r.quads)]


def line_co(ob, attr=None):
    """Corners of the line art (of one layer)."""
    co = [c[np.unique(t)] for a, c, t in _g(ob)["lines"] if attr in (None, a)]
    return np.vstack(co) if co else np.zeros((0, 3))


def line_faces(ob):
    """{edge attribute: quads} of the line art layers shown."""
    return {a: len(t) // 2 for a, _c, t in _g(ob)["lines"]}


def grid_faces(ob):
    return sum(len(co) // 3 for _a, _cell, co, _vs in _g(ob)["grids"])
