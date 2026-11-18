"""Build the extension zip into dist/, and optionally install it.

    python build.py            # dist/rizum_pattern_masks-<version>.zip
    python build.py --install  # also copy the files into Blender 5.0's
                               # extensions/user_default/rizum_pattern_masks
    python build.py --repo     # also put the zip in site/extensions/ and write
                               # its index.json: the add-on's own extension
                               # repository, published with the docs site

Installing only copies files; it never starts Blender, so Blender's
preferences are left alone. Restart Blender to load the new files.

--repo runs Blender's ``extension server-generate`` (set BLENDER to pick the
executable; default: blender on the PATH), with Blender's user folders in a
temporary folder.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "rizum_pattern_masks")
BLENDER = "5.0"
REPO_DIR = os.path.join(HERE, "site", "extensions")


def manifest_value(key):
    with open(os.path.join(PKG, "blender_manifest.toml"), encoding="utf-8") as f:
        m = re.search(rf'^{key}\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1)


def main():
    ext_id, version = manifest_value("id"), manifest_value("version")
    files = sorted(f for f in os.listdir(PKG) if f.endswith((".py", ".toml", ".npz")))
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", f"{ext_id}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(PKG, f), f)
        z.write(os.path.join(HERE, "LICENSE"), "LICENSE")     # the GPL text goes with the code
    print("built", out, os.path.getsize(out), "bytes")
    if "--install" in sys.argv:
        dst = os.path.join(os.environ["APPDATA"], "Blender Foundation", "Blender", BLENDER,
                           "extensions", "user_default", ext_id)
        os.makedirs(dst, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(PKG, f), os.path.join(dst, f))
        print("installed", dst)
    if "--repo" in sys.argv:
        os.makedirs(REPO_DIR, exist_ok=True)
        for f in os.listdir(REPO_DIR):          # one version is offered: the latest
            if f.endswith(".zip"):
                os.remove(os.path.join(REPO_DIR, f))
        shutil.copy2(out, REPO_DIR)
        with tempfile.TemporaryDirectory() as cfg:
            env = dict(os.environ, BLENDER_USER_RESOURCES=cfg,
                       BLENDER_USER_CONFIG=os.path.join(cfg, "config"))
            subprocess.run([os.environ.get("BLENDER", "blender"), "--factory-startup",
                            "--command", "extension", "server-generate",
                            "--repo-dir", REPO_DIR], env=env, check=True)
        print("repository", REPO_DIR)


if __name__ == "__main__":
    main()
