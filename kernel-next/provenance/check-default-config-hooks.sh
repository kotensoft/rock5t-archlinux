#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/build-fd4ebfd1e107d5b89f7a672c7d609789565753b2"
cd "$ROOT/provenance"
[[ ! -e .config ]]
display_alert() { :; }
exit_with_error() { printf '%s\n' "$*" >&2; exit 1; }
linux-version() { [[ "$1" == compare ]] || exit 1; dpkg --compare-versions "$2" "$3" "$4"; }
ARCH=arm64
BRANCH=current
KERNEL_MAJOR_MINOR=6.18
KERNEL_BTF=yes
source "$SRC/lib/functions/compilation/armbian-kernel.sh"
declare -A opts_val=()
declare -a opts_n=() opts_y=() opts_m=() kernel_config_modifying_hashes=()
mapfile -t hooks < <(compgen -A function armbian_kernel_config__ | LC_ALL=C sort)
for hook in "${hooks[@]}"; do "$hook"; done
armbian_kernel_config_apply_opts_from_arrays
printf '%s\n' "${kernel_config_modifying_hashes[@]}" | tac | LC_ALL=C sort -s -t '=' -uk 1,1 > "$ROOT/provenance/default-config-hook-modifications.txt"
sha256sum "$ROOT/provenance/default-config-hook-modifications.txt"
