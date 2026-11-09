"""Build the extension zip into dist/, and optionally install it.

    python build.py            # dist/Rizum_pattern_masks-<version>.zip
    python build.py --install  # also copy the files into Blender 5.0's
                               # extensions/user_default/pattern_masks

Installing only copies files; it never starts Blender, so Blender's
preferences are left alone. Restart Blender to load the new files.
"""
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "pattern_masks")
BLENDER = "5.0"


def manifest_value(key):
    with open(os.path.join(PKG, "blender_manifest.toml"), encoding="utf-8") as f:
        m = re.search(rf'^{key}\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1)


def main():
    ext_id, version = manifest_value("id"), manifest_value("version")
    files = sorted(f for f in os.listdir(PKG) if f.endswith((".py", ".toml")))
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", f"Rizum_{ext_id}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(PKG, f), f)
    print("built", out, os.path.getsize(out), "bytes")
    if "--install" in sys.argv:
        dst = os.path.join(os.environ["APPDATA"], "Blender Foundation", "Blender", BLENDER,
                           "extensions", "user_default", ext_id)
        os.makedirs(dst, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(PKG, f), os.path.join(dst, f))
        print("installed", dst)


if __name__ == "__main__":
    main()
