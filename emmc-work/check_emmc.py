#!/usr/bin/env python3
"""Read-only eMMC software audit. Does not open devices or modify images."""
import argparse
import json
from pathlib import Path
import re
import sys

REQUIRED = ('CONFIG_MMC', 'CONFIG_MMC_BLOCK', 'CONFIG_MMC_SDHCI',
            'CONFIG_MMC_SDHCI_PLTFM', 'CONFIG_MMC_SDHCI_OF_DWCMSHC',
            'CONFIG_PINCTRL_ROCKCHIP', 'CONFIG_REGULATOR_FIXED_VOLTAGE',
            'CONFIG_EXT4_FS', 'CONFIG_SECURITY_LANDLOCK')
NODE = '/mmc@fe2e0000'


def require(value, message):
    if not value:
        raise ValueError(message)


def check_config(config):
    for key in REQUIRED:
        require(re.search(r'^' + key + r'=y$', config, re.M), key + ' must be built in')
    lsm = re.search(r'^CONFIG_LSM="([^"]+)"$', config, re.M)
    require(lsm and 'landlock' in lsm[1].split(','), 'Default LSM lacks Landlock')
    return list(REQUIRED)


def check_dtb_properties(props):
    require(props['model'] == 'Radxa ROCK 5T', 'Not a ROCK5T model')
    require({'radxa,rock-5t', 'rockchip,rk3588'} <= set(props['board_compatible'].split()),
            'Not a ROCK5T compatible list')
    require(props['compatible'] == 'rockchip,rk3588-dwcmshc', 'Unexpected eMMC controller')
    require(props['status'] in ('okay', 'ok'), 'eMMC controller disabled')
    require(props['bus-width'] == '8', 'eMMC bus width is not 8')
    require({'non-removable', 'no-sd', 'no-sdio'} <= set(props['properties']),
            'eMMC node lacks expected fixed-MMC properties')
    return props


def load_modules(build):
    directory = build / 'packaging-work'
    sys.path.insert(0, str(directory))
    import rock5t_image
    import release_image
    return rock5t_image, release_image


def audit(build, variant, rootfs=None, boot=None):
    require((rootfs is None) == (boot is None), 'Supply both --rootfs and --boot-dir')
    image, release = load_modules(build)
    payload = build / 'kernel-next/payload'
    tools = image.Tools(build / 'host-tools/root')
    config = payload / 'boot' / ('config-' + release.KERNEL)
    dtb = payload / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb'
    checked_config = check_config(config.read_text())
    properties = {'model': tools.run('fdtget', '-t', 's', dtb, '/', 'model').strip(),
                  'board_compatible': tools.run('fdtget', '-t', 's', dtb, '/', 'compatible').strip(),
                  'properties': tools.run('fdtget', '-p', dtb, NODE).split()}
    for key in ('compatible', 'status', 'bus-width'):
        properties[key] = tools.run('fdtget', dtb, NODE, key).strip()
    check_dtb_properties(properties)
    require(image.digest(dtb) == release.DTB_SHA256, 'Payload DTB differs from release pin')
    require(image.digest(payload / 'boot/Image') == release.KERNEL_SHA256, 'Payload Image differs from release pin')
    require(image.digest(image.DEFAULT_LOADER) == release.LOADER_SHA256, 'Loader differs from release pin')
    require(image.SECTOR == 512 and image.LOADER_START == 32768 and image.BOOT_START == 16777216
            and image.ROOT_START == 1090519040, 'Unexpected production disk layout')
    preflight = None
    if rootfs is not None:
        preflight = release.preflight(rootfs, boot, variant, release.VERSION, payload, tools)
    return {'schema': 1, 'status': 'passed', 'scope': 'root-and-boot-preflight' if preflight else 'payload-only',
            'release': release.VERSION, 'variant': variant, 'kernel': release.KERNEL,
            'emmc_hardware_tested': False, 'flash_performed': False,
            'full_disk_verification_performed': False,
            'final_root_and_boot_preflight_passed': bool(preflight),
            'required_logical_sector_bytes': 512, 'emmc_node': NODE,
            'dtb_properties': properties, 'builtin_config_checked': checked_config,
            'sha256': {'kernel': release.KERNEL_SHA256, 'dtb': release.DTB_SHA256,
                       'bootloader': release.LOADER_SHA256, 'config': image.digest(config)},
            'media_strategy': 'Reuse the same verified whole-disk raw image; no eMMC rename/copy',
            'limits': ['Run release_image.py verify separately on final output.',
                       'This audit does not test eMMC timing, boot ROM, SPI priority or physical media.',
                       'Remove a same-image SD clone before the first eMMC boot.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--variant', choices=('cli', 'kde'), required=True)
    parser.add_argument('--rootfs', type=Path)
    parser.add_argument('--boot-dir', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.build_root.resolve(), args.variant, args.rootfs, args.boot_dir), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
