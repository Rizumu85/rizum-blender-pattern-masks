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

## Preview captions

1. The panel next to the live previews: stitches, line art and a grid on one skirt
2. The kinds of layer, illustrated: dashed and zigzag stitches, line art and a grid; below, real masks baked into UV space

## Description

Rizum Pattern Masks draws sewing stitches, line art and checks along edges you
mark on a mesh, shows them live in the viewport, and bakes each layer to a
16-bit UV mask PNG for Substance 3D Painter, Clip Studio Paint or any app that
takes masks.

**Layers**

- **Stitches**: dashed or zigzag, a set distance in from the edge measured
  along the fabric, sharp at marked corners. An object can have several stitch
  layers.
- **Line art**: solid lines of one real width everywhere, from outlines to
  bands, following the marked edge exactly.
- **Grid**: a seamless checkerboard laid along the mesh's loops from a marked
  edge, baked as two masks.

**How it works**

- Mark the edges for each layer in Edit Mode. A layer can use another layer's
  edges and follows when they change.
- Sizes are measured on the 3D surface in millimetres, so they stay true
  however the UVs are stretched.
- Settings can be saved as presets. The bake runs in the background with a
  progress bar and writes one PNG per layer to the folder you choose.

**Requirements**

- Blender 4.4 or newer, and a mesh with UVs.
- The add-on reads the base mesh, without modifiers: apply modifiers such as
  Mirror on a copy first.

**Permissions**

- Files: writes the baked mask PNGs to the folder you choose.

Documentation (English, 中文, 日本語):
https://rizumu85.github.io/rizum-blender-pattern-masks/en/

Source code and issues: https://github.com/Rizumu85/rizum-blender-pattern-masks
