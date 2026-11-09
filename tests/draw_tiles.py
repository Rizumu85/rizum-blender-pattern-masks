"""Draw crops from corner_tiles.py output.  python draw_tiles.py in.npy out.png [R] [max]"""
import sys

import numpy as np
from PIL import Image, ImageDraw

data = np.load(sys.argv[1], allow_pickle=True)[0]
R = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 12
S = 300
tiles = []
for label, cu in data["centres"][:mx]:
    def f(p):
        return ((p[0] - cu[0] + R) / (2 * R) * S, (cu[1] + R - p[1]) / (2 * R) * S)

    def vis(a):
        return abs(a[0] - cu[0]) < R * 1.5 and abs(a[1] - cu[1]) < R * 1.5

    im = Image.new('RGB', (S, S), 'black')
    d = ImageDraw.Draw(im)
    for a, b in data["wire"]:
        if vis(a):
            d.line([f(a), f(b)], fill=(60, 60, 60))
    for a, b in data["path"]:
        if vis(a):
            d.line([f(a), f(b)], fill=(200, 60, 200), width=2)
    for L in data["lines"]:
        for p, q in zip(L, L[1:]):
            if vis(p) and abs(p[0] - q[0]) < R and abs(p[1] - q[1]) < R:
                d.line([f(p), f(q)], fill=(80, 220, 255), width=1)
        for p in L:
            if vis(p):
                x, y = f(p)
                d.point((x, y), fill=(255, 255, 255))
    for _, c in data["centres"]:
        if vis(c):
            x, y = f(c)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], outline=(255, 210, 0))
    d.text((4, 4), label, fill='white')
    tiles.append(im)
cols = 4
rows = (len(tiles) + cols - 1) // cols
g = Image.new('RGB', (S * cols, S * rows))
for i, t in enumerate(tiles):
    g.paste(t, ((i % cols) * S, (i // cols) * S))
g.save(sys.argv[2])
print(len(tiles))
