#!/usr/bin/env python3
"""Versioned production release gate; no mounts, rootfs edits or remote operations."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile

import rock5t_image as image

VERSION = '2026.10.08-landlock1'
KERNEL = '6.18.44-current-rockchip64-landlock1'
BASE = Path(__file__).resolve().parent.parent
PAYLOAD = BASE / 'kernel-next/payload'
KERNEL_SHA256 = 'b1a97163f264bbb06b470d98fa1e68b322da073f4b78316f03f613f9a8d561c7'
DTB_SHA256 = 'faa65e7af08784e74276809fe320ef88e684e402bd37caa1fdb4a975b50e96af'
LOADER_SHA256 = 'bde61feff0227b7616f57cce507ee7764290274b41c09499e988f2ff1753e337'
MAX_INITRAMFS = 256 * image.MIB
PHY = 'kernel/drivers/phy/rockchip/phy-rockchip-snps-pcie3.ko'


def release_paths(variant, version=VERSION):
    image.require(variant in ('cli', 'kde'), 'Unknown variant')
    image.require(re.fullmatch(r'[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[a-z0-9][a-z0-9.-]*', version), 'Invalid release version')
    stem = f'archlinux-rock5t-{variant}-{version}.img'
    return (BASE / 'packaging-work/releases' / version / f'{variant}.ids.json',
            BASE / 'output' / version / stem)


def expected_ids(variant, version=VERSION):
    return image.ids(f'archlinux-rock5t-{variant}-{version}')


def decode_newc(data, files=None):
    """Inspect cpio without extracting paths. Return inventory and unread offset."""
    files = {} if files is None else files
    offset = 0
    while True:
        image.require(data[offset:offset + 6] in (b'070701', b'070702'), 'Initramfs is not newc cpio')
        header = data[offset:offset + 110]
        image.require(len(header) == 110, 'Truncated cpio header')
        try:
            fields = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        except ValueError as error:
            raise ValueError('Invalid cpio fields') from error
        mode, size, name_size, checksum = fields[1], fields[6], fields[11], fields[12]
        image.require(0 < name_size < 4096, 'Invalid cpio filename length')
        start = offset + 110
        end = start + name_size
        image.require(end <= len(data) and data[end - 1] == 0, 'Truncated cpio name')
        name = data[start:end - 1].decode('utf-8')
        while name.startswith('./'):
            name = name[2:]
        image.require(not name.startswith('/') and '..' not in PurePosixPath(name).parts, 'Unsafe cpio path')
        start = (end + 3) & ~3
        end = start + size
        image.require(end <= len(data), 'Truncated cpio contents')
        content = data[start:end]
        if header[:6] == b'070702':
            image.require(sum(content) & 0xffffffff == checksum, 'cpio content CRC mismatch')
        offset = (end + 3) & ~3
        if name == 'TRAILER!!!':
            image.require(size == 0, 'Invalid cpio trailer')
            return files, offset
        if name in ('', '.'):
            image.require(stat.S_ISDIR(mode), 'Invalid cpio root entry')
            continue
        entry = {'mode': mode, 'data': content}
        if name in files:
            image.require((stat.S_ISDIR(mode) and stat.S_ISDIR(files[name]['mode'])) or
                          (stat.S_ISLNK(mode) and files[name] == entry), 'Duplicate cpio file: ' + name)
        files[name] = entry


def inspect_initramfs(path, tools):
    image.regular(path, 'Board initramfs')
    image.require(path.stat().st_size <= MAX_INITRAMFS, 'Initramfs input is unexpectedly large')
    data = path.read_bytes()
    files = {}
    compressed_seen = False
    while data:
        data = data.lstrip(b'\0')
        if not data:
            break
        if data[:6] in (b'070701', b'070702'):
            files, consumed = decode_newc(data, files)
            data = data[consumed:]
        elif data.startswith(b'\x28\xb5\x2f\xfd'):
            image.require(not compressed_seen, 'Nested/repeated compressed initramfs streams unsupported')
            # Bound decompression without trusting archive metadata or extracting files.
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as errors:
                source.write(data)
                source.seek(0)
                process = subprocess.Popen([tools.executable('zstd'), '-d', '-q', '-c'], stdin=source,
                                           stdout=subprocess.PIPE, stderr=errors, env=tools.env)
                try:
                    data = process.stdout.read(MAX_INITRAMFS + 1)
                    if len(data) > MAX_INITRAMFS:
                        process.kill()
                    code = process.wait()
                finally:
                    process.stdout.close()
                errors.seek(0)
                image.require(len(data) <= MAX_INITRAMFS and code == 0,
                              'Invalid/oversized zstd initramfs: ' + errors.read().decode(errors='replace'))
            compressed_seen = True
        else:
            raise ValueError('Production initramfs must use newc plus optional zstd; unsupported stream')
    image.require(files, 'Empty initramfs')
    return files


def validate_initramfs(path, release, payload, tools):
    files = inspect_initramfs(path, tools)
    for name in ('init', 'init_functions', 'hooks/udev', 'config', 'buildconfig',
                 f'usr/lib/modules/{release}/modules.dep.bin', f'usr/lib/modules/{release}/{PHY}'):
        image.require(name in files and stat.S_ISREG(files[name]['mode']) and files[name]['data'],
                      'Board initramfs missing regular file: ' + name)
    image.require(files['init']['mode'] & 0o111, 'Board initramfs init is not executable')
    config = files['buildconfig']['data'].decode('utf-8')
    hooks = re.search(r'^HOOKS=\(([^)]*)\)', config, re.M)
    image.require(hooks is not None, 'No mkinitcpio HOOKS record')
    hook_names = re.findall(r'[a-z_]+', hooks.group(1))
    image.require(hook_names == ['base', 'udev', 'modconf', 'block', 'filesystems', 'fsck'],
                  'Unexpected initramfs hooks (no build-host autodetect or QEMU test hooks permitted)')
    checked = 0
    for name, record in files.items():
        # mkinitcpio may emit the module directory itself with a trailing slash.
        # Parse path components so that slash padding is not an empty release.
        pieces = PurePosixPath(name).parts
        if pieces[:3] == ('usr', 'lib', 'modules'):
            if len(pieces) == 3:
                image.require(stat.S_ISDIR(record['mode']), 'Module root must be a directory: ' + name)
            else:
                image.require(pieces[3] == release, 'Wrong release in board initramfs: ' + name)
        if re.search(r'\.ko(?:\.(?:zst|xz|gz))?$', name):
            image.require(name.startswith(f'usr/lib/modules/{release}/'), 'Kernel module outside release directory')
            source = payload / name
            image.regular(source, 'Initramfs reference module')
            image.require(stat.S_ISREG(record['mode']) and hashlib.sha256(record['data']).hexdigest() == image.digest(source),
                          'Initramfs module differs from tested payload: ' + name)
            checked += 1
    image.require(checked > 0, 'Board initramfs contains no checked modules')
    return {'sha256': image.digest(path), 'files': len(files), 'matching_payload_modules': checked,
            'required_pcie_phy': PHY, 'mkinitcpio_hooks': hook_names,
            'hardware_boot_tested': False}


def read_ext4(rootfs, filename, tools):
    # debugfs has no -w: these are read-only inspections of an offline image.
    result = tools.run('debugfs', '-R', 'cat ' + filename, rootfs)
    image.require(bool(result.strip()), 'Missing root filesystem file: ' + filename)
    return result


def preflight(rootfs, boot, variant, version, payload, tools):
    ids_path, output = release_paths(variant, version)
    values = image.read_ids(ids_path)
    image.require(values == expected_ids(variant, version), 'IDs do not belong to requested version/variant')
    for old in ('cli.ids.json', 'kde.ids.json'):
        old_path = BASE / 'packaging-work' / old
        if old_path.exists():
            prior = image.read_ids(old_path)
            image.require(not set(values[k] for k in ('disk_uuid', 'boot_uuid', 'root_uuid')) &
                          set(prior[k] for k in ('disk_uuid', 'boot_uuid', 'root_uuid')), 'Reusing previous release IDs')
    image.require(image.digest(image.DEFAULT_LOADER) == LOADER_SHA256, 'Original verified ROCK5T U-Boot hash changed')
    image.regular(rootfs, 'Offline rootfs')
    info = image.ext4_info(rootfs)
    image.require(info['filesystem_uuid'] == values['root_uuid'], 'Root filesystem UUID must be version-specific too')
    files = image.boot_inventory(boot)
    entries = image.validate_boot_sources(boot, files, values, tools)
    expected = {'LINUX': f'rock5t/{KERNEL}/Image', 'INITRD': f'rock5t/{KERNEL}/initramfs.img',
                'FDT': f'rock5t/{KERNEL}/board.dtb'}
    image.require(entries == [expected], 'Initial release must boot exactly one new board kernel generation')
    for selected, source, pinned in (('LINUX', payload / 'boot/Image', KERNEL_SHA256),
                                     ('FDT', payload / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb', DTB_SHA256)):
        image.require(image.digest(boot / expected[selected]) == image.digest(source) == pinned,
                      'Boot file differs from pinned tested payload: ' + selected)
    config = (payload / 'boot' / ('config-' + KERNEL)).read_text()
    for key in ('CONFIG_MMC', 'CONFIG_MMC_BLOCK', 'CONFIG_MMC_DW_ROCKCHIP', 'CONFIG_MMC_SDHCI_OF_DWCMSHC',
                'CONFIG_EXT4_FS', 'CONFIG_SECURITY_LANDLOCK'):
        image.require(re.search(r'^' + key + r'=y$', config, re.M), 'Missing built-in board root support: ' + key)
    lsm = re.search(r'^CONFIG_LSM="([^"]+)"$', config, re.M)
    image.require(lsm and 'landlock' in lsm.group(1).split(','), 'Landlock absent from default LSM list')
    board_initramfs = validate_initramfs(boot / expected['INITRD'], KERNEL, payload, tools)
    generation = json.loads((boot / f'rock5t/{KERNEL}/generation.json').read_text())
    image.require(generation.get('release') == KERNEL, 'Generation release mismatch')
    expected_hashes = {name: image.digest(boot / f'rock5t/{KERNEL}/{name}') for name in ('Image', 'board.dtb', 'initramfs.img')}
    image.require(generation.get('boot_files') == expected_hashes, 'Generation boot hash metadata mismatch')
    fstab = read_ext4(rootfs, '/etc/fstab', tools)
    wanted = {'/': (values['root_uuid'], 'ext4'), '/boot': (values['boot_uuid'], 'vfat')}
    seen = set()
    for line in fstab.splitlines():
        fields = line.split('#', 1)[0].split()
        if len(fields) >= 3 and fields[1] in wanted:
            identifier, filesystem = wanted[fields[1]]
            image.require(fields[1] not in seen and fields[0] == 'PARTUUID=' + identifier and fields[2] == filesystem,
                          'Root fstab partition identity/type mismatch')
            seen.add(fields[1])
    image.require(seen == set(wanted), 'Missing root or boot fstab entry')
    kernel_config = json.loads(read_ext4(rootfs, '/etc/rock5t/kernel.json', tools))
    cmdline = kernel_config.get('cmdline', '').split()
    image.require([v for v in cmdline if v.startswith('root=')] == ['root=PARTUUID=' + values['root_uuid']],
                  'Root kernel.json PARTUUID mismatch')
    image.require('rt_group_sched=0' in cmdline, 'Expected tested RT policy')
    image.require(read_ext4(rootfs, '/etc/rock5t/variant', tools).strip() == variant, 'Root variant marker mismatch')
    return {'schema': 1, 'status': 'passed', 'version': version, 'variant': variant, 'kernel_release': KERNEL,
            'original_uboot_sha256': LOADER_SHA256, 'board_initramfs': board_initramfs,
            'payload_kernel_sha256': expected_hashes['Image'], 'payload_dtb_sha256': expected_hashes['board.dtb'],
            'partition_ids': values, 'hardware_tested': False, 'output': str(output)}


def verify_compressed(compressed, raw_sha256):
    image.regular(compressed, 'Full compressed image')
    h = hashlib.sha256()
    with lzma.open(compressed, 'rb') as f:
        for data in iter(lambda: f.read(image.CHUNK), b''):
            h.update(data)
    image.require(h.hexdigest() == raw_sha256, 'Compressed stream does not reproduce raw image SHA256')
    return h.hexdigest()


def verify_release(variant, version, tools, rootfs=None):
    _, output = release_paths(variant, version)
    manifest = json.loads(Path(str(output) + '.manifest.json').read_text())
    image.require(manifest.get('release_preflight', {}).get('status') == 'passed', 'Missing release preflight evidence')
    evidence = manifest['release_preflight']
    image.require(evidence.get('version') == version and evidence.get('variant') == variant and
                  evidence.get('kernel_release') == KERNEL, 'Release evidence mismatch')
    image.require(manifest['partition_ids'] == expected_ids(variant, version), 'Release IDs mismatch')
    result = image.verify(output, manifest, tools, rootfs=rootfs)
    image.require(image.digest(output) == manifest['image_sha256'], 'Raw whole-image SHA256 mismatch')
    compressed = Path(str(output) + '.xz')
    image.require(image.digest(compressed) == manifest['compressed_sha256'], 'Compressed SHA256 mismatch')
    verify_compressed(compressed, manifest['image_sha256'])
    result['compressed_roundtrip_sha256'] = 'passed'
    result['version'] = version
    result['variant'] = variant
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('paths', 'preflight', 'package', 'verify'))
    parser.add_argument('--variant', required=True, choices=('cli', 'kde'))
    parser.add_argument('--version', default=VERSION)
    parser.add_argument('--rootfs', type=Path)
    parser.add_argument('--boot-dir', type=Path)
    parser.add_argument('--payload', type=Path, default=PAYLOAD)
    parser.add_argument('--tools', type=Path, default=image.DEFAULT_TOOLS)
    args = parser.parse_args()
    try:
        ids_path, output = release_paths(args.variant, args.version)
        tools = image.Tools(args.tools)
        if args.command == 'paths':
            result = {'ids': str(ids_path), 'output': str(output), 'partition_ids': expected_ids(args.variant, args.version)}
        elif args.command == 'verify':
            result = verify_release(args.variant, args.version, tools, args.rootfs)
        else:
            image.require(args.rootfs is not None and args.boot_dir is not None, '--rootfs and --boot-dir are required')
            result = preflight(args.rootfs.resolve(), args.boot_dir.resolve(), args.variant, args.version, args.payload.resolve(), tools)
            if args.command == 'package':
                output.parent.mkdir(parents=True, exist_ok=True)
                image.package(argparse.Namespace(tools=args.tools, ids=ids_path, rootfs=args.rootfs,
                                                 boot_dir=args.boot_dir, bootloader=image.DEFAULT_LOADER,
                                                 output=output, no_compress=False))
                manifest_path = Path(str(output) + '.manifest.json')
                manifest = json.loads(manifest_path.read_text())
                verify_compressed(Path(str(output) + '.xz'), manifest['image_sha256'])
                manifest['release_preflight'] = result
                manifest['compressed_decompressed_sha256_verified'] = True
                manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
                validation_path = Path(str(output) + '.validation.json')
                validation = json.loads(validation_path.read_text())
                validation['release_preflight'] = result
                validation['preflight_tool_results'] = tools.logs
                validation['compressed_roundtrip_sha256'] = 'passed'
                validation_path.write_text(json.dumps(validation, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, lzma.LZMAError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
