#!/bin/bash
set -euo pipefail
# Run INSIDE the disposable ARM64 builder VM, as its root user.
# Uses the official Arch Linux ARM repositories and mandatory package signatures.
source /mnt/host/vm/proxy.env
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Syu --noconfirm
source /mnt/host/scripts/profile-packages.sh
install_profile cli
pacman -Q > /mnt/host/vm/packages-cli-base.txt
