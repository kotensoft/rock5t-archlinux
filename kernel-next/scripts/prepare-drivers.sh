#!/usr/bin/env bash
# Reproduce the pinned Armbian driver integration for ROCK5T/current.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/build-fd4ebfd1e107d5b89f7a672c7d609789565753b2"
kerneldir="$ROOT/linux-6.18.44"
PROVENANCE="$ROOT/provenance"
DRIVER_SOURCE="$SRC/lib/functions/compilation/patch/drivers_network.sh"
HARNESS_SOURCE="$SRC/lib/functions/compilation/patch/drivers-harness.sh"
GITHUB_SOURCE=https://github.com
KERNEL_MAJOR_MINOR=6.18
LINUXFAMILY=rockchip64
BRANCH=current
version=6.18
export LC_ALL=C
mkdir -p "$PROVENANCE" "$ROOT/logs" "$SRC/cache/sources" "$SRC/cache/driver-archives"
printf '%s  %s\n' 35ac8a9150c6b4935597297433a3f29f43b3417ac314eacde7705a28ef21a65b "$DRIVER_SOURCE" | sha256sum --check --status
printf '%s  %s\n' 5f7b8785413990adf54b8056da0d90a752fe88084a90bb27f19384160a41b76e "$HARNESS_SOURCE" | sha256sum --check --status
trap 'status=$?; printf "Driver integration failed at line %s, status %s.\n" "$LINENO" "$status" >&2; exit "$status"' ERR

display_alert() { printf '[%s] %s %s\n' "${3:-info}" "${1:-}" "${2:-}"; }
exit_with_error() { printf '%s\n' "$*" >&2; exit 1; }
linux-version() {
    [[ "$1" == compare ]] || exit_with_error "Unsupported version operation: $*"
    dpkg --compare-versions "$2" "$3" "$4"
}

# Derive allowed download coordinates from the original Armbian source.
python3 - "$DRIVER_SOURCE" "$PROVENANCE/original-driver-references.tsv" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding='latin-1')
refs = dict(re.findall(r'local\s+(\w+)=[\'"](commit:[0-9a-f]{40})[\'"]', text))
rows = []
for repository, directory, variable in re.findall(r'fetch_from_repo "\$GITHUB_SOURCE/([^"\s]+)" "([^"\s]+)" "\$\{(\w+)\}"', text):
    rows.append(f'https://github.com/{repository}\t{directory}\t{refs[variable]}\n')
Path(sys.argv[2]).write_text(''.join(rows))
PY

