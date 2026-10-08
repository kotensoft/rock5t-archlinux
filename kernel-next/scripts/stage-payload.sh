#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
R=$(cat "$N/build/board/include/config/kernel.release")
[[ "$R" == 6.18.44-current-rockchip64-landlock1 ]]
[[ "$(cat "$N/logs/kernel-build.exit")" == 0 ]]
P="$N/payload"
mkdir -p "$P/boot" "$P/usr"
"$N/scripts/kernel-make.sh" -j8 modules_install INSTALL_MOD_PATH="$P/usr" \
  INSTALL_MOD_STRIP=1 DEPMOD="$N/host-extra/usr/sbin/depmod"
python3 "$N/scripts/stage-dtbs.py"
cp "$N/build/board/arch/arm64/boot/Image" "$P/boot/Image"
cp "$N/build/board/.config" "$P/boot/config-$R"
cp "$N/build/board/System.map" "$P/boot/System.map-$R"
for link in build source; do
    target="$P/usr/lib/modules/$R/$link"
    if [[ -L "$target" ]]; then rm "$target"; fi
done
python3 "$N/scripts/write-manifest.py"
