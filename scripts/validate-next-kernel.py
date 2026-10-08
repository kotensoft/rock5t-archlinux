#!/usr/bin/env python3
"""Fail closed before packaging a replacement for the fixed Armbian board kernel."""
import argparse
import json
from pathlib import Path
import re


def config(path):
    result = {}
    for line in path.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            result[key] = value.strip('"')
    return result


def validate(source, release, baseline):
    actual = config(source / 'boot' / ('config-' + release))
    prior = config(baseline)
    if actual.get('CONFIG_SECURITY_LANDLOCK') != 'y' or 'landlock' not in actual.get('CONFIG_LSM', '').split(','):
        raise ValueError('Landlock must be compiled in and included in the default LSM list')
    protected = ('CONFIG_VIDEO_', 'CONFIG_MEDIA_', 'CONFIG_DRM_', 'CONFIG_MMC_',
                 'CONFIG_PCIE_', 'CONFIG_PHY_ROCKCHIP', 'CONFIG_USB_', 'CONFIG_CFG80211',
                 'CONFIG_MAC80211', 'CONFIG_RT_GROUP_SCHED')
    missing = [k for k, v in prior.items() if k.startswith(protected) and v in ('y', 'm') and actual.get(k) != v]
    if missing:
        raise ValueError('Board-driver/config regression: ' + ', '.join(missing))
    image = source / 'boot/Image'
    with image.open('rb') as f:
        f.seek(56)
        if f.read(4) != b'ARM\x64':
            raise ValueError('Expected a raw ARM64 Image')
    dtb = source / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb'
    data = dtb.read_bytes()
    if data[:4] != b'\xd0\x0d\xfe\xed' or b'radxa,rock-5t\0' not in data:
        raise ValueError('Missing ROCK5T-specific DTB')
    provenance = json.loads((source / 'provenance.json').read_text())
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError('Missing source provenance')
    for key in ('linux_commit', 'armbian_commit'):
        if not re.fullmatch(r'[0-9a-f]{40}', provenance.get(key, '')):
            raise ValueError('Missing full provenance commit: ' + key)
    if provenance.get('kernelrelease') != release:
        raise ValueError('Provenance kernelrelease does not match module payload')
    if provenance.get('patchset_hash') != 'd9e569eab50e60b3':
        raise ValueError('The original authenticated board patchset is not identified')
    if provenance.get('baseline_config_sha256') != 'df04c47ef19557272ed2a926f44ec2abea82fcffa334b484589bcbb54c9841a3':
        raise ValueError('The authenticated runtime baseline config is not identified')
    if not (source / 'usr/lib/modules' / release / 'modules.builtin').is_file():
        raise ValueError('Missing matching module tree')
    return {'release': release, 'landlock_config': 'enabled', 'board_config_comparison': 'passed'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('release')
    p.add_argument('--baseline', type=Path, default=Path(__file__).resolve().parent.parent / 'research/deb-root/boot/config-6.18.44-current-rockchip64')
    a = p.parse_args()
    print(json.dumps(validate(a.source, a.release, a.baseline)))
