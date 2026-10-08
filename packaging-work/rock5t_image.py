#!/usr/bin/env python3
"""Build/verify unprivileged ROCK5T GPT images. Never mounts filesystems."""
import argparse
import binascii
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

SECTOR = 512
MIB = 1024 * 1024
BOOT_START = 16 * MIB
BOOT_SIZE = 1024 * MIB
ROOT_START = BOOT_START + BOOT_SIZE
LOADER_START = 32 * 1024
NAMESPACE = uuid.UUID('c26c1300-4b7e-541d-8b52-d297877dc0a1')
EFI_TYPE = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
LINUX_TYPE = '0fc63daf-8483-4772-8e79-3d69d8477de4'
BASE = Path(__file__).resolve().parent.parent
DEFAULT_TOOLS = BASE / 'host-tools/root'
DEFAULT_LOADER = BASE / 'research/deb-root/usr/lib/linux-u-boot-current-rock-5t/u-boot-rockchip.bin'
CHUNK = 4 * MIB


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ids(seed):
    require(bool(seed.strip()), 'seed must not be empty')
    return {'schema': 1, 'seed': seed, **{f'{role}_uuid': str(uuid.uuid5(NAMESPACE, seed + ':' + role)) for role in ('disk', 'boot', 'root')}}


def read_ids(path):
    value = json.loads(Path(path).read_text())
    require(value == ids(value['seed']), 'UUID file differs from deterministic schema')
    return value


def regular(path, desc):
    require(path.is_file() and not path.is_symlink(), f'{desc} must be a regular, non-symlink file: {path}')


