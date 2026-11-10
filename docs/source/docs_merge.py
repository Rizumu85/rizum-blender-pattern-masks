"""Merge Gemini's per-page drafts (docs-page-<slug>.json) into
docs/content/en.json, checking each against the planned structure: page
slugs, section ids in order, and figures where the plan puts them.

    python docs/source/docs_merge.py <drafts_dir>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import tempfile  # noqa: E402

sys.argv, drafts = sys.argv[:1] + [tempfile.mkdtemp()], sys.argv[1]   # the plan module writes prompts there
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("docs_prompt", os.path.join(HERE, "docs_prompt.py"))
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)            # PAGES and FIGURES

FIG_OF = {}
for slug, _, sections in plan.PAGES:
    for sid, what in sections:
        for fid in plan.FIGURES:
            if f"Figure: {fid}" in what:
                FIG_OF[(slug, sid)] = fid

pages, problems = [], []
for slug, _, sections in plan.PAGES:
    path = os.path.join(drafts, f"docs-page-{slug}.json")
    if not os.path.exists(path):
        problems.append(f"{slug}: no draft")
        continue
    page = json.load(open(path, encoding="utf-8"))
    if "pages" in page:                    # an older reply shape
        page = page["pages"][0]
    if page.get("slug") != slug:
        problems.append(f"{slug}: slug is {page.get('slug')!r}")
        page["slug"] = slug
    ids = [s.get("id") for s in page.get("sections", [])]
    want = [sid for sid, _ in sections]
    if ids != want:
        problems.append(f"{slug}: sections {ids} != {want}")
    for s in page.get("sections", []):
        s["figure"] = FIG_OF.get((slug, s.get("id")), "")
        s.setdefault("table", [])
        s.setdefault("body", "")
    pages.append(page)

out = os.path.join(os.path.dirname(os.path.dirname(HERE)), "docs", "content", "en.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"lang": "en", "pages": pages}, f, ensure_ascii=False, indent=1)
print("wrote", out, len(pages), "pages")
for p in problems:
    print("CHECK", p)