fetch_from_repo() {
    local url="$1" directory="$2" reference="$3"
    local row repository commit archive target checksum
    row=$(printf '%s\t%s\t%s' "$url" "$directory" "$reference")
    grep -Fxq "$row" "$PROVENANCE/original-driver-references.tsv" || exit_with_error "Unlisted driver source: $row"
    [[ "$reference" =~ ^commit:[a-f0-9]{40}$ ]] || exit_with_error "Driver source is not pinned."
    repository=${url#https://github.com/}
    commit=${reference#commit:}
    archive="$SRC/cache/driver-archives/${directory}-${commit}.tar.gz"
    target="$SRC/cache/sources/$directory/$commit"
    if [[ ! -f "$archive" ]]; then
        curl --fail --location --retry 3 --connect-timeout 20 --max-time 300 \
            "https://codeload.github.com/$repository/tar.gz/$commit" --output "$archive.part"
        mv "$archive.part" "$archive"
    fi
    checksum=$(sha256sum "$archive" | cut -d' ' -f1)
    # Public-release reproduction verifies the captured archive lock before extraction.
    python3 - "$archive" "$PROVENANCE/driver-sources.lock.json" <<'VERIFY'
import hashlib, json, sys
from pathlib import Path
path = Path(sys.argv[1])
record = next(x for x in json.loads(Path(sys.argv[2]).read_text())['external_driver_sources']
              if x['archive_filename'] == path.name)
if path.stat().st_size != record['archive_bytes'] or hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != record['archive_sha256']:
    raise SystemExit('Pinned driver archive does not match its recorded hash')
VERIFY
    printf '%s\t%s\t%s\t%s\t%s\n' "$checksum" "$url" "$commit" "$archive" "$(date -u +%FT%TZ)" >> "$PROVENANCE/driver-download-hashes.tsv"
    if [[ ! -f "$target/.armbian-pinned-archive" ]]; then
        [[ ! -e "$target" ]] || exit_with_error "Unverified driver cache exists: $target"
        mkdir -p "$target"
        python3 - "$archive" "$target" "$commit" <<'PY'
import sys, tarfile
from pathlib import Path, PurePosixPath
archive, target, commit = sys.argv[1:]
with tarfile.open(archive, 'r:gz') as tf:
    members = tf.getmembers()
    roots = {m.name.split('/')[0] for m in members}
    if len(roots) != 1 or not next(iter(roots)).endswith('-' + commit):
        raise RuntimeError('Archive root does not match the pinned commit')
    selected = []
    for m in members:
        parts = PurePosixPath(m.name).parts
        if not parts or '..' in parts or m.name.startswith('/'):
            raise RuntimeError('Unsafe archive path')
        if len(parts) == 1:
            continue
        m.name = '/'.join(parts[1:])
        selected.append(m)
    tf.extractall(target, members=selected, filter='data')
Path(target, '.armbian-pinned-archive').write_text(commit + '\n')
PY
    fi
    [[ "$(cat "$target/.armbian-pinned-archive")" == "$commit" ]] || exit_with_error "Driver cache marker mismatch."
}

process_patch_file() {
    local file="$1"
    [[ "$file" == "$SRC/patch/misc/"* && -f "$file" ]] || exit_with_error "Invalid driver patch: $file"
    [[ "$(pwd -P)" == "$kerneldir" ]] || exit_with_error "Patch work directory changed."
    # Mirror Armbian's removal of files declared as new by a patch.
    python3 - "$file" "$kerneldir" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding='latin-1')
root = Path(sys.argv[2]).resolve()
for name in re.findall(r'^--- /dev/null\n\+\+\+ b/([^\n\t]+)', text, re.M):
    p = root / name
    if not p.resolve().is_relative_to(root):
        raise RuntimeError('Patch path escapes kernel tree')
    if p.exists():
        p.unlink()
PY
    printf 'PATCH %s\n' "${file#"$SRC/"}"
    sha256sum "$file" >> "$PROVENANCE/applied-driver-patch-hashes.txt"
    patch --batch -p1 -N --input="$file" --no-backup-if-mismatch --reject-file=-
}

source "$DRIVER_SOURCE"
mapfile -t all_drivers < <(sed -n '/declare -a all_drivers=(/,/^[[:space:]]*)/p' "$HARNESS_SOURCE" | grep -E '^[[:space:]]+driver_[[:alnum:]_]+$' | tr -d '\t ')
[[ ${#all_drivers[@]} == 21 ]] || exit_with_error "Original driver order changed."
printf '%s\n' "${all_drivers[@]}" > "$PROVENANCE/original-driver-order.txt"

case "${1:-integrate}" in
    prefetch)
        while IFS=$'\t' read -r url directory reference; do
            case "$directory" in
                rtl8189es|rtl8189fs|rtl8192eu|rtl8822eu|rtl8852bs|rtl8723ds|uwe5622)
                    fetch_from_repo "$url" "$directory" "$reference" yes ;;
            esac
        done < "$PROVENANCE/original-driver-references.tsv"
        ;;
    integrate)
        [[ -d "$kerneldir/.git" ]] || exit_with_error "Kernel Git base is missing."
        [[ -z "$(git -C "$kerneldir" status --porcelain)" ]] || exit_with_error "Kernel tree must be clean before integration."
        : > "$PROVENANCE/applied-driver-patch-hashes.txt"
        for driver in "${all_drivers[@]}"; do
            cd "$kerneldir"
            version=6.18
            printf 'DRIVER %s\n' "$driver"
            "$driver"
        done
        cd "$kerneldir"
        [[ -n "$(git status --porcelain)" ]] || exit_with_error "Driver integration made no changes."
        [[ -z "$(find . -name '*.rej' -print -quit)" ]] || exit_with_error "Rejected patch file found."
        git diff --stat
        ;;
    *) exit_with_error "Usage: $0 [prefetch|integrate]" ;;
esac
