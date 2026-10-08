#!/usr/bin/env bash
# Prepare the exact pinned integrated tree; does not compile or install a kernel.
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
N="$R/kernel-next"
F="$N/build-fd4ebfd1e107d5b89f7a672c7d609789565753b2"
python3 "$R/tools/fetch-kernel-sources.py"
[[ ! -e "$N/linux-6.18.44" ]] || { echo 'Linux source directory already exists; refusing replacement' >&2; exit 1; }
[[ -x "$N/venv/bin/python" ]] || { echo 'Prepare kernel-next/venv as documented first' >&2; exit 1; }
python3 - "$N" <<'PY'
import sys, tarfile
from pathlib import Path
n = Path(sys.argv[1])
# The framework directory may hold verified driver archives, but no existing framework code.
f = n/'build-fd4ebfd1e107d5b89f7a672c7d609789565753b2'
if (f/'lib').exists():
    raise SystemExit('Framework already extracted; refusing replacement')
for archive in ('linux-6.18.44.tar.xz', 'armbian-fd4ebfd1.tar.gz'):
    with tarfile.open(n/archive) as tf:
        tf.extractall(n, filter='data')
PY
git -C "$N/linux-6.18.44" init -q
git -C "$N/linux-6.18.44" config user.name 'ROCK5T source builder'
git -C "$N/linux-6.18.44" config user.email 'build@invalid'
git -C "$N/linux-6.18.44" add .
git -C "$N/linux-6.18.44" commit -qm 'Pinned Linux 6.18.44 source archive'
"$N/scripts/prepare-drivers.sh" integrate
git -C "$N/linux-6.18.44" add -A
git -C "$N/linux-6.18.44" commit -qm 'Pinned Armbian external driver integration'
git -C "$N/linux-6.18.44" rev-parse HEAD > "$N/provenance/driver-source-local-commit.txt"
"$N/scripts/apply-board-patches.sh"
git -C "$N/linux-6.18.44" add -A
git -C "$N/linux-6.18.44" commit -qm 'Pinned Armbian board patches and device trees'
actual=$(git -C "$N/linux-6.18.44" rev-parse HEAD^{tree})
expected=$(cat "$N/provenance/patched-source-tree-hash.txt")
[[ "$actual" == "$expected" ]] || { printf 'Source tree mismatch: expected %s, got %s\n' "$expected" "$actual" >&2; exit 1; }
mkdir -p "$N/build/board"
cp "$N/config/landlock.config" "$N/build/board/.config"
printf 'Integrated source tree verified: %s\n' "$actual"
