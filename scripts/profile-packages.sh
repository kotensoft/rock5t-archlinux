#!/bin/bash
# Source only inside the disposable build VM/chroot, never on the user's device.
install_profile() {
    local profile=${1:?profile required} required
    [[ $profile == cli || $profile == kde ]] || return 2
    if [[ ! -r /proc/cmdline ]] || ! grep -qw 'rock5t.builder=1' /proc/cmdline; then
        echo 'Refusing package installation outside the marked build VM' >&2
        return 1
    fi
    local -a wanted legacy profiles=(/mnt/host/profiles/cli.packages)
    if [[ $profile == kde ]]; then profiles+=(/mnt/host/profiles/kde.packages); fi
    mapfile -t wanted < <(grep -hEv '^[[:space:]]*(#|$)' "${profiles[@]}")
    # Fail closed if the requested common requirements were dropped from source.
    for required in rtkit wireless-regdb iw; do
        printf '%s\n' "${wanted[@]}" | grep -qx "$required" || {
            echo "Required package absent from profile: $required" >&2; return 1;
        }
    done
    if [[ $profile == kde ]]; then
        mapfile -t legacy < <(pacman -Qq sddm sddm-kcm firefox 2>/dev/null || true)
        if ((${#legacy[@]})); then pacman -R --noconfirm "${legacy[@]}" || return; fi
    fi
    pacman -S --needed --noconfirm "${wanted[@]}" || return
    pacman -Q "${wanted[@]}" || return
    if [[ $profile == kde ]]; then
        mapfile -t legacy < <(pacman -Qq sddm sddm-kcm firefox 2>/dev/null || true)
        if ((${#legacy[@]})); then
            echo 'Legacy SDDM/Firefox package remains; refusing KDE profile' >&2
            return 1
        fi
        pacman -Q plasma-meta plasma-login-manager chromium || return
    fi
}
