"""Make viewable crops of a baked mask and print stats. python inspect_mask.py <mask.png> <out_prefix>"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

src, prefix = sys.argv[1], sys.argv[2]
im = Image.open(src)
print("mode", im.mode, "size", im.size)
a = np.asarray(im).astype(np.float64)
a /= 65535.0 if a.max() > 255 else 255.0
print("max", a.max(), "nonzero px", int((a > 0).sum()),
      "partial px (AA)", int(((a > 0.02) & (a < 0.98)).sum()))
lab, n = ndimage.label(a > 0.5)
sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
print("components", n, "size min/median/max", sizes.min(), np.median(sizes), sizes.max())

ys, xs = np.nonzero(a > 0.02)
y0, y1 = ys.min(), ys.max()
band = a[max(0, y0 - 20):y1 + 20]
h, w = band.shape
# whole band, downsampled into 4 stacked strips
strips = np.array_split(band, 4, axis=1)
mw = max(s.shape[1] for s in strips)
stack = np.vstack([np.pad(s, ((0, 4), (0, mw - s.shape[1]))) for s in strips])
Image.fromarray((stack * 255).astype(np.uint8)).save(prefix + "_band.png")
# seam crops at u=0 and u=1, 4x zoom
for name, x in (("seam_left", 0), ("seam_right", w - 120)):
    crop = band[:, x:x + 120]
    Image.fromarray((crop * 255).astype(np.uint8)).resize(
        (crop.shape[1] * 4, crop.shape[0] * 4), Image.NEAREST).save(prefix + f"_{name}.png")
print("band rows", y0, y1)
