#!/usr/bin/env bash
# Run inside one variant's delivery folder. This never writes a block device.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
shopt -s nullglob
lists=(*.img.xz.parts.sha256)
((${#lists[@]} == 1)) || { echo 'Need exactly one matching parts checksum list in this folder.' >&2; exit 1; }
list=${lists[0]}; output=${list%.parts.sha256}; partial=$output.partial
[[ ! -e $output && ! -L $output && ! -e $partial && ! -L $partial ]] || { echo 'Output or partial file exists; nothing overwritten.' >&2; exit 1; }
parts=(); n=1
while read -r hash part extra; do
  expected="$output.part$(printf '%03d' "$n")"
  [[ $hash =~ ^[0-9a-f]{64}$ && $part == "$expected" && -z ${extra:-} && -f $part && ! -L $part ]] || { echo "Invalid or missing part $n." >&2; exit 1; }
  parts+=("$part"); ((n+=1))
done < "$list"
((${#parts[@]} > 0)) || { echo 'Empty parts list.' >&2; exit 1; }
[[ -f $output.sha256 ]] || { echo 'Missing full-file SHA256.' >&2; exit 1; }
sha256sum --check --strict -- "$list"
# noclobber ensures exclusive creation, even if another process starts a merge.
(set -o noclobber; : > "$partial")
trap 'rm -f -- "$partial"' EXIT
cat -- "${parts[@]}" >> "$partial"
read -r hash name extra < "$output.sha256"
[[ $hash =~ ^[0-9a-f]{64}$ && $name == "$output" && -z ${extra:-} ]] || { echo 'Invalid full-file SHA256 record.' >&2; exit 1; }
actual=$(sha256sum -- "$partial"); actual=${actual%% *}
[[ $actual == "$hash" ]] || { echo 'Merged SHA256 mismatch. Do not flash.' >&2; exit 1; }
# Hard-link publication is atomic and refuses an existing output filename.
ln -- "$partial" "$output"
rm -- "$partial"
trap - EXIT
printf 'Merged and SHA256 verified: %s\n' "$output"
printf 'Keep every part until the image has been safely written and verified.\n'
