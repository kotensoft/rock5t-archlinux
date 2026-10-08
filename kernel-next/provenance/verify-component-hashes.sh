#!/usr/bin/env bash
set -euo pipefail
SRC=$(cd "${1:-$(dirname "$0")/fd4ebfd1}" && pwd)
ROOT=$(cd "$(dirname "$0")" && pwd)
SHOW_DEBUG=no
display_alert() { :; }
source "$ROOT/hash-files-aug18.sh"
calculate_hash_for_bash_deb_artifact "$SRC"/lib/functions/compilation/kernel*.sh "$SRC"/lib/functions/compilation/stubble.sh
printf 'framework_bash_hash=%s\n' "$hash_files"
calculate_hash_for_files "$SRC/lib/functions/compilation/patch/drivers_network.sh" "$SRC/lib/functions/compilation/patch/drivers-harness.sh"
printf 'driver_bash_hash=%s\n' "$hash_files"
calculate_hash_for_files "$SRC/config/kernel/linux-rockchip64-current.config"
printf 'config_hash=%s\n' "$hash_files"
if [[ -d "$SRC/patch/kernel/archive/rockchip64-6.18" ]]; then
  calculate_hash_for_all_files_in_dirs "$SRC/patch/kernel/archive/rockchip64-6.18"
  printf 'kernel_patch_hash=%s\n' "$hash_files"
fi
if [[ -d "$SRC/patch/misc" ]]; then
  calculate_hash_for_all_files_in_dirs "$SRC/patch/misc"
  printf 'driver_patch_hash=%s\n' "$hash_files"
fi

calculate_hash_for_variables "install" "Image" "" "Image" ""
printf 'packaging_variables_hash=%s\n' "$hash_variables"
printf '\n' | sha256sum | sed 's/  -$/  empty_extension_hooks/'
