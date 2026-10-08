#!/bin/bash
set -euo pipefail
phase=${1:?cli or kde}
case "$phase" in cli|kde) ;; *) exit 2;; esac
while IFS= read -r url; do
 case "$url" in http://*|https://*) name=${url##*/}; cp -u "/mnt/host/arch-packages/$name" /var/cache/pacman/pkg/; cp "/mnt/host/arch-packages/$name.sig" /var/cache/pacman/pkg/;; esac
done < "/mnt/host/vm/next-$phase-urls.txt"
source /mnt/host/scripts/profile-packages.sh
install_profile "$phase"
pacman -Q > "/mnt/host/vm/packages-$phase-base.txt"
