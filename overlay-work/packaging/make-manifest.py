#!/usr/bin/env python3
"""Hash a complete package payload before makepkg. See README.md for layout."""
import argparse
import hashlib
import json
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("payload", type=Path)
p.add_argument("--dtb", default="rockchip/rk3588-rock-5t.dtb")
a = p.parse_args()
release = a.payload.name
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,127}", release) or ".." in release:
    p.error("payload directory must be named with the kernel's exact uname -r")
files = {}
for f in sorted(a.payload.rglob("*")):
    if f.is_symlink():
        p.error(f"remove symlink {f}; do not package build/source module symlinks")
    if f.is_file() and f.relative_to(a.payload).as_posix() != "manifest.json":
        h = hashlib.sha256()
        with f.open("rb") as src:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                h.update(chunk)
        files[f.relative_to(a.payload).as_posix()] = h.hexdigest()
manifest = {"format": 1, "release": release, "dtb": a.dtb, "files": files}
(a.payload / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
print(f"Wrote manifest for {release}: {len(files)} files")
