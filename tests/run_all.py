"""Every check before a change ships, in one command:

    python tests/run_all.py                      # all three parts
    python tests/run_all.py functional stability # some of them
    python tests/run_all.py performance --save-baseline

  functional   the test scripts in this folder (background and window ones)
  stability    random editing in a Blender window (stress_test.py), several
               seeds: any exception, crash or hang fails
  performance  perf_suite.py, compared with tests/perf_baseline.json: a
               timing more than 30 % and 50 ms slower than the baseline fails
               (measured twice before failing: other programs slow it down;
               with psutil installed, the run also says how busy the computer
               was, before and after)

Blender runs with its user folders in the output folder, so your own
preferences and add-ons are never read or written. The test scenes live in
test/ (local only; tests/make_test_mesh.py builds test/skirt_test.blend);
tests whose scene is missing are skipped. Set BLENDER to pick the Blender
executable (default: blender on the PATH) and TEST_SCENES for another scene
folder, e.g. one made by an older Blender.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# another folder with the test scenes, for an older Blender that can't open
# files saved by a newer one (build it there with make_test_mesh.py)
SCENES = os.environ.get("TEST_SCENES") or os.path.join(REPO, "test")
SKIRT = os.path.join(SCENES, "skirt_test.blend")
BASELINE = os.path.join(HERE, "perf_baseline.json")
BLENDER = os.environ.get("BLENDER", "blender")
BAD = re.compile(r"Traceback|\bFAIL|FAILED|WRONG|Segmentation|EXCEPTION_ACCESS_VIOLATION")

# name, scene, window?, extra: "dir" passes an output folder, "log" a log file
FUNCTIONAL = [
    ("assign_show_test", SKIRT, False, None),
    ("background_test", SKIRT, False, "dir"),
    ("border_line_test", SKIRT, False, "dir"),
    ("clear_scene_test", SKIRT, False, None),
    ("corner_mark_test", SKIRT, False, None),
    ("detect_test", SKIRT, False, None),
    ("edge_sets_test", SKIRT, False, "dir"),
    ("exclude_test", SKIRT, False, None),
    ("fork_loop_test", None, False, None),
    ("grid_test", SKIRT, False, "dir"),
    ("multi_test", SKIRT, False, "dir"),
    ("multi_stitch_test", SKIRT, False, "dir"),
    ("preset_test", SKIRT, False, None),
    ("reference_test", SKIRT, False, "dir"),
    ("zigzag_test", SKIRT, False, "dir"),
    ("scaled_object_test", SKIRT, False, "dir"),
    ("stray_mark_test", SKIRT, False, None),
    ("preview_cache_test", SKIRT, False, None),
    ("undo_layers_test", SKIRT, True, "log"),
    ("undo_test", SKIRT, True, "log"),
    ("preset_default_test", SKIRT, True, "log"),
    ("multi_bake_test", SKIRT, True, "dir"),
]
# files saved by older versions of the add-on (local only)
OLD_FILES = ["user_latest", "user_latest2", "user_latest3", "user_skirt_copy"]


def blender(out, args, log, timeout=900):
    """Run Blender with its user folders inside ``out``; (exit code, seconds)."""
    cfg = os.path.join(out, "blender_user")
    os.makedirs(os.path.join(cfg, "config"), exist_ok=True)
    env = dict(os.environ, BLENDER_USER_RESOURCES=cfg,
               BLENDER_USER_CONFIG=os.path.join(cfg, "config"))
    t = time.perf_counter()
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        try:
            # --python-exit-code: a script that fails to run ends Blender (a
            # window would otherwise stay open until the time-out)
            code = subprocess.run([BLENDER, "--factory-startup", "--python-exit-code", "1"] + args,
                                  cwd=HERE, env=env,
                                  stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    return code, time.perf_counter() - t


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def judge(name, code, texts):
    bad = [ln.strip() for t in texts for ln in t.splitlines() if BAD.search(ln)]
    if code != 0:
        bad.insert(0, f"exit {code}")
    return (not bad), bad[:4]


def functional(out):
    rows = []
    for name, scene, window, extra in FUNCTIONAL:
        if scene and not os.path.exists(scene):
            rows.append((name, None, ["scene missing"]))
            continue
        d = os.path.join(out, name)
        os.makedirs(d, exist_ok=True)
        log, extra_args, files = os.path.join(d, "out.txt"), [], []
        if extra == "dir":
            extra_args = ["--", d]
        elif extra == "log":
            files = [os.path.join(d, "log.txt")]
            extra_args = ["--", files[0]]
        args = ([] if window else ["-b"]) + ([scene] if scene else []) + ["-P", f"{name}.py"]
        code, _s = blender(out, args + extra_args, log)
        ok, why = judge(name, code, [read(log)] + [read(f) for f in files])
        rows.append((name, ok, why))
    # the background bake job starts from a baked file
    if os.path.exists(SKIRT):
        d = os.path.join(out, "bake_job_test")
        os.makedirs(d, exist_ok=True)
        code, _s = blender(out, ["-b", SKIRT, "-P", "run_test.py", "--", d],
                           os.path.join(d, "run_out.txt"))
        res, log = os.path.join(d, "result.blend"), os.path.join(d, "log.txt")
        if code == 0 and os.path.exists(res):
            code, _s = blender(out, [res, "-P", "bake_job_test.py", "--", os.path.join(d, "job"), log],
                               os.path.join(d, "out.txt"))
        ok, why = judge("bake_job_test", code, [read(os.path.join(d, "out.txt")), read(log)])
        rows.append(("bake_job_test", ok, why))
    for stem in OLD_FILES:
        src = os.path.join(SCENES, stem + ".blend")
        for test in ("migrate_test", "migrate_stitch_test"):
            name = f"{test}:{stem}"
            if not os.path.exists(src):
                rows.append((name, None, ["scene missing"]))
                continue
            d = os.path.join(out, test, stem)
            os.makedirs(d, exist_ok=True)
            copy = os.path.join(d, stem + ".blend")       # never the original
            shutil.copy2(src, copy)
            log = os.path.join(d, "out.txt")
            code, _s = blender(out, ["-b", copy, "-P", f"{test}.py"], log)
            ok, why = judge(name, code, [read(log)])
            rows.append((name, ok, why))
    return rows


def stability(out, seeds, steps):
    rows = []
    for seed in seeds:
        d = os.path.join(out, f"stress_{seed}")
        os.makedirs(d, exist_ok=True)
        log = os.path.join(d, "log.txt")
        code, secs = blender(out, [SKIRT, "-P", "stress_test.py", "--", log, str(steps), str(seed)],
                             os.path.join(d, "out.txt"), timeout=1800)
        text = read(log)
        exc = len(re.findall(r"^EXC ", text, re.M))
        done = "\nDONE" in text
        why = [f"{exc} exceptions"] if exc else []
        if not done:
            why.append(f"stopped early (exit {code}): crash or hang")
        info = [ln for ln in text.splitlines() if re.match(r"(panel|overlay) draws|steps ", ln)]
        slow = sorted(re.findall(r"^\d+ (\w+)\n    took (\d+)ms", text, re.M),
                      key=lambda x: -int(x[1]))[:3]
        if slow:
            info.append("slowest steps: " + ", ".join(f"{a} {ms}ms" for a, ms in slow))
        rows.append((f"stress seed {seed}", not why, why + info))
    return rows


def _perf_run(out, d, tag):
    log = os.path.join(d, f"out{tag}.txt")
    code, _s = blender(out, ["-b", SKIRT, "-P", "perf_suite.py"], log)
    text = read(log)
    runs = {r["mesh"]: r for r in (json.loads(m) for m in re.findall(r"^PERF (\{.*\})$", text, re.M))}
    return code, runs


def _slower(runs, base):
    """{mesh: [(name, baseline, now)]} of timings over 30 % and 50 ms slower."""
    out = {}
    for mesh, r in runs.items():
        b = base.get(mesh, {})
        out[mesh] = [(k, b[k], v) for k, v in r.items() if isinstance(v, (int, float))
                     and k not in ("faces", "dashes") and k in b
                     and v > b[k] * 1.3 and v - b[k] > 50]
    return out


def machine_load(seconds=3.0):
    """What else is using the CPU: (cores busy in all, [(program, cores)]),
    or None without psutil."""
    try:
        import psutil
    except ImportError:
        return None
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(seconds)
    use = {}
    for p in procs:
        try:
            c = p.cpu_percent(None) / 100.0
        except psutil.Error:
            continue
        if c > 0.05 and p.info["name"] not in ("System Idle Process", "Idle"):
            use[p.info["name"]] = use.get(p.info["name"], 0.0) + c
    top = sorted(use.items(), key=lambda kv: -kv[1])[:4]
    return sum(use.values()), top


def performance(out, save):
    if not os.path.exists(SKIRT):
        return [("perf_suite", None, ["scene missing"])], None
    d = os.path.join(out, "perf")
    os.makedirs(d, exist_ok=True)
    before = machine_load()
    code, runs = _perf_run(out, d, "")
    if code != 0 or not runs:
        return [("perf_suite", False, [f"exit {code}", "no timings"])], None
    base = json.loads(read(BASELINE) or "{}")
    if any(_slower(runs, base).values()):
        # timings move with whatever else the computer is doing: measure again
        # and keep the faster of the two before calling anything slower
        code, again = _perf_run(out, d, "2")
        for mesh, r in again.items():
            if mesh in runs:
                runs[mesh] = {k: (min(v, runs[mesh][k]) if isinstance(v, (int, float))
                                  and k not in ("faces", "dashes") else v) for k, v in r.items()}
    slower = _slower(runs, base)
    rows = []
    if before is not None:
        after = machine_load()
        busy = max(before[0], after[0])
        top = before[1] if before[0] >= after[0] else after[1]
        note = ", ".join(f"{name} {c:.1f}" for name, c in top)
        rows.append((f"machine: other programs used {busy:.1f} of {os.cpu_count()} cores"
                     + (" (timings may read high)" if busy > 1.0 else ""), "info",
                     [note] if note else []))
    for mesh, r in runs.items():
        b = base.get(mesh, {})
        cells = [f"{k} {v:.0f}" + (f" ({b[k]:.0f})" if k in b else "") for k, v in r.items()
                 if isinstance(v, (int, float)) and k not in ("faces", "dashes")]
        worse = [f"{k} {was:.0f} -> {v:.0f} ms" for k, was, v in slower[mesh]]
        rows.append((f"perf {mesh} ({r['faces']} faces)", not worse,
                     worse + ["ms (baseline): " + ", ".join(cells)]))
    if save:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(runs, f, indent=1, sort_keys=True)
    return rows, runs


def main():
    argv = sys.argv[1:]
    parts = [a for a in argv if a in ("functional", "stability", "performance")] or \
        ["functional", "stability", "performance"]
    opt = {a.split("=")[0]: a.split("=")[1] for a in argv if a.startswith("--") and "=" in a}
    seeds = [int(x) for x in opt.get("--seeds", "11,22,33").split(",")]
    steps = int(opt.get("--steps", "400"))
    out = opt.get("--out", os.path.join(SCENES, "out", time.strftime("checks_%Y%m%d_%H%M%S")))
    os.makedirs(out, exist_ok=True)
    rows = []
    if "functional" in parts:
        rows += functional(out)
    if "stability" in parts:
        rows += stability(out, seeds, steps) if os.path.exists(SKIRT) else \
            [("stress", None, ["scene missing"])]
    if "performance" in parts:
        rows += performance(out, "--save-baseline" in argv)[0]
    failed = 0
    for name, ok, why in rows:
        mark = {None: "SKIP", "info": "info", True: "ok  ", False: "FAIL"}[ok]
        failed += ok is False
        print(f"{mark} {name}")
        for w in why:
            print(f"       {w}")
    print(f"\n{failed} failed, logs in {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
