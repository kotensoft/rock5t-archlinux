#!/bin/bash
set -euo pipefail
source /mnt/host/vm/proxy.env
source /mnt/host/scripts/profile-packages.sh
install_profile kde
pacman -Q > /mnt/host/vm/packages-kde.txt
