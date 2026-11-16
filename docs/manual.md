# Rizum Pattern Masks: manual

The full reference: every row and setting of the panel, the bake, and the
limits. For an overview, see the [README](../README.md).

Places sewing stitches (dashed or zigzag), line art (solid lines of a fixed
real width) and checkerboards along edges you pick on a mesh. Everything is measured along
the surface in millimetres. The result is baked into the mesh's UV space as
16-bit mask PNGs for Substance 3D Painter or a 2D app such as Clip Studio.

Requires Blender 4.4 or newer (tested on 4.4 and 5.0).

## Install

Edit > Preferences > Get Extensions > ⌄ (top right) > **Install from Disk…** >
`rizum_pattern_masks-0.5.0.zip`.

The panel is in the 3D View sidebar (N) under **Pattern Masks**.

## Use

Work on a copy of your .blend. The add-on only adds edge and vertex attributes
to the mesh and never changes its shape, UVs or materials, but a copy is still
the safe way.

The panel is a layer list, like layers in Painter. It starts empty: **+**
next to the list adds a **Stitches**, **Line Art** or **Grid** layer, as many
of each as you like. Until there is a layer, the panel
shows nothing else, and selecting an object never changes it. **The row you select is the
one you work on**: the section below the list is titled with its name and holds,
in working order, its **Edges** row, the **Sharp Corners** row, then its
settings. In the 3D view a layer higher in the list is drawn over the ones
below it; **▲ ▼** next to the list move the selected layer.

1. Select the object and go to Edit Mode.
2. Add a layer with **+** (or select an existing row).
3. Select the edges it should follow. Any edge selection works, not only
   clean loops: Alt+click loops, click / Shift+click single edges, Ctrl+click
   for the shortest path between two vertices, or a loop-select add-on.
   Connected edges are joined into lines automatically.
4. Press **+** in its **Edges** row. The preview is drawn over the 3D view
   (nothing is added to the scene) and updates a moment after you stop
   changing a value.
5. Tune the settings, then **Bake Masks**.

Each row of the list has, from left to right:

- the name (double-click a line art layer to rename it; a name you type goes
  into the file name of its mask),
- the preview color in the viewport (it does not change the masks),
- the edge icon: show or hide the layer's marked edges in the viewport (stitch
  edges purple, line art edges green, the selected row brightest). This is
  display only; it is turned back on when you edit that row's edges,
- the eye: show and bake the layer's result. A hidden layer is neither shown
  nor baked.

