#!/bin/bash
set -euo pipefail
grep -qw rock5t.builder=1 /proc/cmdline
python3 /mnt/host/overlay-work/tests/test_ssh_parser.py > /mnt/host/vm/next/target-openssh-parser.log 2>&1
pacman -Q > /mnt/host/vm/next/packages-cli-baseline.txt
mapfile -t kde < <(grep -Ev '^[[:space:]]*(#|$)' /mnt/host/profiles/kde.packages)
pacman -Sp --print-format '%l' "${kde[@]}" > /mnt/host/vm/next-kde-urls.txt
rm -rf /usr/lib/modules/6.18.44-current-rockchip64-landlock1
find /var/cache/pacman/pkg -mindepth 1 -maxdepth 1 -type f -delete
sync
