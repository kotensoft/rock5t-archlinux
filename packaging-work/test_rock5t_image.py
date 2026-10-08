#!/usr/bin/env python3
"""Small offline tests. Integration uses a 64 MiB FAT and 32 MiB ext4 fixture."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

import rock5t_image as r


class UnitTests(unittest.TestCase):
    def test_ids_are_stable_and_variant_specific(self):
        self.assertEqual(r.ids('cli'), r.ids('cli'))
        self.assertNotEqual(r.ids('cli')['root_uuid'], r.ids('kde')['root_uuid'])
        self.assertEqual(len(set(r.ids('cli')[key] for key in ('disk_uuid', 'boot_uuid', 'root_uuid'))), 3)

    def test_copy_offsets_and_holes(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td) / 'source', Path(td) / 'target'
            with src.open('wb') as f:
                f.write(b'A' * 4096)
                f.seek(8 * r.MIB)
                f.write(b'B' * 4096)
                f.truncate(9 * r.MIB)
            with dst.open('wb') as f:
                f.write(b'guard' + bytes(4091))
                f.truncate(src.stat().st_size + 8192)
            r.sparse_copy(src, dst, dst_offset=4096)
            self.assertEqual(r.digest(src), r.digest(dst, 4096, src.stat().st_size))
            self.assertEqual(dst.read_bytes()[:5], b'guard')
            self.assertLess(dst.stat().st_blocks * 512, dst.stat().st_size // 2)
            extract = Path(td) / 'extract'
            with extract.open('wb') as f:
                f.truncate(src.stat().st_size)
            r.sparse_copy(dst, extract, src_offset=4096, length=src.stat().st_size)
            self.assertEqual(r.digest(src), r.digest(extract))

    def test_extlinux_fails_closed(self):
        identifier = r.ids('test')['root_uuid']
        inventory = {'Image': {}, 'initramfs': {}, 'dtbs/board.dtb': {}}
        config = f'LABEL Arch\n LINUX /Image\n INITRD /initramfs\n FDT /dtbs/board.dtb\n APPEND root=PARTUUID={identifier} rw\n'
        self.assertEqual(r.boot_paths(config, identifier, inventory)[0]['LINUX'], 'Image')
        for invalid in (config.replace(identifier, 'wrong'), config.replace('FDT ', 'FDTDIR '),
                        config + 'INCLUDE surprise\n', config.replace('/Image', '/../Image'),
                        config.replace('/Image', '/missing'), config.replace('INITRD /initramfs', '')):
            with self.assertRaises(ValueError):
                r.boot_paths(invalid, identifier, inventory)

    def test_reject_ambiguous_fat_names(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / 'Image').write_bytes(b'kernel')
            (directory / 'image').write_bytes(b'other')
            with self.assertRaises(ValueError):
                r.boot_inventory(directory)
            (directory / 'image').unlink()
            (directory / 'symlink').symlink_to('Image')
            with self.assertRaises(ValueError):
                r.boot_inventory(directory)


class IntegrationTests(unittest.TestCase):
    def test_production_fat_geometry_exact_size(self):
        tools = r.Tools(r.DEFAULT_TOOLS)
        with tempfile.TemporaryDirectory(prefix='fat-regression-', dir=Path(__file__).parent) as td:
            fat = Path(td) / 'boot.fat'
            # Use the production 1 GiB size: the small integration fixture did
            # not trigger mkfs.fat's default 63-sector track rounding.
            self.assertEqual(r.BOOT_SIZE, 1024 * r.MIB)
            with fat.open('wb') as f:
                f.truncate(r.BOOT_SIZE)
            tools.run('mkfs.fat', '--invariant', '-F', '32', '-S', str(r.SECTOR),
                      '-h', str(r.BOOT_START // r.SECTOR), '-n', 'BOOT', fat)
            with self.assertRaisesRegex(ValueError, 'FAT filesystem length mismatch'):
                r.validate_fat32(fat)
            r.format_fat32(fat, r.ids('fat-regression')['boot_uuid'], tools)
            with fat.open('rb') as f:
                header = f.read(r.SECTOR)
            self.assertEqual(struct.unpack_from('<I', header, 32)[0], 2097152)
            self.assertEqual(struct.unpack_from('<H', header, 24)[0], 32)
            tools.run('fsck.fat', '-n', '-v', fat)
            example = Path(td) / 'proof.txt'
            example.write_text('FAT32 production geometry is exact.\n')
            tools.run('mcopy', '-i', fat, example, '::/')
            self.assertEqual(tools.run('mtype', '-i', fat, '::/proof.txt'), example.read_text())
            tools.run('fsck.fat', '-n', '-v', fat)
            self.assertLess(fat.stat().st_blocks * 512, r.BOOT_SIZE // 8)

    def test_small_package_verify_and_corruption_detection(self):
        tools = r.Tools(r.DEFAULT_TOOLS)
        dtb_source = r.BASE / 'research/deb-root/usr/lib/linux-image-6.18.44-current-rockchip64/rockchip/rk3588-rock-5t.dtb'
        self.assertTrue(dtb_source.exists(), 'real ROCK5T DTB fixture missing')
        with tempfile.TemporaryDirectory(prefix='test-', dir=Path(__file__).parent) as td:
            directory = Path(td)
            root = directory / 'root.ext4'
            with root.open('wb') as f:
                f.truncate(32 * r.MIB)
            tools.run('mke2fs', '-t', 'ext4', '-F', '-L', 'ROOT', root)
            boot = directory / 'boot'
            (boot / 'extlinux').mkdir(parents=True)
            (boot / 'dtbs').mkdir()
            kernel = bytearray(128)
            kernel[56:60] = b'ARM\x64'
            (boot / 'Image').write_bytes(kernel)
            (boot / 'initramfs').write_bytes(b'test-initramfs-not-for-hardware')
            selected_dtb = boot / 'dtbs/board.dtb'
            shutil.copyfile(dtb_source, selected_dtb)
            values = r.ids('test-integration')
            ids_file = directory / 'ids.json'
            ids_file.write_text(json.dumps(values))
            (boot / 'extlinux/extlinux.conf').write_text(f'LABEL Arch\n LINUX /Image\n INITRD /initramfs\n FDT /dtbs/board.dtb\n APPEND root=PARTUUID={values["root_uuid"]} rw rootwait\n')
            # A generic board.dtb basename is allowed, but its board identity is not.
            files = r.boot_inventory(boot)
            for property_name, incorrect_value in (('model', 'Different board'),
                                                   ('compatible', 'rockchip,rk3588')):
                tools.run('fdtput', '-t', 's', selected_dtb, '/', property_name, incorrect_value)
                with self.assertRaisesRegex(ValueError, 'DTB is not ROCK5T'):
                    r.validate_boot_sources(boot, files, values, tools)
                shutil.copyfile(dtb_source, selected_dtb)
            output = directory / 'test.img'
            args = argparse.Namespace(tools=r.DEFAULT_TOOLS, ids=ids_file, rootfs=root, boot_dir=boot,
                                      bootloader=r.DEFAULT_LOADER, output=output, no_compress=False)
            # Production CLI constants remain fixed. Only this fixture is reduced.
            with patch.object(r, 'BOOT_SIZE', 64 * r.MIB), patch.object(r, 'ROOT_START', 80 * r.MIB):
                r.package(args)
                manifest = json.loads(Path(str(output) + '.manifest.json').read_text())
                self.assertEqual(r.verify(output, manifest, tools)['status'], 'passed')
                self.assertEqual(r.verify(output, manifest, tools, rootfs=root)['status'], 'passed')
                with lzma.open(Path(str(output) + '.xz'), 'rb') as f:
                    h = hashlib.sha256()
                    for data in iter(lambda: f.read(r.CHUNK), b''):
                        h.update(data)
                self.assertEqual(h.hexdigest(), manifest['image_sha256'])
                # Fail on damaged primary or backup GPT, then restore.
                for offset in (512 + 16, output.stat().st_size - 512 + 16):
                    with output.open('r+b') as f:
                        f.seek(offset)
                        original = f.read(1)
                        f.seek(offset)
                        f.write(bytes([original[0] ^ 0x80]))
                    with self.assertRaisesRegex(ValueError, 'CRC'):
                        r.validate_gpt(output, values, root.stat().st_size)
                    with output.open('r+b') as f:
                        f.seek(offset)
                        f.write(original)
                # Loader corruption must fail before filesystem tools run.
                with output.open('r+b') as f:
                    f.seek(r.LOADER_START)
                    f.write(b'BAD!')
                with self.assertRaisesRegex(ValueError, 'bootloader SHA256'):
                    r.verify(output, manifest, tools, rootfs=root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
