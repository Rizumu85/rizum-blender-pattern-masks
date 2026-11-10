"""Write the README hero and the add-on icon as SVG.

    python docs/source/make_svgs.py

Both use the add-on's own motif: a scalloped hem with the stitch line inset
from it, the inset arcs meeting in a sharp point at each cusp (what the
add-on does at a marked corner).
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

NIGHT = "#161B24"
PANEL = "#1F2633"
CREAM = "#EFE7D8"
THREAD = "#E8843A"
NAVY = "#22304A"
MUTED = "#8A93A6"
SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', "
        "'Hiragino Sans', 'Yu Gothic UI', Meiryo, sans-serif")

# per README language: the two lines under the name, and the layer names as
# the add-on's panel shows them in that language (no Japanese UI yet)
TEXT = {
    "en": (("Stitches, line art and grids that follow the mesh,", "baked to UV masks for Painter."),
           ("Stitches", "Line Art", "Grid")),
    "zh-CN": (("沿着网格走的缝线、线稿和格纹，", "烘焙成给 Painter 用的 UV 遮罩。"),
              ("缝线", "线稿", "格纹")),
    "ja": (("メッシュに沿ったステッチ・線画・チェック柄を", "Painter 用の UV マスクにベイク。"),
           ("Stitches", "Line Art", "Grid")),
}
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def scallops(x0, x1, y, n, depth):
    """Centres and radius of n circular scallops hanging below y between x0
    and x1 (each arc spans its width and drops ``depth`` below y)."""
    w = (x1 - x0) / n
    half = w / 2
    r = (half * half + depth * depth) / (2 * depth)       # circle through the cusps and the low point
    cy = y + depth - r
    return [(x0 + half + i * w, cy) for i in range(n)], r, w


def arc_path(centres, r, w, y_cusp, start="M"):
    """Path along the lower arcs of the circles, cusp to cusp."""
    out = []
    for i, (cx, cy) in enumerate(centres):
        a = (cx - w / 2, y_cusp)
        b = (cx + w / 2, y_cusp)
        if i == 0:
            out.append(f"{start} {a[0]:.2f} {a[1]:.2f}")
        out.append(f"A {r:.2f} {r:.2f} 0 0 0 {b[0]:.2f} {b[1]:.2f}")
    return " ".join(out)


def inset_path(centres, r, w, d):
    """The stitch line: the arcs moved in by d (concentric, radius r - d),
    joined where neighbours cross, so each cusp becomes a sharp point."""
    rr = r - d
    pts = []
    for i, (cx, cy) in enumerate(centres):
        # neighbours cross on the vertical through the cusp between them
        def cusp_y(xc):
            dx = abs(xc - cx)
            return cy + math.sqrt(max(rr * rr - dx * dx, 0.0))
        left = (cx - w / 2, cusp_y(cx - w / 2))
        right = (cx + w / 2, cusp_y(cx + w / 2))
        pts.append((left, right))
    out = [f"M {pts[0][0][0]:.2f} {pts[0][0][1]:.2f}"]
    for left, right in pts:
        out.append(f"L {left[0]:.2f} {left[1]:.2f}")
        out.append(f"A {rr:.2f} {rr:.2f} 0 0 0 {right[0]:.2f} {right[1]:.2f}")
    return " ".join(out)


def hero(lang="en"):
    lines, names = TEXT[lang]
    W, H = 1200, 360
    y = 304                                   # where the scallops hang from
    n, depth = 10, 26
    margin = 0
    cs, r, w = scallops(margin, W - margin, y, n, depth)
    hem = arc_path(cs, r, w, y)
    body = f"M 0 22 Q 0 0 22 0 L {W - 22} 0 Q {W} 0 {W} 22 L {W} {y} " + \
        hem.replace("M", "L", 1).replace(f"L {0:.2f}", f"L {0:.2f}") + " Z"
    # rebuild hem in reverse order for a closed outline: right to left
    cs_r = list(reversed(cs))
    hem_r = []
    for i, (cx, cy) in enumerate(cs_r):
        a = (cx + w / 2, y)
        b = (cx - w / 2, y)
        if i == 0:
            hem_r.append(f"L {a[0]:.2f} {a[1]:.2f}")
        hem_r.append(f"A {r:.2f} {r:.2f} 0 0 1 {b[0]:.2f} {b[1]:.2f}")
    body = f"M 0 22 Q 0 0 22 0 L {W - 22} 0 Q {W} 0 {W} 22 L {W} {y} " + " ".join(hem_r) + " Z"
    stitch = inset_path(cs, r, w, 15)
    trim = arc_path(cs, r - 3.5, w, y)

    # the layer list on the right, as in the add-on's panel, feeding mask files
    lx, ly = 760, 64
    rows = list(zip(names, ("_stitch.png", "_line.png", "_grid_black.png")))
    rows_svg = []
    for i, (name, f) in enumerate(rows):
        yy = ly + i * 62
        if i == 0:
            icon = (f'<path d="M 18 {yy + 25} H 52" stroke="{THREAD}" stroke-width="5" '
                    f'stroke-linecap="round" stroke-dasharray="8 7"/>')
        elif i == 1:
            icon = f'<path d="M 18 {yy + 25} H 52" stroke="{CREAM}" stroke-width="5" stroke-linecap="round"/>'
        else:
            sq = []
            for a in range(4):
                for b in range(2):
                    if (a + b) % 2 == 0:
                        sq.append(f'<rect x="{18 + a * 8.5}" y="{yy + 17 + b * 8.5}" width="8.5" height="8.5" fill="{CREAM}"/>')
            icon = "".join(sq)
        rows_svg.append(
            f'<rect x="0" y="{yy}" width="200" height="50" rx="10" fill="{PANEL}"/>{icon}'
            f'<text x="68" y="{yy + 32}" font-family="{SANS}" font-size="21" fill="{CREAM}">{name}</text>'
            f'<path d="M 214 {yy + 25} H 244" stroke="{MUTED}" stroke-width="2"/>'
            f'<path d="M 238 {yy + 19} L 246 {yy + 25} L 238 {yy + 31}" fill="none" stroke="{MUTED}" stroke-width="2"/>'
            f'<text x="258" y="{yy + 31}" font-family="{MONO}" font-size="19" fill="{MUTED}">{f}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
  <title id="title">Rizum Pattern Masks</title>
  <desc id="desc">A Blender add-on: stitches, line art and grids that follow the mesh, baked to UV mask PNGs. The banner's own scalloped edge carries a dashed stitch line that meets in sharp points at the cusps, as the add-on draws it.</desc>
  <path d="{body}" fill="{NIGHT}"/>
  <path d="{trim}" fill="none" stroke="{NAVY}" stroke-width="7"/>
  <path d="{stitch}" fill="none" stroke="{THREAD}" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="miter" stroke-dasharray="15 11"/>
  <g id="title-block" transform="translate(64 0)">
    <text x="0" y="92" font-family="{MONO}" font-size="19" letter-spacing="2" fill="{MUTED}">RIZUM · BLENDER ADD-ON</text>
    <text x="0" y="168" font-family="{SANS}" font-size="74" font-weight="700" fill="{CREAM}">Pattern Masks</text>
    <text x="2" y="214" font-family="{SANS}" font-size="25" fill="{MUTED}">{lines[0]}</text>
    <text x="2" y="246" font-family="{SANS}" font-size="25" fill="{MUTED}">{lines[1]}</text>
  </g>
  <g id="layers" transform="translate({lx} 0)">
    {"".join(rows_svg)}
  </g>
</svg>
'''
    return svg


def icon(size=256, small=False):
    """The add-on icon: a scalloped hem running corner to corner, cloth with
    a band of checks in the upper left, the dark tile below right (so the
    icon keeps its edge on light pages). The hem has a line along it and
    stitches inside, a gap centred on every scallop tip. ``small``: a variant
    for about 32 px (fewer scallops, bolder strokes)."""
    S = size
    # shallow enough that the inset arcs still meet above each tip
    n, depth = (3, 18) if small else (4, 15)
    # drawn level, then turned 45 degrees about the centre: cloth above the
    # hem line, which sits a little below right of the centre
    L, y = S * 1.5, 26
    cs, r, w = scallops(-L / 2, L / 2, y, n, depth)
    hem = arc_path(cs, r, w, y)
    fabric = f"M {-L / 2} -400 L {-L / 2} {y} " + hem.replace("M", "L", 1) + f" L {L / 2} -400 Z"
    # two rows of checks, one square centred on the tile's corner
    cell = S / 7.5
    checks = []
    for a in range(-6, 7):
        for b in range(2):
            if (a + b) % 2 == 0:
                checks.append(f'<rect x="{(a - 0.5) * cell:.2f}" y="{-118 - b * cell:.2f}" '
                              f'width="{cell:.2f}" height="{cell:.2f}" fill="{NAVY}"/>')
    # the line and the stitches are the hem offset into the cloth (concentric
    # arcs meeting in a point at each tip, as the add-on draws a marked
    # corner), so the cream between them stays even all along
    band = 11 if small else 8                      # the line along the hem
    edge = 7 if small else 6                       # cream between the hem and the line
    sw = 10 if small else 7.5                      # thread width
    lift = 34 if small else 26                     # stitches this far inside the hem
    line = inset_path(cs, r, w, edge + band / 2)
    stitch = inset_path(cs, r, w, lift)
    # a whole number of stitches per scallop, a gap centred on each tip
    rr = r - lift
    arc = rr * 2 * math.asin((w / 2) / rr)
    target = 36 if small else 26
    period = arc / max(1, round(arc / target))
    dash = period * 0.6
    core, gap = dash - sw, period - dash + sw
    offset = core + gap / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}" role="img" aria-labelledby="title">
  <title id="title">Rizum Pattern Masks icon</title>
  <defs>
    <clipPath id="tile"><rect width="{S}" height="{S}" rx="{S * 0.22:.1f}"/></clipPath>
    <clipPath id="fabric"><path d="{fabric}"/></clipPath>
  </defs>
  <rect width="{S}" height="{S}" rx="{S * 0.22:.1f}" fill="{NIGHT}"/>
  <g clip-path="url(#tile)"><g transform="translate({S / 2} {S / 2}) rotate(-45)">
    <path d="{fabric}" fill="{CREAM}"/>
    <g clip-path="url(#fabric)">{"".join(checks)}
      <path d="{line}" fill="none" stroke="{NAVY}" stroke-width="{band}" stroke-miterlimit="20"/>
      <path d="{stitch}" fill="none" stroke="{THREAD}" stroke-width="{sw}" stroke-linecap="round" stroke-dasharray="{core:.2f} {gap:.2f}" stroke-dashoffset="{offset:.2f}"/>
    </g>
  </g></g>
</svg>
'''


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", path)


for lang in TEXT:
    write(os.path.join(REPO, "assets", "readme", "hero.svg" if lang == "en" else f"hero.{lang}.svg"),
          hero(lang))
write(os.path.join(REPO, "assets", "brand", "icon.svg"), icon())


# -- docs site figures (no text: the captions are in each language's page) -----
def piece(W=240, H=160, n=3, depth=16, y=112, x0=34):
    """A cloth piece with a scalloped hem: (outline path, hem path, scallops)."""
    x1 = W - x0
    cs, r, w = scallops(x0, x1, y, n, depth)
    hem = arc_path(cs, r, w, y)
    back = []
    for i, (cx, cy) in enumerate(reversed(cs)):
        a, b = (cx + w / 2, y), (cx - w / 2, y)
        if i == 0:
            back.append(f"L {a[0]:.2f} {a[1]:.2f}")
        back.append(f"A {r:.2f} {r:.2f} 0 0 1 {b[0]:.2f} {b[1]:.2f}")
    outline = f"M {x0} 28 L {x1} 28 L {x1} {y} " + " ".join(back) + " Z"
    return outline, hem, (cs, r, w, y)


def step_svg(k):
    W, H = 240, 160
    outline, hem, (cs, r, w, y) = piece()
    stitch = inset_path(cs, r, w, 10)
    parts = []
    if k == 1:      # edges selected in Edit Mode
        parts.append(f'<path d="{outline}" fill="#9AA0AA"/>')
        parts.append(f'<path d="{hem}" fill="none" stroke="#FFA02C" stroke-width="4"/>')
        for i, (cx, cy) in enumerate(cs):
            for xx in (cx - w / 2, cx + w / 2):
                parts.append(f'<rect x="{xx - 4}" y="{y - 4}" width="8" height="8" fill="#FFA02C"/>')
        bg = "#2B2F38"
    elif k == 2:    # live preview
        parts.append(f'<path d="{outline}" fill="#C9C2B5"/>')
        parts.append(f'<path d="{stitch}" fill="none" stroke="{THREAD}" stroke-width="5" stroke-linecap="round" stroke-dasharray="9 7"/>')
        parts.append(f'<g transform="translate(150 50)"><rect width="56" height="8" rx="4" fill="#3A4152"/>'
                     f'<rect width="30" height="8" rx="4" fill="{THREAD}"/><circle cx="30" cy="4" r="8" fill="#EFE7D8"/></g>')
        bg = "#2B2F38"
    elif k == 3:    # the baked mask
        parts.append(f'<path d="{stitch}" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round" stroke-dasharray="9 7"/>')
        bg = "#000000"
    else:           # painted with it
        parts.append(f'<path d="{outline}" fill="{CREAM}"/>')
        checks = []
        for a in range(0, 13):
            for b in range(0, 5):
                if (a + b) % 2 == 0:
                    checks.append(f'<rect x="{34 + a * 14}" y="{28 + b * 14}" width="14" height="14" fill="{NAVY}" opacity="0.85"/>')
        parts.append(f'<clipPath id="pc4"><path d="{outline}"/></clipPath><g clip-path="url(#pc4)">{"".join(checks)}</g>')
        parts.append(f'<path d="{hem}" fill="none" stroke="#12161D" stroke-width="4"/>')
        parts.append(f'<path d="{stitch}" fill="none" stroke="{THREAD}" stroke-width="5" stroke-linecap="round" stroke-dasharray="9 7"/>')
        bg = "#2B2F38"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<rect width="{W}" height="{H}" rx="10" fill="{bg}"/>' + "".join(parts) + "</svg>\n")


def reference_svg():
    """Left: a line layer's edges (the waist, green). Right: the stitches refer
    to it and leave out its right half (red): stitches only on the left."""
    W, H = 760, 300
    def ring(cx):
        return f'<ellipse cx="{cx}" cy="110" rx="140" ry="44" fill="none" stroke="#5E6779" stroke-width="2"/>'
    left = (f'<path d="M 60 110 A 140 44 0 0 0 340 110" fill="none" stroke="#4CD964" stroke-width="5"/>'
            f'<path d="M 60 110 A 140 44 0 0 1 340 110" fill="none" stroke="#4CD964" stroke-width="5" opacity="0.45"/>')
    # right: the same waist; stitches 14 px below it on the left half, red edge on the right half
    rx, cx = 140, 580
    right = (f'<path d="M {cx - rx} 110 A {rx} 44 0 0 0 {cx} 154" fill="none" stroke="#4CD964" stroke-width="3"/>'
             f'<path d="M {cx} 154 A {rx} 44 0 0 0 {cx + rx} 110" fill="none" stroke="#FF5A47" stroke-width="5"/>'
             f'<path d="M {cx + rx} 110 A {rx} 44 0 0 0 {cx} 66" fill="none" stroke="#FF5A47" stroke-width="5" opacity="0.45"/>'
             f'<path d="M {cx} 66 A {rx} 44 0 0 0 {cx - rx} 110" fill="none" stroke="#4CD964" stroke-width="3" opacity="0.45"/>'
             f'<path d="M {cx - rx} 126 A {rx} 44 0 0 0 {cx} 170" fill="none" stroke="{THREAD}" stroke-width="6" stroke-linecap="round" stroke-dasharray="10 8"/>')
    body = (f'<path d="M 60 110 L 30 270 L 370 270 L 340 110" fill="#C9C2B5" opacity="0.18"/>'
            f'<path d="M {cx - rx} 110 L {cx - rx - 30} 270 L {cx + rx + 30} 270 L {cx + rx} 110" fill="#C9C2B5" opacity="0.18"/>')
    arrow = f'<path d="M 382 110 H 420" stroke="#8A93A6" stroke-width="3"/><path d="M 412 102 L 422 110 L 412 118" fill="none" stroke="#8A93A6" stroke-width="3"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<rect width="{W}" height="{H}" rx="14" fill="{NIGHT}"/>{body}{ring(200)}{left}{ring(cx)}{right}{arrow}</svg>\n')


site_img = os.path.join(REPO, "site", "img")
for k in (1, 2, 3, 4):
    write(os.path.join(site_img, f"step{k}.svg"), step_svg(k))
write(os.path.join(site_img, "reference.svg"), reference_svg())
write(os.path.join(site_img, "icon.svg"), icon())
write(os.path.join(site_img, "icon-small.svg"), icon(small=True))
write(os.path.join(REPO, "assets", "brand", "icon-small.svg"), icon(small=True))