def digest(path, offset=0, size=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        f.seek(offset)
        remaining = path.stat().st_size - offset if size is None else size
        while remaining:
            data = f.read(min(CHUNK, remaining))
            require(bool(data), f'Unexpected EOF in {path}')
            h.update(data)
            remaining -= len(data)
    return h.hexdigest()


def sparse_copy(src, dst, dst_offset=0, src_offset=0, length=None):
    """Copy a range without allocating holes; destination range must be new/zero."""
    length = src.stat().st_size - src_offset if length is None else length
    require(length >= 0, 'negative copy length')
    with src.open('rb') as source, dst.open('r+b') as target:
        pos, end = src_offset, src_offset + length
        supports_holes = True
        while pos < end:
            if supports_holes:
                try:
                    start = os.lseek(source.fileno(), pos, os.SEEK_DATA)
                    if start >= end:
                        break
                    stop = min(os.lseek(source.fileno(), start, os.SEEK_HOLE), end)
                except OSError as error:
                    if error.errno == errno.ENXIO:
                        break
                    if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                        raise
                    supports_holes = False
                    start, stop = pos, end
            else:
                start, stop = pos, end
            source.seek(start)
            target.seek(dst_offset + start - src_offset)
            pos = start
            while pos < stop:
                data = source.read(min(CHUNK, stop - pos))
                require(bool(data), f'Unexpected EOF copying {src}')
                if data.count(0) == len(data):
                    target.seek(len(data), 1)
                else:
                    target.write(data)
                pos += len(data)
            pos = stop
        target.flush()
        os.fsync(target.fileno())


class Tools:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.env = os.environ.copy()
        self.env.update(LC_ALL='C', TZ='UTC', MTOOLSRC='/dev/null', MTOOLS_SKIP_CHECK='0')
        self.env['LD_LIBRARY_PATH'] = str(self.root / 'usr/lib/x86_64-linux-gnu')
        self.logs = []

    def executable(self, name):
        for directory in ('usr/sbin', 'usr/bin', 'sbin', 'bin'):
            p = self.root / directory / name
            if p.is_file() and os.access(p, os.X_OK):
                return str(p)
        raise ValueError(f'Missing downloaded host tool: {name} below {self.root}')

    def run(self, name, *args, binary=False):
        command = [self.executable(name), *map(str, args)]
        result = subprocess.run(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        description = shlex.join(command)
        if not binary:
            self.logs.append({'command': description, 'returncode': result.returncode,
                              'stdout': result.stdout.decode(errors='replace'),
                              'stderr': result.stderr.decode(errors='replace')})
        require(result.returncode == 0, f'{description} failed ({result.returncode}):\n{result.stderr.decode(errors="replace")}\n' + ('' if binary else result.stdout.decode(errors='replace')))
        return result.stdout if binary else result.stdout.decode()

    def hash_fat_file(self, image_spec, rel):
        command = [self.executable('mtype'), '-i', image_spec, '::/' + rel]
        h = hashlib.sha256()
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE, stderr=errors)
            for data in iter(lambda: process.stdout.read(CHUNK), b''):
                h.update(data)
            process.stdout.close()
            code = process.wait()
            errors.seek(0)
            require(code == 0, f'mtype failed on {rel}: {errors.read().decode(errors="replace")}')
        return h.hexdigest()


def ext4_info(path):
    with path.open('rb') as f:
        f.seek(1024)
        sb = f.read(1024)
    require(len(sb) == 1024 and struct.unpack_from('<H', sb, 56)[0] == 0xEF53, 'Root is not an ext filesystem')
    state = struct.unpack_from('<H', sb, 58)[0]
    incompat = struct.unpack_from('<I', sb, 96)[0]
    require(state == 1 and not incompat & 4, 'Root filesystem is not cleanly unmounted; journal recovery needed')
    block_size = 1024 << struct.unpack_from('<I', sb, 24)[0]
    blocks = struct.unpack_from('<I', sb, 4)[0]
    if incompat & 0x80:
        blocks |= struct.unpack_from('<I', sb, 0x150)[0] << 32
    require(block_size in (1024, 2048, 4096, 8192, 16384, 32768, 65536), 'Invalid ext4 block size')
    require(block_size * blocks == path.stat().st_size, 'Root image length must exactly match filesystem size')
    require(struct.unpack_from('<I', sb, 92)[0] & 4, 'Root filesystem must have an ext4 journal')
    require(incompat & 0x40, 'Root filesystem must use ext4 extents')
    return {'bytes': block_size * blocks, 'block_size': block_size, 'filesystem_uuid': str(uuid.UUID(bytes=sb[104:120]))}


def validate_fat32(path):
    with path.open('rb') as f:
        sector = f.read(SECTOR)
    require(len(sector) == SECTOR and sector[510:512] == b'\x55\xaa', 'Invalid FAT boot sector')
    require(struct.unpack_from('<H', sector, 11)[0] == SECTOR, 'FAT sector size mismatch')
    require(struct.unpack_from('<H', sector, 17)[0] == 0 and struct.unpack_from('<H', sector, 22)[0] == 0,
            'Boot filesystem is not FAT32')
    require(struct.unpack_from('<I', sector, 36)[0] > 0 and sector[82:90] == b'FAT32   ', 'Boot filesystem is not FAT32')
    require(struct.unpack_from('<I', sector, 32)[0] * SECTOR == BOOT_SIZE, 'FAT filesystem length mismatch')
    require(struct.unpack_from('<I', sector, 28)[0] == BOOT_START // SECTOR, 'FAT hidden-sector offset mismatch')


def format_fat32(path, boot_uuid, tools):
    # mkfs.fat aligns the BPB total-sector count to sectors-per-track. Its
    # default 63-sector geometry truncates a 1 GiB filesystem by 8 sectors.
    # Fixed 32-sector tracks divide our MiB-sized FAT partition exactly.
    serial = boot_uuid.replace('-', '')[:8]
    tools.run('mkfs.fat', '--invariant', '-F', '32', '-S', str(SECTOR), '-g', '64/32',
              '-h', str(BOOT_START // SECTOR), '-n', 'BOOT', '-i', serial, path)
    validate_fat32(path)


def boot_inventory(boot):
    require(boot.is_dir() and not boot.is_symlink(), 'Boot files must be an ordinary directory')
    files, names = {}, set()
    for p in sorted(boot.rglob('*')):
        rel = p.relative_to(boot).as_posix()
        require(not p.is_symlink(), f'FAT input cannot contain symlinks: {rel}')
        require(p.is_file() or p.is_dir(), f'FAT input cannot contain special files: {rel}')
        require(all(0x20 <= ord(c) < 0x7F and c not in ':*?"<>|\\' for c in rel), f'Unsupported FAT name: {rel}')
        require(all(part == part.rstrip(' .') and len(part) <= 255 for part in Path(rel).parts), f'Unsupported FAT name: {rel}')
        require(rel.casefold() not in names, f'Case-insensitive FAT name collision: {rel}')
        names.add(rel.casefold())
        if p.is_file():
            require(p.stat().st_size < 2**32, f'File exceeds FAT32 limit: {rel}')
            files[rel] = {'bytes': p.stat().st_size, 'sha256': digest(p)}
    require(files and sum(v['bytes'] for v in files.values()) < BOOT_SIZE * 0.85, 'Missing boot files or FAT partition too small')
    return files


def boot_paths(text, root_uuid, inventory):
    """Validate every boot stanza, disallow includes and board-ambiguous FDTDIR."""
    entries, current = [], None
    for original in text.splitlines():
        line = original.strip()
        if not line or line.startswith('#'):
            continue
        tokens = line.split(None, 1)
        key = tokens[0].upper()
        value = tokens[1] if len(tokens) > 1 else ''
        require(key not in ('INCLUDE', 'CONFIG', 'FDTDIR', 'DEVICETREEDIR'), f'Unsupported extlinux directive: {key}')
        if key == 'LABEL':
            current = {}
            entries.append(current)
        elif key in ('LINUX', 'KERNEL', 'INITRD', 'FDT', 'DEVICETREE', 'APPEND'):
            require(current is not None, 'Boot directives must appear inside a LABEL stanza')
            key = {'KERNEL': 'LINUX', 'DEVICETREE': 'FDT'}.get(key, key)
            require(key not in current, f'Duplicate boot directive: {key}')
            current[key] = value
    require(entries, 'No extlinux LABEL stanzas')
    result = []
    for entry in entries:
        require(all(key in entry for key in ('LINUX', 'INITRD', 'FDT', 'APPEND')), 'Each extlinux stanza needs LINUX, INITRD, FDT, and APPEND')
        roots = [v for v in shlex.split(entry['APPEND']) if v.startswith('root=')]
        require(roots == ['root=PARTUUID=' + root_uuid], 'extlinux root PARTUUID does not match UUID file')
        paths = {}
        for key in ('LINUX', 'INITRD', 'FDT'):
            raw = entry[key]
            path = PurePosixPath(raw)
            require('..' not in path.parts and not any(c.isspace() for c in raw), f'Unsafe or multiple {key} path')
            # Relative names are relative to /extlinux, where this config lives.
            rel = str(path).lstrip('/') if path.is_absolute() else 'extlinux/' + str(path)
            require(rel in inventory, f'Boot reference is missing: {rel}')
            paths[key] = rel
        result.append(paths)
    return result


def validate_boot_sources(boot, inventory, values, tools):
    require('extlinux/extlinux.conf' in inventory, 'Missing extlinux/extlinux.conf')
    entries = boot_paths((boot / 'extlinux/extlinux.conf').read_text(), values['root_uuid'], inventory)
    for entry in entries:
        with (boot / entry['LINUX']).open('rb') as f:
            f.seek(56)
            require(f.read(4) == b'ARM\x64', 'LINUX must refer to an uncompressed ARM64 Linux Image')
        require(inventory[entry['INITRD']]['bytes'] > 0, 'Initramfs is empty')
        dtb = boot / entry['FDT']
        model = tools.run('fdtget', '-t', 's', dtb, '/', 'model').strip()
        compat = tools.run('fdtget', '-t', 's', dtb, '/', 'compatible').strip().split()
        require(model == 'Radxa ROCK 5T' and 'radxa,rock-5t' in compat and 'rockchip,rk3588' in compat,
                f'DTB is not ROCK5T: model={model!r}; compatible={compat!r}')
    return entries


def gpt_header(f, lba, total):
    f.seek(lba * SECTOR)
    raw = f.read(SECTOR)
    require(raw[:8] == b'EFI PART', f'Missing GPT header at LBA {lba}')
    revision, size, crc, reserved = struct.unpack_from('<IIII', raw, 8)
    require(revision == 0x10000 and size == 92 and reserved == 0, 'Unsupported GPT header')
    calc = bytearray(raw[:size])
    calc[16:20] = b'\0' * 4
    require(binascii.crc32(calc) & 0xFFFFFFFF == crc, 'GPT header CRC mismatch')
    current, backup, first, last = struct.unpack_from('<QQQQ', raw, 24)
    require(current == lba and backup == (total - 1 if lba == 1 else 1), 'GPT header locations invalid')
    table_lba, count, entry_size, table_crc = struct.unpack_from('<QIII', raw, 72)
    require(count == 128 and entry_size == 128, 'Unexpected GPT entry table shape')
    require(first == 34 and last == total - 34, 'Unexpected usable GPT bounds')
    require(table_lba == (2 if lba == 1 else total - 33), 'Unexpected GPT table location')
    f.seek(table_lba * SECTOR)
    table = f.read(count * entry_size)
    require(binascii.crc32(table) & 0xFFFFFFFF == table_crc, 'GPT partition array CRC mismatch')
    return {'uuid': str(uuid.UUID(bytes_le=raw[56:72])), 'table': table, 'first': first, 'last': last}


def validate_gpt(image, values, root_size):
    total = image.stat().st_size // SECTOR
    require(image.stat().st_size % SECTOR == 0, 'Disk is not sector-aligned')
    with image.open('rb') as f:
        mbr = f.read(SECTOR)
        require(mbr[510:512] == b'\x55\xaa' and mbr[450] == 0xEE, 'Invalid protective MBR')
        start, length = struct.unpack_from('<II', mbr, 454)
        require(start == 1 and length == min(total - 1, 0xFFFFFFFF), 'Protective MBR range is invalid')
        require(mbr[462:510] == bytes(48), 'Unexpected additional MBR entries')
        primary = gpt_header(f, 1, total)
        backup = gpt_header(f, total - 1, total)
    require(primary['uuid'] == backup['uuid'] == values['disk_uuid'], 'Disk UUID mismatch')
    require(primary['table'] == backup['table'], 'GPT primary/backup partition arrays differ')
    expected = [(EFI_TYPE, values['boot_uuid'], BOOT_START, BOOT_SIZE, 'BOOT'),
                (LINUX_TYPE, values['root_uuid'], ROOT_START, root_size, 'ROOT')]
    for i, (typ, identifier, offset, length, name) in enumerate(expected):
        entry = primary['table'][i * 128:(i + 1) * 128]
        first, last, attributes = struct.unpack_from('<QQQ', entry, 32)
        require(str(uuid.UUID(bytes_le=entry[:16])) == typ and str(uuid.UUID(bytes_le=entry[16:32])) == identifier,
                f'Partition {i + 1} type/UUID mismatch')
        require(first * SECTOR == offset and (last - first + 1) * SECTOR == length and attributes == 0,
                f'Partition {i + 1} geometry or attributes mismatch')
        require(entry[56:128].decode('utf-16-le').rstrip('\0') == name, 'Partition name mismatch')
        require(last <= primary['last'], 'Partition overlaps backup GPT')
    require(primary['table'][256:] == bytes(len(primary['table']) - 256), 'Unexpected extra GPT partitions')
    return {'primary_and_backup_crc': 'passed', 'backup_header_lba': total - 1, 'root_start_lba': ROOT_START // SECTOR}


def verify(image, manifest, tools, rootfs=None, boot_fat=None):
    regular(image, 'Disk image')
    require(manifest['schema'] == 1 and manifest['board'] == 'radxa,rock-5t', 'Wrong manifest schema/board')
    values = manifest['partition_ids']
    require(values == ids(values['seed']), 'Manifest UUIDs are inconsistent')
    require(image.stat().st_size == manifest['disk_bytes'], 'Disk image length mismatch')
    validate_gpt(image, values, manifest['root']['bytes'])
    tools.run('sgdisk', '--verify', image)
    loader = manifest['bootloader']
    require(loader['offset'] == LOADER_START and 0 < loader['bytes'] <= BOOT_START - LOADER_START, 'Invalid bootloader range')
    require(digest(image, LOADER_START, loader['bytes']) == loader['sha256'], 'Embedded bootloader SHA256 mismatch')
    require(digest(image, ROOT_START, manifest['root']['bytes']) == manifest['root']['sha256'], 'Embedded root SHA256 mismatch')
    require(digest(image, BOOT_START, BOOT_SIZE) == manifest['boot']['sha256'], 'Embedded FAT SHA256 mismatch')
    with tempfile.TemporaryDirectory(prefix='rock5t-verify-', dir=image.parent) as td:
        temporary = Path(td)
        if rootfs is None:
            rootfs = temporary / 'root.ext4'
            with rootfs.open('xb') as f:
                f.truncate(manifest['root']['bytes'])
            sparse_copy(image, rootfs, src_offset=ROOT_START, length=manifest['root']['bytes'])
        else:
            regular(rootfs, 'Source root image')
            require(digest(rootfs) == manifest['root']['sha256'], 'Source root differs from disk')
        ext4_info(rootfs)
        tools.run('e2fsck', '-f', '-n', rootfs)
        if boot_fat is None:
            boot_fat = temporary / 'boot.fat'
            with boot_fat.open('xb') as f:
                f.truncate(BOOT_SIZE)
            sparse_copy(image, boot_fat, src_offset=BOOT_START, length=BOOT_SIZE)
        else:
            require(digest(boot_fat) == manifest['boot']['sha256'], 'Source FAT differs from disk')
        validate_fat32(boot_fat)
        tools.run('fsck.fat', '-n', '-v', boot_fat)
        spec = str(image) + '@@' + str(BOOT_START)
        listing = tools.run('mdir', '-i', spec, '-/', '-b', '::/').splitlines()
        found = {line.removeprefix('::/').removeprefix('::') for line in listing if line and not line.endswith('/')}
        require(found == set(manifest['boot']['files']), f'FAT file listing mismatch: {found ^ set(manifest["boot"]["files"])}')
        for rel, data in manifest['boot']['files'].items():
            require(tools.hash_fat_file(spec, rel) == data['sha256'], f'FAT file SHA256 mismatch: {rel}')
        config = tools.run('mtype', '-i', spec, '::/extlinux/extlinux.conf', binary=True).decode()
        entries = boot_paths(config, values['root_uuid'], manifest['boot']['files'])
        for entry in entries:
            dtb = temporary / 'rock5t.dtb'
            dtb.write_bytes(tools.run('mtype', '-i', spec, '::/' + entry['FDT'], binary=True))
            model = tools.run('fdtget', '-t', 's', dtb, '/', 'model').strip()
            compat = tools.run('fdtget', '-t', 's', dtb, '/', 'compatible').split()
            require(model == 'Radxa ROCK 5T' and 'radxa,rock-5t' in compat and 'rockchip,rk3588' in compat, 'Embedded DTB identity mismatch')
    return {'status': 'passed', 'checks': ['GPT primary and backup CRC/geometry/UUIDs', 'protective MBR',
            'bootloader byte-for-byte SHA256 at 32 KiB', 'root partition byte-for-byte SHA256',
            'read-only forced e2fsck', 'FAT32 byte-for-byte SHA256 and read-only fsck.fat',
            'exact FAT file inventory and hashes', 'extlinux PARTUUID and referenced files', 'embedded ROCK5T DTB identity'],
            'hardware_tested': False}


def package(args):
    tools = Tools(args.tools)
    for name in ('sgdisk', 'mkfs.fat', 'fsck.fat', 'e2fsck', 'mcopy', 'mdir', 'mtype', 'fdtget', 'xz'):
        tools.executable(name)
    values = read_ids(args.ids)
    rootfs, boot, loader, output = [Path(p).absolute() for p in (args.rootfs, args.boot_dir, args.bootloader, args.output)]
    regular(rootfs, 'Root image')
    regular(loader, 'Bootloader')
    require(output.suffix == '.img', 'Output name must end in .img')
    require(output.parent.is_dir(), 'Output directory does not exist')
    destinations = [output, Path(str(output) + '.partial'), Path(str(output) + '.manifest.json'),
                    Path(str(output) + '.validation.json'), Path(str(output) + '.sha256'),
                    Path(str(output) + '.xz'), Path(str(output) + '.xz.partial'), Path(str(output) + '.xz.sha256')]
    require(not any(p.exists() for p in destinations), 'Refusing to overwrite an output/partial/sidecar')
    root_info = ext4_info(rootfs)
    require(root_info['bytes'] % MIB == 0, 'Root image must be a whole number of MiB')
    require(0 < loader.stat().st_size <= BOOT_START - LOADER_START, 'Bootloader overlaps FAT partition')
    with loader.open('rb') as f:
        require(f.read(4) == b'RKNS', 'Bootloader lacks expected Rockchip RKNS header')
    files = boot_inventory(boot)
    validate_boot_sources(boot, files, values, tools)
    partial = Path(str(output) + '.partial')
    total_bytes = math.ceil((ROOT_START + root_info['bytes'] + 34 * SECTOR) / MIB) * MIB
    with rootfs.open('rb') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = rootfs.stat()
        tools.run('e2fsck', '-f', '-n', rootfs)
        root_info['sha256'] = digest(rootfs)
        with tempfile.TemporaryDirectory(prefix='rock5t-package-', dir=output.parent) as td:
            fat = Path(td) / 'boot.fat'
            with fat.open('xb') as f:
                f.truncate(BOOT_SIZE)
            format_fat32(fat, values['boot_uuid'], tools)
            for p in sorted(boot.iterdir()):
                tools.run('mcopy', '-s', '-p', '-m', '-i', fat, p, '::/')
            tools.run('fsck.fat', '-n', '-v', fat)
            with partial.open('xb') as f:
                f.truncate(total_bytes)
            root_last = (ROOT_START + root_info['bytes']) // SECTOR - 1
            tools.run('sgdisk', '--clear', '--set-alignment=1', '--disk-guid=' + values['disk_uuid'],
                      f'--new=1:{BOOT_START // SECTOR}:{ROOT_START // SECTOR - 1}', '--typecode=1:ef00', '--change-name=1:BOOT', '--partition-guid=1:' + values['boot_uuid'],
                      f'--new=2:{ROOT_START // SECTOR}:{root_last}', '--typecode=2:8300', '--change-name=2:ROOT', '--partition-guid=2:' + values['root_uuid'], partial)
            sparse_copy(loader, partial, LOADER_START)
            sparse_copy(fat, partial, BOOT_START)
            sparse_copy(rootfs, partial, ROOT_START)
            after = rootfs.stat()
            require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Root image changed during packaging')
            manifest = {'schema': 1, 'board': 'radxa,rock-5t', 'disk_bytes': total_bytes, 'sector_bytes': SECTOR,
                        'partition_ids': values, 'root': root_info,
                        'bootloader': {'offset': LOADER_START, 'bytes': loader.stat().st_size, 'sha256': digest(loader)},
                        'boot': {'offset': BOOT_START, 'bytes': BOOT_SIZE, 'sha256': digest(fat), 'files': files}}
            manifest['validation'] = verify(partial, manifest, tools, rootfs=rootfs, boot_fat=fat)
            partial.rename(output)
    manifest['image_sha256'] = digest(output)
    Path(str(output) + '.sha256').write_text(f'{manifest["image_sha256"]}  {output.name}\n')
    if not args.no_compress:
        compressed = Path(str(output) + '.xz')
        work = Path(str(compressed) + '.partial')
        command = [tools.executable('xz'), '--threads=2', '--memlimit-compress=1024MiB', '-4', '--check=crc64', '--stdout', str(output)]
        with work.open('xb') as out:
            subprocess.run(command, env=tools.env, stdout=out, check=True)
        tools.run('xz', '--test', work)
        work.rename(compressed)
        manifest['compressed_sha256'] = digest(compressed)
        manifest['compressed_bytes'] = compressed.stat().st_size
        Path(str(compressed) + '.sha256').write_text(f'{manifest["compressed_sha256"]}  {compressed.name}\n')
    Path(str(output) + '.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    Path(str(output) + '.validation.json').write_text(json.dumps({'result': manifest['validation'], 'tool_results': tools.logs}, indent=2) + '\n')
    print(json.dumps({'image': str(output), 'bytes': total_bytes, 'manifest': str(output) + '.manifest.json', 'validation': manifest['validation']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make_ids = sub.add_parser('ids', help='Generate stable GPT UUIDs before preparing the root/boot files')
    make_ids.add_argument('--seed', required=True)
    make_ids.add_argument('--output', type=Path)
    build = sub.add_parser('package')
    build.add_argument('--rootfs', type=Path, required=True)
    build.add_argument('--boot-dir', type=Path, required=True)
    build.add_argument('--ids', type=Path, required=True)
    build.add_argument('--bootloader', type=Path, default=DEFAULT_LOADER)
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--tools', type=Path, default=DEFAULT_TOOLS)
    build.add_argument('--no-compress', action='store_true')
    check = sub.add_parser('verify')
    check.add_argument('--image', type=Path, required=True)
    check.add_argument('--manifest', type=Path, required=True)
    check.add_argument('--rootfs', type=Path, help='Optional unchanged source root; avoids temporary root extraction')
    check.add_argument('--tools', type=Path, default=DEFAULT_TOOLS)
    args = parser.parse_args()
    try:
        if args.command == 'ids':
            content = json.dumps(ids(args.seed), indent=2) + '\n'
            if args.output:
                with args.output.open('x') as f:
                    f.write(content)
            print(content, end='')
        elif args.command == 'package':
            package(args)
        else:
            manifest = json.loads(args.manifest.read_text())
            tools = Tools(args.tools)
            result = verify(args.image.absolute(), manifest, tools, args.rootfs.absolute() if args.rootfs else None)
            require(digest(args.image) == manifest['image_sha256'], 'Whole-image SHA256 mismatch')
            print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
