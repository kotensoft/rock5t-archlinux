#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
SOURCE_TREE=$(realpath "${1:-kernel-next/payload}")
mapfile -t releases < <(find "$SOURCE_TREE/usr/lib/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
((${#releases[@]} == 1)) || { echo 'Expected exactly one explicitly built kernel release' >&2; exit 1; }
KREL=${releases[0]}
[[ $KREL =~ ^6\.18\.[0-9]+-current-rockchip64-landlock[0-9]+$ ]] || { echo 'Refusing legacy/non-Landlock kernel payload' >&2; exit 1; }
PKGVER=${KREL%%-*}
PKGREL=${PKGREL:-2}
[[ $PKGREL =~ ^[1-9][0-9]*$ ]] || exit 1
EPOCH=${SOURCE_DATE_EPOCH:-$(date -u +%s)}
[[ $EPOCH =~ ^[0-9]+$ ]] || exit 1
python3 scripts/validate-next-kernel.py "$SOURCE_TREE" "$KREL"
PKGDIR=$PWD/work/kernel-pkg-$KREL
DEST=$PKGDIR/usr/lib/rock5t-kernel/$KREL
[[ ! -e $PKGDIR ]] || { echo 'Refusing to mix an existing package staging tree' >&2; exit 1; }
mkdir -p "$DEST/dtbs/rockchip" "$DEST/modules" packages
cp "$SOURCE_TREE/boot/Image" "$DEST/Image"
cp "$SOURCE_TREE/boot/config-$KREL" "$DEST/config"
cp "$SOURCE_TREE/boot/System.map-$KREL" "$DEST/System.map"
cp "$SOURCE_TREE/boot/dtbs/rockchip/rk3588-rock-5t.dtb" "$DEST/dtbs/rockchip/"
cp "$SOURCE_TREE/provenance.json" "$DEST/provenance.json"
cp -a "$SOURCE_TREE/usr/lib/modules/$KREL/." "$DEST/modules/"
# Debian build/header pointers are not runtime payloads.
find "$DEST/modules" -maxdepth 1 -type l -name build -delete
find "$DEST/modules" -maxdepth 1 -type l -name source -delete
python3 overlay-work/packaging/make-manifest.py "$DEST"
SIZE=$(du -sb "$PKGDIR/usr" | cut -f1)
cat > "$PKGDIR/.PKGINFO" <<EOF
pkgname = linux-rock5t
pkgbase = linux-rock5t
pkgver = $PKGVER-$PKGREL
pkgdesc = Radxa ROCK5T patched Linux with Landlock and complete source provenance
url = https://www.armbian.com/boards/rock-5t
builddate = $EPOCH
packager = ROCK5T image build
size = $SIZE
arch = aarch64
license = GPL-2.0-only
depend = coreutils
depend = kmod
depend = mkinitcpio
depend = python
EOF
T=$PWD/host-tools/root
export PATH=$T/usr/bin:$PATH LD_LIBRARY_PATH=$T/usr/lib/x86_64-linux-gnu
( cd "$PKGDIR"; tar --sort=name --mtime=@$EPOCH --owner=0 --group=0 --numeric-owner -cf - .PKGINFO usr ) | zstd -T2 -8 -o "packages/linux-rock5t-$PKGVER-$PKGREL-aarch64.pkg.tar.zst"
sha256sum packages/*.pkg.tar.zst > packages/SHA256SUMS
