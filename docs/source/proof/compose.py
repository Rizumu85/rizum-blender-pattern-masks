"""The README proof board: the toon skirt (whole, dashed close-up, zigzag
close-up) over the board's own strip of baked masks in UV space, which is kept.

    python compose.py ../../../assets/readme/proof.png ../../../assets/readme/proof.png out
"""
import sys
from PIL import Image, ImageDraw
OLD, OUT = sys.argv[1], sys.argv[2]
old = Image.open(OLD).convert("RGBA")
W, H = old.size
board = old.copy()
BG = (22, 27, 36, 255)
ImageDraw.Draw(board).rectangle((20, 20, W - 21, 830), fill=BG)   # clear the old top row

def panel(box, shot, r=18):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    # the docs' dark stage: lighter in the middle
    g = Image.new("RGBA", (w, h))
    gp = g.load()
    cx, cy = w * 0.5, h * 0.4
    R = (w * w + h * h) ** 0.5 * 0.55
    inner, outer = (40, 49, 67), (29, 36, 49)
    for y in range(h):
        for x in range(w):
            t = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / R)
            gp[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * t) for i in range(3)) + (255,)
    im = Image.open(shot).convert("RGBA").resize((w, h), Image.LANCZOS)
    g.alpha_composite(im)
    m = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), r * 4, fill=255)
    board.paste(g, (x0, y0), m.resize((w, h), Image.LANCZOS))

D = sys.argv[3]
panel((36, 36, 984, 816), f"{D}/P_all.png")
panel((1008, 36, 1764, 414), f"{D}/P_dash.png")
panel((1008, 438, 1764, 816), f"{D}/P_zig.png")
board.save(OUT, optimize=True)

# the masks strip in the skirt's colours: grey checks -> the toon blue, cream ->
# its fabric (anti-aliased edges keep their mix)
import numpy as np
a = np.asarray(board).astype(np.float32)
y0, y1 = 836, H - 20
reg = a[y0:y1, :, :3]
G, Cr = np.array([96, 98, 105.]), np.array([239, 231, 216.])
B2, F2 = np.array([115, 131, 163.]), np.array([246, 239, 226.])
d = Cr - G
t = np.clip(((reg - G) @ d) / (d @ d), 0, 1)
near = np.linalg.norm(reg - (G + t[..., None] * d), axis=-1) < 10
reg[near] = (B2 + t[..., None] * (F2 - B2))[near]
a[y0:y1, :, :3] = reg
Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA").save(OUT, optimize=True)
