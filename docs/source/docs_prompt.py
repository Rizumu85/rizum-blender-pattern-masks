"""Build the prompts that ask Gemini to draft the documentation site's text,
one per language, from the manual (the source of truth) and a fixed page
structure. The replies are checked against the manual and the code before
they go into the site.

    python docs/source/docs_prompt.py <out_dir>

Writes <out_dir>/prompt-<lang>-<part>.txt: each language in three parts of
three pages (one reply for the whole site is more than Gemini will write).
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
out_dir = sys.argv[1]
os.makedirs(out_dir, exist_ok=True)

manual = open(os.path.join(REPO, "docs", "manual.md"), encoding="utf-8").read()

# the add-on's own Chinese UI labels, so the Chinese docs name buttons as the user sees them
src = open(os.path.join(REPO, "rizum_pattern_masks", "i18n.py"), encoding="utf-8").read()
tree = ast.parse(src)
tables = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
            and node.targets[0].id in ("ZH", "ZH_CTX"):
        tables[node.targets[0].id] = ast.literal_eval(node.value)
labels = {k: v for k, v in {**tables["ZH"], **tables["ZH_CTX"]}.items() if len(k) <= 40}
labels.update({"Edges": "边", "Reference": "引用", "Sharp Corners": "尖角", "Flip Side": "翻到另一侧"})

PAGES = [
    ("index", "Overview", [
        ("what", "What the add-on does, in a few sentences, and who it is for (texturing clothing, bags, plush toys and props in Painter or a 2D app)."),
        ("layers", "The three kinds of layers (stitches, line art, grid), one short paragraph each. Figure: fig-hero-render."),
        ("workflow", "The workflow in four steps: mark edges, tune, bake, use the masks. Figure: fig-workflow."),
        ("why", "What makes it different from painting by hand or using UV-space tools: sizes measured on the 3D surface in millimetres, lines that keep their distance from the edge along the fabric, sharp corners where marked, live preview."),
        ("requirements", "Requirements: Blender 4.4 or newer (tested on 4.4 and 5.0), a mesh with UVs."),
    ]),
    ("start", "Install and first mask", [
        ("install", "Installing: from Blender's Get Extensions (search Pattern Masks), or from a zip with Install from Disk."),
        ("first", "A step-by-step first mask: stitches along a hem, from selecting the mesh to a PNG in Painter. Number the steps. Figure: fig-panel."),
        ("safety", "What the add-on changes in the file (only edge and vertex attributes; never shape, UVs or materials) and the advice to work on a copy."),
    ]),
    ("layers", "Layers and edges", [
        ("list", "The layer list: adding layers (+), the stitch row, line art and grid rows, what each column of a row does (name, preview color, edge marks toggle, eye). The selected row is the one you edit."),
        ("edges", "The Edges row: + adds the selected edges, − removes them, the arrow selects them, × clears them. Any edge selection works."),
        ("reference", "References: a layer can also follow another layer's edges (menu or eyedropper), along a chain of references. Leaving out edges the layer gets this way with −; they show red; + brings them back. Figure: fig-reference."),
        ("corners", "Sharp corners: marking corner vertices (+, −, select, Auto), what a marked corner does to the line (a mitred point), the slit rule."),
        ("side", "Flip Side, live updates (play toggle) and the refresh button."),
    ]),
    ("stitches", "Stitches", [
        ("style", "Dashed and zigzag. Figure: fig-stitch-settings."),
        ("settings", "Every stitch setting as a table: From Edge, Corner Inset, Smooth, Width, Length, Gap, Height (zigzag), Round Ends (dashed), Even Fit (dashed). Say what each changes and when to change it."),
        ("tips", "Practical tips: keeping stitches off a seam, matching a real stitch length, low-poly edges and Smooth."),
    ]),
    ("line-art", "Line art", [
        ("what", "What a line art layer draws: a solid line of one real width, from an outline on the edge to a band further in; several layers; names and file names."),
        ("settings", "Every line art setting as a table: From Edge, Corner Inset, Smooth, Width."),
        ("shape", "How the line keeps the exact shape of the edge, with sharp inner and outer corners, unlike shrinking a filled shape in a 2D app."),
    ]),
    ("grid", "Grid", [
        ("what", "What a grid layer is: a checkerboard laid from a marked edge, squares measured on the surface, two masks (dark and light squares)."),
        ("layouts", "The two layouts. Follow Loops: rows along the marked edge, columns down the loops, squares of one size, forks where the piece widens. Unrolled: the piece laid flat, the edge straight, columns straight down, no forks, squares growing towards the hem; meant for open panels, not closed tubes. Figure: fig-grid-layouts."),
        ("settings", "Every grid setting as a table: From Edge, Along Edge, Angle, Cell Size, Wobble, Layout."),
        ("marking", "Which edge to mark for a grid, and how UV islands decide where squares go."),
    ]),
    ("presets", "Presets", [
        ("use", "Saving, applying (Ctrl+Z undoes it) and removing presets; names kept as typed; what each kind of preset holds."),
        ("default", "The star: making a preset the default for new layers of its kind, and what Default does with and without a starred preset."),
    ]),
    ("bake", "Baking and using the masks", [
        ("settings", "Bake settings: Size, UV Map, Folder, Background (Black or Transparent), Stitches: Samples & Device. The bake runs in the background with a progress bar."),
        ("files", "The files: one PNG per layer and texture set, names, UDIM tiles, what happens when baking again. Grids give two files. Figure: fig-masks."),
        ("painter", "Using the masks in Substance 3D Painter (import, grayscale mask on a fill layer, re-import after a new bake) and in Clip Studio Paint (transparent background)."),
    ]),
    ("limits", "Notes and limits", [
        ("mesh", "Things about the mesh: modifiers are ignored (apply Mirror on a copy), two layers of fabric close together, open line ends, tiny pockets."),
        ("grid", "Grid limits: forks with Follow Loops, Unrolled needs a moment to compute and is for open panels, preview vs bake smoothness."),
        ("bake", "Bake limits: memory for 8192, a face across UDIM tiles."),
        ("faq", "Three to six short questions and answers a new user is likely to have, drawn only from the facts above."),
    ]),
]

FIGURES = {
    "fig-hero-render": "the demo skirt textured with the baked masks",
    "fig-workflow": "a four-step diagram: mark edges, tune, bake, paint",
    "fig-panel": "a screenshot of the add-on's panel next to the live preview",
    "fig-reference": "a screenshot: the stitches refer to a waist line layer and leave out half of it (red)",
    "fig-stitch-settings": "an interactive diagram of the stitch settings on a scalloped edge",
    "fig-grid-layouts": "renders of the same piece with Follow Loops and Unrolled",
    "fig-masks": "the baked masks in UV space",
}

LANG = {
    "en": ("English", "Use the English UI labels exactly as written in the manual."),
    "zh-CN": ("Simplified Chinese (简体中文)",
              "Name every button and setting with the add-on's Chinese UI label from this table "
              "(English label: Chinese label), and Blender's own menus with Blender's Chinese UI "
              "(编辑 › 偏好设置 › 获取扩展, 从磁盘安装…, 编辑模式, 侧边栏):\n"
              + "\n".join(f"{k}: {v}" for k, v in sorted(labels.items()))),
    "ja": ("Japanese (日本語)",
           "The add-on's UI is not translated into Japanese: write its buttons and settings with "
           "their English labels, in bold, as the user sees them (for example **From Edge**), and "
           "explain them in Japanese. Blender's own menus may be named in English with a Japanese "
           "gloss the first time (Get Extensions, Install from Disk…, Edit Mode)."),
}

SCHEMA = {
    "lang": "<language code>",
    "pages": [
        {
            "slug": "<one of the slugs given>",
            "title": "<page title>",
            "lead": "<one or two sentences under the title>",
            "sections": [
                {
                    "id": "<the section id given>",
                    "heading": "<section heading>",
                    "body": "<Markdown: paragraphs, numbered steps, bullet lists, **bold** UI labels, `code`>",
                    "table": [["<setting>", "<what it does>"]],
                    "figure": "<figure id given for this section, or empty>",
                }
            ],
        }
    ],
}


def manual_parts():
    """The manual cut at its headings: {heading or "intro": text}."""
    parts, key, cur = {}, "intro", []
    for line in manual.split("\n"):
        if line.startswith(("## ", "### ")):
            parts[key] = "\n".join(cur)
            key, cur = line.lstrip("# ").strip(), [line]
        else:
            cur.append(line)
    parts[key] = "\n".join(cur)
    return parts


SOURCES = {          # which parts of the manual each page draws on
    "index": ["intro", "Use", "Notes and limits"],
    "start": ["intro", "Install", "Use", "In Painter"],
    "layers": ["Use"],
    "stitches": ["Use", "Stitches"],
    "line-art": ["Line art"],
    "grid": ["Grid", "Notes and limits"],
    "presets": ["Presets"],
    "bake": ["Bake", "In Painter"],
    "limits": ["Notes and limits"],
}


def page_prompt(page):
    """One page in English, from the manual sections it needs: Gemini
    answers this in full (the whole site, or one page in three languages in
    one reply, it declines or fails on). Chinese and Japanese are translated
    from the checked English."""
    slug, title, sections = page
    parts = manual_parts()
    excerpt = "\n\n".join(parts[k] for k in SOURCES[slug] if k in parts)
    spec = [f"PAGE slug={slug} (English working title: {title})"]
    for sid, what in sections:
        spec.append(f"  SECTION id={sid}: {what}")
    figs = "\n".join(f"{k}: {v}" for k, v in FIGURES.items())
    rules = "\n\n".join(f"For {LANG[l][0]}: {LANG[l][1]}" for l in LANG)
    one = {k: v for k, v in SCHEMA["pages"][0].items()}
    return f"""You are writing one page of the user documentation website for a Blender add-on, Rizum Pattern Masks, in English.

