# Blender Extensions listing

Images and text for the listing on extensions.blender.org. The add-on zip is
built with `python build.py` (or `blender --command extension build`).

| Field | File |
|---|---|
| Icon | `icon.png` (256 × 256, from `../brand/icon.svg`) |
| Featured image | `featured.png` (1920 × 1080) |
| Preview 1 | `screenshot-panel.png`: the panel next to the live previews |
| Preview 2 | `preview-proof.png` (1920 × 1080): the README's proof board (`../readme/proof.png`, the toon skirt, the two stitch close-ups and the masks in UV space) at 16:9 |

Rebuild them with the scripts in `docs/source/` (see the README's
Development section).

## Description

Rizum Pattern Masks draws sewing stitches, line art and checks along edges you
mark on a mesh, and bakes each layer to a 16-bit UV mask PNG for Substance 3D
Painter, Clip Studio Paint or any app that takes masks.

- **Stitches**: dashed or zigzag, a set distance in from the edge measured
  along the fabric, sharp at marked corners.
- **Line art**: solid lines of one real width everywhere, from outlines to
  bands.
- **Grid**: a checkerboard laid along the mesh's loops from a marked edge,
  baked as two masks.

Sizes are measured on the 3D surface in millimetres, so they stay true however
the UVs are stretched. Layers can reference each other's edges, settings can
be saved as presets, and the bake runs in the background.

Documentation: https://rizumu85.github.io/rizum-blender-pattern-masks/en/