**Edges** row (in the selected row's section): **+** add the selected edges,
**−** remove them, arrow selects the row's edges, **×** clears them all, and the
edge icon at the end is the same show / hide toggle as in the list. Each line art layer
has its own edges, so a line drawn by one layer never shows up in another, and
marking them never adds stitches.

**Reference**: the link menu at the end of the Edges row makes the layer also
follow another layer's edges. Choose the layer there, or **Pick in List** and
then click the layer in the list (Esc or right-click cancels). Once a layer is
followed, a **Reference** row under Edges shows it, with **×** to stop; layers
that follow another one show a link in the list. Any layer can refer to any other: line art
to the stitches, the stitches to a line art layer, a grid to either. A layer
follows what the referred layer follows, its reference included, so edges
that several layers need are marked once. To leave out some of the edges a
layer gets this way, select them and press **−** on the Edges row: the layer
drops them (shown red in the viewport while the layer is selected), and the
layer they come from keeps them. **+** takes such an edge back, **×** clears
the layer's own edges and what it left out, and the arrow selects the edges the
layer ends up with. **−** next to the list removes the selected layer together with its
edges (the stitches too; **+** adds them back, without edges).

**Sharp Corners** row, right under Edges (sharp points of the lines, like
pen-tool corner points; a corner is a vertex, so the marks are shared by all
rows):

- **+** / **−** mark or unmark the selected vertices; your marks are what count.
- the arrow selects the marked vertices.
- **Auto** marks likely corners on the marked edges and selects them. It also
  runs once by itself the first time you add edges. It compares each vertex
  with its neighbours: a vertex that bends away from the fabric (where two
  scallops meet) counts even at small angles, and so does a bend much sharper
  than the ones around it.
- the vertex icon at the end shows or hides the corner marks (yellow dots).

The marks are drawn in the 3D view and in the UV editor (UV editor: Edit Mode).
They are only drawn, not stored in the masks; corner marks off the marked edges
are ignored.

At marked corners the inset line meets in a sharp point, like a mitred seam: the
two straight offsets are extended until they meet. The line is smoothed on each
side separately, and two stitches point into the corner. A mark at a very narrow
notch, where that point would lie more than twice the inset from the edge, is
treated as a slit and the line passes over it.

Beside the list, under + and −, the play toggle turns live updates on or off
(turn it off for very heavy meshes); the refresh button under it rebuilds once
(also after you move vertices).

**Flip Side** (under Sharp Corners, for all rows) puts the stitches and lines on the other side of the picked edges
(needed for edges in the middle of the mesh).

### Stitches

Both the stitches and the line art list their settings in the same order:
where the line runs (From Edge, Corner Inset, Smooth), then its shape (Width,
and for stitches Style and its sizes).

**Style**: **Dashed** (separate stitches) or **Zigzag** (one thread going back
and forth across the line). A zigzag starts and ends on the line, is fitted with
a whole number of legs between marked corners, and passes through each marked
corner on the line.

| Setting | Meaning |
|---|---|
| From Edge | Distance of the stitch line from the picked edges: the line is everywhere exactly this far from the nearest edge, measured along the fabric (on the flat UV layout, scaled to real size, and never less than in 3D). On an open border it moves inward automatically. |
| Corner Inset | Extra inset at marked corners. The corner point moves further in, and the line returns to the normal inset along a smooth arc on both sides. |
| Smooth | Evens out low-poly zigzags along the line. Small values keep scallop shapes, large values flatten them. |
| Width / Length / Gap | Stitch size. For a zigzag, Width is the thread, Length the distance along the line from one peak to the next. |
| Height | Zigzag only: how far it swings across the line, peak to peak. It is centred on the line, so the outer peaks are Height / 2 closer to the edge than From Edge. |
| Round Ends | Dashed only: corner radius as a fraction of half the width (1 = fully round ends). |
| Even Fit | Dashed only: closed loops get a whole number of stitches; open lines get equal space at both ends. |

### Line art

Each line art layer is a solid line along its own edges (and those of the
layer it refers to). A new layer starts with no edges, 0.5 mm wide, 0 mm from
the edge and black. Like stitch layers, layers you have not renamed show their
name in the interface language ("Line 2", "线稿 2") and bake to fixed English
file names (`_line2.png`, like `_stitch.png` and `_stitch2.png`); a name you type is used as it is,
in the panel and in the file name.

| Setting | Meaning |
|---|---|
| From Edge | Distance from the picked edges to the outer side of the line. 0 = the line starts right at the edge, like an outline. |
| Corner Inset | Extra inset at marked corners, as for the stitches. |
| Smooth | Smooths the inner side of the line between corners, like the stitch line (0 = off). The outer side keeps the exact edge, so the line still fills up to it. Bends of a low-poly edge stay in the inner side if their vertices are marked as corners: clear those marks to smooth them. |
| Width | Width of the line. It is the same real width everywhere on the model, whatever the UV size of each part. |

The line keeps the exact shape of the edge at its distance: marked inner corners
and outer corners stay sharp points, and it does not round off the way a
filled-and-shrunk outline does in a 2D app.

### Grid

A **Grid** layer (from **+**) is a black-and-white checkerboard on the fabric,
laid out the way one is painted by hand over the wireframe: the squares follow
the mesh's edge loops. Rows follow the loops that run along the marked edge,
columns follow the loops that run away from it, and where the loops lean (as
they do where cloth drapes and shears) the squares lean with them. Triangles
and n-gons carry the rows and columns on from their neighbours.

The squares are measured on the 3D surface, so they are the same real size
everywhere, however the UV layout is stretched. Where the piece flares and the
columns spread apart, a new pair of columns starts once there is room for one
(and the same for rows where the loops fan out), so the squares keep both
their size and their direction. Where a pair starts, the squares fork over
two or three rows, the way a checker runs into a sewn-in wedge; these forks
tend to sit in the folds, where the mesh adds its own loops. The directions
are evened out over a few faces, so the squares follow the loops without
kinking at every quad or turning sharply at thin wedges. A row boundary runs
along the marked edge.

Mark an edge (such as the waist, or a seam) in each piece that should be
checked: every UV island with a marked edge is filled, and the pattern runs on
across UV seams inside those islands. Where one island holds parts built
differently (say a skirt whose loops circle the waist above a flounce whose
loops run along its seam), the squares still follow each part's loops, and
turn where the parts meet.

| Setting | Meaning |
|---|---|
| From Edge | Slides the squares away from the marked edge (drag up to ±100 mm, or type any value), to line them up with squares painted by hand. |
| Along Edge | Slides the squares along the marked edge (the same range). |
| Angle | Turns the squares against the marked edge (45 degrees: on the bias). |
| Cell Size | Size of each square. |
| Wobble | Bows the lines of the squares a little at random, as cloth pulls them out of true; one bow spans a few squares, so a line is curved rather than wavy, and the corners stay sharp. With Unrolled the bows grow with the squares towards the hem. 0 keeps them straight. |
| Layout | How the squares are laid on the piece: **Follow Loops** or **Unrolled** (below). |

**Follow Loops** is the layout described above: rows along the marked edge,
columns down the loops, squares of one size, forking where the piece widens.

**Unrolled** lays each UV island out flat with as little stretch as possible
(the piece's own pattern, at true size), then bends that pattern so the
marked edge becomes a straight line: the edge runs along x at its true
length, the columns go straight down from it, and the squares stay square
but grow away from the edge by the same share the piece widens (a conformal
map, log-polar about the circle the marked edge lies on). Nothing forks and
nothing leans. On a flared piece the squares at the hem are as many times
larger than at the waist as the hem's cloth is longer than the waist: about
1.7 times on a pleated skirt, several times on a long flounce cut on a tight
waist curve. Cloth that lies closer to the edge's centre of curvature than
the edge itself (a notch that is not a true arc) gets squares smaller than
the cell there. Pieces (UV islands) do not match across their seams, as cut
cloth does not. Where the mesh is stretched (not something flat cloth could
take), the squares stretch with it.

The bake writes two masks per grid layer and texture set:
`<object>_<material>_<layer>_black.png` and `_white.png` (the black and the
white squares, each white in its own mask), to color separately in Clip Studio
or Painter and to blend into parts painted by hand. The viewport preview shows
the black squares in the layer's color; the white squares stay clear.

### Presets

The preset button at the right of the layer section's title saves the current
settings under the name typed next to **+**, applies a saved preset (click its
name; Ctrl+Z takes it back) or removes one (**−**). The star next to a preset
makes it the default: new layers of that kind start with it, and **Default**
at the top applies it. Without a starred preset, **Default** sets the layer
back to the add-on's own defaults; click the star again to go back to those.
A setting a preset doesn't hold (one added in a later version) is set to its
default when the preset is applied. Names are kept as typed, symbols included (only `\ / : * ? " < > |`,
which file names can't hold, become `_`). Stitch presets hold all stitch settings, style included; grid presets hold the
six grid settings; line art presets
hold From Edge, Corner Inset, Smooth and Width, and apply
to the selected layer. Presets are Blender preset files in your user scripts
folder (`presets/rizum_pattern_masks/`), so they are available in every .blend.

All lengths are in millimetres, shown with "mm" in the field (0.1 mm per arrow
click). They are converted with
the scene's Unit Scale, so a scene set up as 1 unit = 1 cm also gets real
millimetres.

## Bake

- **Size**: the size of the mask PNGs in pixels (default 4096; use the texture set
  size in Painter).
- **UV Map**: follows the mesh's active UV map (the one selected in Object Data >
  UV Maps) until you pick one from the menu; **Follow Active UV Map** goes back
  to following it.
- **Stitches: Samples & Device** (Samples, Device, CPU Usage; shown only
  while there are stitches). Stitches are baked by rendering their strips with
  Cycles; line art is computed directly from the distance to the edges, so it
  needs none of these. Samples only smooth the antialiased
  border of each stitch; the shape is the same at any count. 16 (the default)
  is clean; 8 leaves a few border pixels up to 0.15 off, 1 is visibly rougher.
  The bake runs in the background, so Blender stays
  usable; the status bar shows the progress (cancel with its × or Esc). CPU Usage
  limits how many cores the bake takes (default 50%), so Blender does not freeze.
  GPU is faster but can make the screen stutter while it bakes.
- **Folder**: the arrow button next to it opens the folder in the file
  manager once something is baked. Where the masks go (default `//stitch_masks/`, next to the .blend;
  save the .blend first). The bake settings belong to each object. An object
  set up for the first time bakes into the folder of another object in the
  scene and at the size you picked last (change it, and the next new object
  uses the new size); its other bake settings start at their defaults.

One PNG is written per material for each stitch and line layer, named
`<object>_<material>_<layer name>.png`: `_stitch.png` for the first stitch
layer, `_stitch2.png` for the next, unless you renamed them. In Painter, each material is one texture set;
slots that use the same material share one image. Baking again overwrites the
same file. Faces in other UDIM tiles get their own file with a `.1002` style
suffix.

**Background**: **Black** = white mask on black, as Painter masks expect;
**Transparent** = white with the mask in the alpha channel (16-bit, soft edges
kept), ready to use as a layer or mask in Clip Studio and similar apps.

The bake button says how many layers it will bake: only rows whose eye is on
and that have edges count. The masks are antialiased. Stitches are bled a few pixels past UV
island borders, so seams stay clean in Painter. Lines are bled by only 2 pixels,
so a line along the outer edge does not get a thick halo in a 2D app.

Line art is computed per texel from the distance to the edges (no ray tracing),
so it is quick and never picks up a second layer of the mesh.

## In Painter

Import the PNG into the project as a texture, then use it as a grayscale mask, for
example on a fill layer for the thread color. After re-baking, re-import the file
so Painter picks up the change.

## Notes and limits

- The base mesh is used and modifiers are ignored. Apply modifiers such as Mirror
  on a copy first, so the mesh matches what Painter gets.
- The line is the set of points at the inset distance from the picked edges, the
  same rule a seamstress follows. So it has no gaps, no doubled stretches and
  no spikes. At a notch or slit narrower than twice the inset it passes over
  the opening. Around an unmarked bend that points into the fabric it runs in a
  round arc. Larger Smooth values soften it further.
- Only edges reachable over the surface within a short range count for a
  point, starting on the fabric side and never crossing the picked edges, and
  distances are measured along the fabric. So where lace curls or folds and
  another part of the edge comes close through the air, the line still keeps
  its distance from the outline as it looks in the texture. The outer side of
  an edge never gets stitches.
- Where the mesh has two layers almost touching (for example a lace edge
  folded over itself), the stitches are baked only onto the layer the line
  lies on, so the texture never shows a second, offset copy of the line.
- At the end of an open line the stitches stop square to the last edge.
- Tiny closed pockets of fabric just beyond the inset (possible on strongly
  curled lace) are ignored rather than stitched as little rings.
- Stitches are kept on the same layer of fabric by walking across connected
  faces, so folds that touch each other are not mixed up.
- The previews (stitches, line art, grid) are drawn over the 3D view, not
  objects of their own: they show and hide with their object (Shift+H, H,
  local view). Turn a layer's preview off in the add-on's panel. Files saved
  with versions before 0.5.0 had preview objects; they are removed when the
  file is opened.
- Vertices moved by hand in Edit Mode update the preview when you leave Edit
  Mode (the add-on's own buttons update it at once). An object linked into two
  scenes with different Unit Scales shows one scene's preview at a time.
- An 8192 bake needs about 2 GB of free memory for the image buffers.
- A single face whose UVs cross a UDIM tile border is baked into one tile only.
- A grid is worked out again when its Cell Size or Angle changes: about a
  quarter of a second for a 4,000-triangle piece, a second and a half for
  30,000 triangles.
- Unrolled first lays the piece out flat, which takes a second or two on a
  4,000-triangle piece (longer on bigger ones). Press **Unroll** under Layout
  to work it out; the preview appears when it is done, and it is kept until
  the mesh or the marked edge changes, so Cell Size, Angle and the offsets
  stay quick afterwards. Baking works it out by itself.
- The viewport preview draws the Wobble's bows straight across each mesh
  triangle (the bake is smooth per texel): on a coarse mesh with large
  squares a bow can show a slight corner at a triangle edge in the preview
  only.
- Where the piece widens (a flared skirt), new columns of squares must start
  somewhere, and each start shows as a small fork two or three rows tall.
  Their number is set by how much the piece widens divided by the square
  size, so larger squares mean fewer forks; where they sit follows from the
  mesh's loops. Unrolled has none, at the price of the squares growing
  towards the hem. The viewport preview cuts those triangles finer to show
  them.

## Development

- `rizum_pattern_masks/` is the add-on itself.
- `tests/` holds scripts run inside Blender, for example
  `blender -b --factory-startup test/skirt_test.blend -P tests/grid_test.py -- <out_dir>`.
  `tests/make_test_mesh.py` makes `test/skirt_test.blend`. The `test/` folder
  holds local scenes and renders and is not in git.
- `python build.py` writes the zip to `dist/`. `python build.py --install`
  also copies the files into Blender 5.0's `extensions/user_default/rizum_pattern_masks`.