The MANUAL EXCERPT below is the only source of facts. Do not add features, numbers, defaults, shortcuts or behaviour it does not state; if it does not say something, leave it out. Explain the facts for someone using the add-on for the first time, in the order of the structure below, without copying the excerpt's sentences.

STYLE
- Plain, direct and concrete. Say what the user does and what they get. No marketing words, no exclamation marks, no filler such as "simply", "easily", "powerful", "seamless".
- Short sentences, one idea each. Paragraphs of two to four sentences.
- Address the reader directly as "you".
- Bold UI labels when you name them. File names and paths in `code`.
- Numbered steps for procedures, tables for settings, bullet lists for parallel items.
- Do not mention the manual, the excerpt or this prompt.

UI LABELS
Use the add-on's UI labels exactly as the excerpt writes them.

STRUCTURE
Write exactly these section ids, in this order. A section with a figure gets that figure id in "figure", the others "". Use "table" only where a section asks for one (rows of [setting, what it does]); otherwise an empty list.
{chr(10).join(spec)}

FIGURES (made separately; refer to them only through the "figure" field)
{figs}

OUTPUT
Reply with one JSON object in a single ```json code block, nothing else, of this shape:
{json.dumps(one, ensure_ascii=False, indent=1)}

MANUAL EXCERPT
{excerpt}
"""


def prompt(lang, pages):
    name, labels_rule = LANG[lang]
    spec = []
    for slug, title, sections in pages:
        spec.append(f"PAGE slug={slug} (English working title: {title})")
        for sid, what in sections:
            spec.append(f"  SECTION id={sid}: {what}")
    figs = "\n".join(f"{k}: {v}" for k, v in FIGURES.items())
    return f"""You are writing the user documentation website for a Blender add-on, Rizum Pattern Masks. Write it in {name}.

The MANUAL below is the only source of facts. Do not add features, numbers, defaults, shortcuts or behaviour that the manual does not state. If the manual does not say something, leave it out. Do not copy the manual's sentences: explain the same facts for someone using the add-on for the first time, in the order of the structure below.

STYLE
- Plain, direct and concrete. Say what the user does and what they get. No marketing words, no exclamation marks, no filler such as "simply", "easily", "powerful", "seamless".
- Short sentences. One idea per sentence. Each paragraph two to four sentences.
- Address the reader directly ("you" in English; 你 in Chinese; no explicit pronoun in Japanese, polite です/ます form).
- Bold the add-on's UI labels when you name them. Put file names and paths in `code`.
- Numbered steps for procedures, tables for settings, bullet lists for parallel items.
- Do not mention the manual or this prompt.

UI LABELS
{labels_rule}

STRUCTURE
This reply covers part of the site. Write every page and every section listed, with exactly these slugs and section ids, in this order. A section that has a figure gets that figure id in "figure"; the others get "". Use "table" only for sections that ask for a table (rows of [setting, what it does]); otherwise give an empty list.
{chr(10).join(spec)}

FIGURES (I will make them; refer to them only through the "figure" field, not in the text)
{figs}

OUTPUT
Reply with one JSON object in a single ```json code block, nothing else, matching this shape:
{json.dumps(SCHEMA, ensure_ascii=False, indent=1)}

MANUAL
{manual}
"""


for page in PAGES:
    text = page_prompt(page)
    path = os.path.join(out_dir, f"prompt-page-{page[0]}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", path, len(text), "chars")

for lang in []:          # the earlier whole-language prompts (Gemini declined them)
    for part in range(3):
        text = prompt(lang, PAGES[part * 3:part * 3 + 3])
        path = os.path.join(out_dir, f"prompt-{lang}-{part + 1}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", path, len(text), "chars")
