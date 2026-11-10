"""Draw the add-on's own icons into rizum_pattern_masks/icons.npz.

    python tools/make_icons.py

In the style of Lucide (lucide.dev, ISC License): a 24 unit grid, round ends
and joins; the marks, preset and folder icons are filled, the others are
lines. Blender's own icons stay for the common buttons (+, -, select, eye);
these are only for the add-on's own buttons.

Each icon is drawn at every whole size Blender may show it at (16 px times
the UI scale, which includes the system's display scaling), so it is never
scaled on screen: a scaled icon looks soft. They are stored together as 8-bit
coverage masks ("<name>_<px>", row 0 at the top) in one compressed numpy file;
a preview sheet of a few sizes goes to tools/icons_preview.png. Straight
lines sit on whole pixels and line widths are whole pixels. The icons are
white shapes: the add-on paints them in the theme's text colour when it draws
them, as Blender does with its own icons.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "rizum_pattern_masks", "icons.npz")
SIZES = range(12, 65)
SS = 8                       # supersampling
INK = (255, 255, 255, 255)


def arc(cx, cy, rad, a0, a1, n=12):
    return [(cx + rad * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + rad * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rrect(x0, y0, x1, y1, r):
    return (arc(x1 - r, y0 + r, r, -90, 0, 6) + arc(x1 - r, y1 - r, r, 0, 90, 6)
            + arc(x0 + r, y1 - r, r, 90, 180, 6) + arc(x0 + r, y0 + r, r, 180, 270, 6))


def turned(pts, ang, cx, cy):
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts]


def _on_grid(v):
    return abs(v * 2 - round(v * 2)) < 1e-9          # whole or half grid units


class Canvas:
    """Draws grid-unit shapes at n px (supersampled)."""

    def __init__(self, n):
        self.n = n
        self.k = n / 24.0                             # px per grid unit
        self.im = Image.new("RGBA", (n * SS, n * SS), (0, 0, 0, 0))
        self.dr = ImageDraw.Draw(self.im)

    def width(self, w):
        return max(1, round(w * self.k))             # whole pixels

    def _pt(self, x, y, off):
        """Grid point to supersampled px; points of straight lines (on whole
        or half grid units) land on whole pixels (off 0.5: pixel centres)."""
        px, py = x * self.k, y * self.k
        if _on_grid(x) and _on_grid(y):
            px, py = round(px - off) + off, round(py - off) + off
        return px * SS, py * SS

    def stroke(self, pts, w=2.0):
        wpx = self.width(w)
        off = 0.5 if wpx % 2 else 0.0
        P = [self._pt(x, y, off) for x, y in pts]
        r = wpx * SS / 2
        for a, b in zip(P[:-1], P[1:]):
            self.dr.line([a, b], fill=INK, width=wpx * SS)
        for x, y in P:
            self.dr.ellipse([x - r, y - r, x + r, y + r], fill=INK)

    def loop(self, pts, w=2.0):
        self.stroke(pts + [pts[0]], w)

    def fill(self, pts):
        self.dr.polygon([self._pt(x, y, 0.0) for x, y in pts], fill=INK)

    def dot(self, x, y, rad):
        cx, cy = x * self.k * SS, y * self.k * SS
        r = rad * self.k * SS
        self.dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK)

    def image(self):
        return self.im.resize((self.n, self.n), Image.LANCZOS)


def marks(c):
    """Filled: a highlighter (body, slanted tip) and the stroke it leaves."""
    # centred on its weight: the body is most of it, so it sits a little low
    c.fill(turned(rrect(-3.4, -8.6, 3.4, 1.0, 1.5), 45, 13.2, 11.6))
    c.fill(turned([(-2.8, 2.4), (2.8, 2.4), (1.6, 6.2), (-0.9, 7.1)], 45, 13.2, 11.6))
    c.stroke([(4, 20.5), (11, 20.5)], w=2.6)


def preset(c):
    """Filled: a bookmark."""
    c.fill([(19, 21), (12, 17), (5, 21), (5, 5)] + arc(7, 5, 2, 180, 270, 6)[1:-1]
           + [(7, 3), (17, 3)] + arc(17, 5, 2, 270, 360, 6)[1:-1] + [(19, 5)])


def folder(c):
    """Filled: a folder with its tab."""
    c.fill([(20, 20)] + arc(20, 18, 2, 90, 0, 6)[1:-1] + [(22, 18), (22, 8)]
           + arc(20, 8, 2, 0, -90, 6)[1:-1] + [(20, 6)]
           + [(12.1, 6), (11.0, 5.7), (10.4, 5.1), (9.6, 3.9), (9.0, 3.3), (7.9, 3)]
           + [(4, 3)] + arc(4, 5, 2, -90, -180, 6)[1:-1] + [(2, 5), (2, 18)]
           + arc(4, 18, 2, 180, 90, 6)[1:-1] + [(4, 20)])


def corners(c):
    """Two edges meeting square at a vertex."""
    c.stroke([(4, 17), (12, 9), (20, 17)])
    c.dot(12, 9, 3.0)


def link(c):
    """Two open links and a bar, drawn a little bolder than the other lines."""
    c.stroke([(9, 17), (7, 17)] + arc(7, 12, 5, 90, 270)[1:-1] + [(7, 7), (9, 7)], w=2.6)
    c.stroke([(15, 7), (17, 7)] + arc(17, 12, 5, -90, 90)[1:-1] + [(17, 17), (15, 17)], w=2.6)
    c.stroke([(8, 12), (16, 12)], w=2.6)


def reveal(c):
    c.stroke([(15, 3), (21, 3), (21, 9)])
    c.stroke([(10, 14), (21, 3)])
    c.stroke([(18, 13), (18, 19)] + arc(16, 19, 2, 0, 90)[1:-1] + [(16, 21), (5, 21)]
             + arc(5, 19, 2, 90, 180)[1:-1] + [(3, 19), (3, 8)] + arc(5, 8, 2, 180, 270)[1:-1]
             + [(5, 6), (11, 6)])


ICONS = {"marks": marks, "preset": preset, "folder": folder, "corners": corners,
         "link": link, "reveal": reveal}


def main():
    masks = {}
    for name, fn in sorted(ICONS.items()):
        for n in SIZES:
            c = Canvas(n)
            fn(c)
            masks[f"{name}_{n}"] = np.asarray(c.image())[..., 3].copy()
    np.savez_compressed(OUT, **masks)
    print("wrote", OUT, os.path.getsize(OUT), "bytes,", len(masks), "masks")
    # preview: 16, 18, 20, 24 px on Blender's panel grey
    shown = (16, 18, 20, 24)
    sheet = Image.new("RGB", (len(ICONS) * 40, len(shown) * 40), (61, 61, 61))
    for j, n in enumerate(shown):
        for i, name in enumerate(sorted(ICONS)):
            m = Image.fromarray(masks[f"{name}_{n}"])
            sheet.paste((236, 236, 236), (i * 40 + (40 - n) // 2, j * 40 + (40 - n) // 2), m)
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(
        os.path.join(HERE, "icons_preview.png"))


if __name__ == "__main__":
    main()
