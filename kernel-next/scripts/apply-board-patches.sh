#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
SRC="$N/build-fd4ebfd1e107d5b89f7a672c7d609789565753b2"
mkdir -p "$N/empty-userpatches"
exec env SRC="$SRC" PATCH_TYPE=kernel \
  PATCH_DIRS_TO_APPLY=archive/rockchip64-6.18 \
  APPLY_PATCHES=yes PATCHES_TO_GIT=no REWRITE_PATCHES=no \
  GIT_ARCHEOLOGY=no LINUXFAMILY=rockchip64 \
  USERPATCHES_PATH="$N/empty-userpatches" \
  GIT_WORK_DIR="$N/linux-6.18.44" BOARD=rock-5t \
  BRANCH_FOR_PATCHES=rock5t-landlock-source \
  BASE_GIT_REVISION="$(cat "$N/provenance/driver-source-local-commit.txt")" \
  LOG_DEBUG=no "$N/venv/bin/python" "$SRC/lib/tools/patching.py"
