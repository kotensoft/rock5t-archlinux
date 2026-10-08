#!/usr/bin/env bash
# Read-only metadata verification. Does not fetch, patch, configure or build U-Boot.
# Usage: bash verify-uboot-source.sh /path/to/armbian-build-snapshot
set -eo pipefail
SRC=$(cd "${1:?Usage: bash verify-uboot-source.sh FRAMEWORK_DIRECTORY}" && pwd)
export LC_ALL=C
# Verify the default ROCK5T/current source inputs; ignore shell overrides.
for name in BOARD BRANCH ARCH BOOTCONFIG BOOTDELAY UBOOT_DEBUGGING UBOOT_TARGET_MAP \
 BOOT_SCENARIO BOOT_SUPPORT_SPI BOOT_SOC DDR_BLOB BL31_BLOB BL32_BLOB MINILOADER_BLOB \
 ATF_COMPILE ATFSOURCE ATFBRANCH ATFPATCHDIR ATF_TARGET_MAP ATF_LOG_LEVEL \
 CRUSTCONFIG CRUSTBRANCH CRUSTPATCHDIR IMAGE_PARTITION_TABLE BOOT_FDT_FILE SERIALCON \
 SRC_EXTLINUX SRC_CMDLINE UBOOT_HASH_EXTRA UBOOT_GIT_CACHE_TTL do_normalize_src_path; do
 unset "$name"
done
BOARD=rock-5t BRANCH=current ARCH=arm64 SHOW_DEBUG=no
USERPATCHES_PATH="$SRC/.uboot-verification-no-userpatches"
[[ ! -e "$USERPATCHES_PATH" ]] || { echo 'Verification path unexpectedly exists' >&2; exit 1; }
display_alert() { :; }
debug_var() { :; }
debug_dict() { :; }
enable_extension() { :; } # The two relevant default extensions are explicitly sourced below.
source "$SRC/config/boards/rock-5t.conf"
source "$SRC/config/sources/families/rockchip-rk3588.conf"
source "$SRC/lib/functions/compilation/atf.sh"
source "$SRC/lib/functions/general/hash-files.sh"
source "$SRC/lib/functions/general/extensions.sh"
source "$SRC/extensions/uboot-binman-fix-pkg-resources.sh"
source "$SRC/extensions/uboot-fix-pylibfdt-swig.sh"
source "$SRC/lib/functions/artifacts/artifact-uboot.sh"
# These two hooks only assign recipe variables and declare writer functions.
post_family_config__rock5t_use_mainline_uboot
post_family_config__900_late_default_serial_console_by_branch
# Construct the source-only dump helpers. The selected hooks are all default
# priority 500, so C-locale alphabetical order equals extension-manager order.
for hook in post_uboot_custom_postprocess fetch_custom_uboot build_custom_uboot \
 pre_config_uboot_target post_config_uboot_target pre_package_uboot_image \
 check_uboot_produced_binary_file; do
 mapfile -t functions < <(compgen -A function | grep "^${hook}__" | LC_ALL=C sort)
 if (( ${#functions[@]} )); then
  body=""
  for func in "${functions[@]}"; do body+='"$@" '"$func"'; '; done
  eval "function dump_custom_sources_extension_hooks_${hook}() { $body }"
 fi
done
# Use the authenticated package's U-Boot commit. No network lookup takes place.
run_memoized() {
 GIT_INFO_UBOOT[SHA1]=88dc2788777babfd6322fa655df549a019aa1e69
 GIT_INFO_UBOOT[MAKEFILE_VERSION]=2026.04
 GIT_INFO_UBOOT[MAKEFILE_FULL_VERSION]=2026.04
}
declare -A artifact_map_packages=() artifact_input_variables=()
artifact_uboot_prepare_version
printf '%s\n%s\n' "$artifact_version" "$artifact_version_reason"
expected='version "2026.04" git revision "88dc2788777babfd6322fa655df549a019aa1e69" patches hash "05fe3b9a63ca850e" Extension hooks hash "45e42e29ed80425e56623d5a2d7aeedef8b3405461e91a1082187f5fa70b9045" uboot functions hash "5d42cc02cb77c2c4c35986b8efd4c6d8f4ef677f7e20c7e81ccb6bacadea2aa8" variables hash "9e871aa8124fe599364e1c44a7e73941f77ffc9aab50bc27a46c47ad47e98601" framework bash hash "5da4413f38e29074"'
[[ "$artifact_version_reason" == "$expected" ]] || { echo 'FAIL: at least one component differs' >&2; exit 1; }
[[ "$artifact_version" == '2026.04-S88dc-P05fe-H50cb-V9e87-B5da4' ]] || exit 1
echo 'PASS: all five U-Boot component hashes match the authenticated package.'
