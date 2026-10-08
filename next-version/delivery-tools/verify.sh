#!/usr/bin/env bash
# Verify available full .xz/.img files in this script's directory.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
shopt -s nullglob
checked=0
for list in *.img.sha256 *.img.xz.sha256; do
  file=${list%.sha256}
  [[ -f $file && ! -L $file ]] || continue
  read -r hash name extra < "$list"
  [[ $hash =~ ^[0-9a-f]{64}$ && $name == "$file" && -z ${extra:-} ]] || { echo 'Invalid SHA256 record.' >&2; exit 1; }
  sha256sum --check --strict -- "$list"
  if [[ $file == *.xz ]]; then xz --test -- "$file"; fi
  ((checked+=1))
done
((checked > 0)) || { echo 'No full .img.xz or .img available. Merge the parts first.' >&2; exit 1; }
printf 'Verified %s full image file(s).\n' "$checked"
