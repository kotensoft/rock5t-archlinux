#!/usr/bin/env python3
"""Offline release/delivery regression fixtures; none are hardware boot images."""
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import rock5t_image as image
import release_image as release

TOOLS = release.BASE / 'next-version/delivery-tools'
spec = importlib.util.spec_from_file_location('delivery', TOOLS / 'prepare_delivery.py')
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def cpio(entries):
    raw = bytearray()
    for index, (name, content, mode) in enumerate([*entries, ('TRAILER!!!', b'', 0)]):
        name = name.encode() + b'\0'
        fields = [index, mode, 0, 0, 1, 0, len(content), 0, 0, 0, 0, len(name), 0]
        raw.extend(b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + name)
        raw.extend(b'\0' * (-len(raw) % 4))
        raw.extend(content)
        raw.extend(b'\0' * (-len(raw) % 4))
    return bytes(raw)


def board_fixture(base, bad_hook=False, wrong_module=False):
    payload = base / 'payload'
    module_name = f'usr/lib/modules/{release.KERNEL}/{release.PHY}'
    module = payload / module_name
    module.parent.mkdir(parents=True)
    module.write_bytes(b'fixture-only-kernel-module')
    records = [(name, data, stat.S_IFREG | 0o644) for name, data in {
        'init': b'#!/bin/sh\nfixture-only', 'init_functions': b'fixture-only',
        'hooks/udev': b'fixture-only', 'config': b'fixture-only',
        'buildconfig': b'HOOKS=(base udev modconf block filesystems fsck)\n',
        f'usr/lib/modules/{release.KERNEL}/modules.dep.bin': b'fixture-only-depmod',
        module_name: module.read_bytes(),
    }.items()]
    records[0] = (records[0][0], records[0][1], stat.S_IFREG | 0o755)
    if bad_hook:
        records = [(n, d.replace(b'base udev', b'base autodetect udev') if n == 'buildconfig' else d, m) for n, d, m in records]
    if wrong_module:
        records = [(n, b'tampered' if n == module_name else d, m) for n, d, m in records]
    return payload, records


class ReleaseTests(unittest.TestCase):
    def test_versioned_paths_and_ids_do_not_collide(self):
        prior = set()
        for variant in ('cli', 'kde'):
            ids_path, output = release.release_paths(variant)
            self.assertEqual(image.read_ids(ids_path), release.expected_ids(variant))
            self.assertEqual(output.parent, release.BASE / 'output' / release.VERSION)
            self.assertIn(release.VERSION, output.name)
            for values in (image.read_ids(ids_path), image.read_ids(release.BASE / 'packaging-work' / f'{variant}.ids.json')):
                current = set(values[k] for k in ('disk_uuid', 'boot_uuid', 'root_uuid'))
                self.assertEqual(len(current), 3)
                self.assertFalse(prior & current)
                prior.update(current)
        for bad in ('../old', '2026/10/08', '2026.10.08-../evil', ''):
            with self.assertRaises(ValueError):
                release.release_paths('cli', bad)

    def test_cpio_rejects_unsafe_truncated_and_duplicate_files(self):
        for blob in (b'070701', cpio([('../oops', b'bad', stat.S_IFREG | 0o644)]),
                     cpio([('init', b'a', stat.S_IFREG | 0o644), ('init', b'b', stat.S_IFREG | 0o644)])):
            with self.assertRaises(ValueError):
                release.decode_newc(blob)
        files, _ = release.decode_newc(cpio([('init', b'test', stat.S_IFREG | 0o755)]))
        self.assertEqual(files['init']['data'], b'test')

    def test_board_initramfs_gate_uncompressed_and_zstd(self):
        tools = image.Tools(image.DEFAULT_TOOLS)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            base = Path(td)
            payload, records = board_fixture(base)
            uncompressed = base / 'initramfs'
            uncompressed.write_bytes(cpio(records))
            result = release.validate_initramfs(uncompressed, release.KERNEL, payload, tools)
            self.assertEqual(result['matching_payload_modules'], 1)
            self.assertFalse(result['hardware_boot_tested'])
            # Normal mkinitcpio early archive repeats an identical usr/sbin symlink.
            link = ('usr/sbin', b'bin', stat.S_IFLNK | 0o777)
            raw = base / 'body'
            raw.write_bytes(cpio([link, *records]))
            compressed = tools.run('zstd', '-q', '-c', raw, binary=True)
            uncompressed.write_bytes(cpio([link]) + b'\0' * 40 + compressed)
            self.assertEqual(release.validate_initramfs(uncompressed, release.KERNEL, payload, tools)['matching_payload_modules'], 1)
            with patch.object(release, 'MAX_INITRAMFS', uncompressed.stat().st_size + 1):
                # Compressed input fits, decompressed body exceeds the limit.
                with self.assertRaisesRegex(ValueError, 'oversized'):
                    release.inspect_initramfs(uncompressed, tools)

    def test_module_directory_roots_allow_trailing_slash_but_reject_wrong_release(self):
        tools = image.Tools(image.DEFAULT_TOOLS)
        for name, mode, accepted in (
            ('usr/lib/modules/', stat.S_IFDIR | 0o755, True),
            ('usr/lib/modules', stat.S_IFDIR | 0o755, True),
            (f'usr/lib/modules/{release.KERNEL}/', stat.S_IFDIR | 0o755, True),
            ('usr/lib/modules/wrongrelease/', stat.S_IFDIR | 0o755, False),
            ('usr/lib/modules//wrongrelease/', stat.S_IFDIR | 0o755, False),
            ('usr/lib/modules/', stat.S_IFREG | 0o644, False),
            ('usr/lib/modules/../unsafe', stat.S_IFDIR | 0o755, False),
            ('/usr/lib/modules/', stat.S_IFDIR | 0o755, False),
        ):
            with self.subTest(name=name, mode=mode), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
                base = Path(td)
                payload, records = board_fixture(base)
                initramfs = base / 'initramfs'
                initramfs.write_bytes(cpio([(name, b'', mode), *records]))
                if accepted:
                    result = release.validate_initramfs(initramfs, release.KERNEL, payload, tools)
                    self.assertEqual(result['matching_payload_modules'], 1)
                else:
                    with self.assertRaises(ValueError):
                        release.validate_initramfs(initramfs, release.KERNEL, payload, tools)

    def test_board_gate_rejects_qemu_hooks_wrong_release_and_module(self):
        tools = image.Tools(image.DEFAULT_TOOLS)
        for change in ('hook', 'module', 'wrong-release', 'missing-phy'):
            with self.subTest(change=change), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
                base = Path(td)
                payload, records = board_fixture(base, change == 'hook', change == 'module')
                if change == 'wrong-release':
                    records = [(n.replace(release.KERNEL, 'qemu-other'), d, m) for n, d, m in records]
                if change == 'missing-phy':
                    records = [(n, d, m) for n, d, m in records if not n.endswith(release.PHY)]
                initramfs = base / 'initramfs'
                initramfs.write_bytes(cpio(records))
                with self.assertRaises(ValueError):
                    release.validate_initramfs(initramfs, release.KERNEL, payload, tools)

    def test_compressed_roundtrip_matches_raw_and_detects_wrong_hash(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            path = Path(td) / 'fixture.img.xz'
            raw = b'fixture-only-not-a-disk' * 100
            path.write_bytes(lzma.compress(raw))
            self.assertEqual(release.verify_compressed(path, hashlib.sha256(raw).hexdigest()), hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError, 'raw image SHA256'):
                release.verify_compressed(path, '0' * 64)

    def test_preflight_reads_offline_ext4_and_rejects_stale_fstab(self):
        tools = image.Tools(image.DEFAULT_TOOLS)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            base = Path(td)
            payload, records = board_fixture(base)
            kernel = payload / 'boot/Image'
            kernel.parent.mkdir(parents=True)
            shutil.copyfile(release.PAYLOAD / 'boot/Image', kernel)
            dtb = payload / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb'
            dtb.parent.mkdir(parents=True)
            shutil.copyfile(release.PAYLOAD / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb', dtb)
            shutil.copyfile(release.PAYLOAD / 'boot' / ('config-' + release.KERNEL),
                            payload / 'boot' / ('config-' + release.KERNEL))
            boot = base / 'boot'
            generation_dir = boot / 'rock5t' / release.KERNEL
            generation_dir.mkdir(parents=True)
            shutil.copyfile(kernel, generation_dir / 'Image')
            shutil.copyfile(dtb, generation_dir / 'board.dtb')
            (generation_dir / 'initramfs.img').write_bytes(cpio(records))
            (generation_dir / 'generation.json').write_text(json.dumps({
                'release': release.KERNEL,
                'boot_files': {n: image.digest(generation_dir / n) for n in ('Image', 'board.dtb', 'initramfs.img')},
            }))
            ids = release.expected_ids('cli')
            cmdline = f"root=PARTUUID={ids['root_uuid']} rw rootwait rt_group_sched=0"
            (boot / 'extlinux').mkdir()
            (boot / 'extlinux/extlinux.conf').write_text(
                f'LABEL rock5t\n LINUX /rock5t/{release.KERNEL}/Image\n INITRD /rock5t/{release.KERNEL}/initramfs.img\n'
                f' FDT /rock5t/{release.KERNEL}/board.dtb\n APPEND {cmdline}\n')
            root = base / 'fixture.ext4'
            with root.open('wb') as f:
                f.truncate(32 * image.MIB)
            tools.run('mke2fs', '-t', 'ext4', '-F', '-U', ids['root_uuid'], root)
            tools.run('debugfs', '-w', '-R', 'mkdir /etc', root)
            tools.run('debugfs', '-w', '-R', 'mkdir /etc/rock5t', root)
            for name, content in {
                '/etc/fstab': f"PARTUUID={ids['root_uuid']} / ext4 defaults 0 1\nPARTUUID={ids['boot_uuid']} /boot vfat defaults 0 2\n",
                '/etc/rock5t/kernel.json': json.dumps({'cmdline': cmdline}),
                '/etc/rock5t/variant': 'cli\n',
            }.items():
                local = base / Path(name).name
                local.write_text(content)
                tools.run('debugfs', '-w', '-R', f'write {local} {name}', root)
            result = release.preflight(root, boot, 'cli', release.VERSION, payload, tools)
            self.assertEqual(result['status'], 'passed')
            self.assertFalse(result['hardware_tested'])
            stale = base / 'fstab'
            stale.write_text('PARTUUID=old-root / ext4 defaults 0 1\n')
            tools.run('debugfs', '-w', '-R', 'rm /etc/fstab', root)
            tools.run('debugfs', '-w', '-R', f'write {stale} /etc/fstab', root)
            with self.assertRaisesRegex(ValueError, 'fstab partition identity'):
                release.preflight(root, boot, 'cli', release.VERSION, payload, tools)

    def test_actual_old_initramfs_parsing_and_module_hashes(self):
        # Read-only regression against existing artifacts, no old-image changes.
        kernel = '6.18.44-current-rockchip64'
        old = release.BASE / 'boot-cli/rock5t' / kernel / 'initramfs.img'
        if not old.exists():
            self.skipTest('Existing old board initramfs unavailable')
        files = release.inspect_initramfs(old, image.Tools(image.DEFAULT_TOOLS))
        modules = [n for n in files if n.endswith('.ko')]
        self.assertGreater(len(modules), 1)
        self.assertIn(f'usr/lib/modules/{kernel}/{release.PHY}', files)
        for name in modules:
            source = release.BASE / 'research/deb-root' / name.removeprefix('usr/')
            self.assertEqual(hashlib.sha256(files[name]['data']).hexdigest(), image.digest(source))


class DeliveryTests(unittest.TestCase):
    def test_export_json_redacts_nested_build_paths_without_changing_evidence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            base = Path(td).resolve()
            build_root = base / 'private-build-root'
            digest = 'abcdef0123456789' * 4
            original = {
                'schema': 1, 'status': 'passed', 'hardware_tested': False,
                'image_sha256': digest, 'disk_bytes': 5386534912,
                'tool_results': [{'command': f'{build_root}/host-tools/usr/bin/check {build_root}/vm/root.ext4',
                                  'stdout': f'checked {build_root}/output/temporary/image: clean\n',
                                  'returncode': 0}],
                'nested': [str(build_root), {'path': str(build_root / 'boot/Image'),
                                             'device_path': '/usr/lib/modules/kernel/test.ko',
                                             'prefix_lookalike': str(build_root) + '-other/file'}],
                str(build_root / 'path-key'): {'sha256': digest},
            }
            source = base / 'original.json'
            source.write_text(json.dumps(original, separators=(',', ':')) + '\n')
            source_bytes = source.read_bytes()
            destination = base / 'export.json'
            delivery.export_json_report(source, destination, build_root)
            exported = json.loads(destination.read_text())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(original['image_sha256'], exported['image_sha256'])
            self.assertEqual(original['disk_bytes'], exported['disk_bytes'])
            self.assertEqual(original['hardware_tested'], exported['hardware_tested'])
            self.assertEqual(exported['tool_results'][0]['returncode'], 0)
            self.assertEqual(exported['tool_results'][0]['command'], '$BUILD_ROOT/host-tools/usr/bin/check $BUILD_ROOT/vm/root.ext4')
            self.assertEqual(exported['tool_results'][0]['stdout'], 'checked $BUILD_ROOT/output/temporary/image: clean\n')
            self.assertEqual(exported['nested'][0], '$BUILD_ROOT')
            self.assertEqual(exported['nested'][1]['device_path'], '/usr/lib/modules/kernel/test.ko')
            self.assertEqual(exported['nested'][1]['prefix_lookalike'], str(build_root) + '-other/file')
            self.assertEqual(exported['$BUILD_ROOT/path-key']['sha256'], digest)
            self.assertEqual(delivery.redact_build_paths(original, build_root), exported)
            self.assertEqual(original['nested'][0], str(build_root))
            with self.assertRaises(FileExistsError):
                delivery.export_json_report(source, destination, build_root)

    def prepare_fixture(self, base):
        raw = b'tiny merge fixture, never a hardware disk\n' * 4096
        source = base / 'archlinux-rock5t-cli-test.img.xz'
        source.write_bytes(lzma.compress(raw))
        out = base / 'delivery'; out.mkdir()
        info = delivery.split_file(source, out, part_bytes=64)
        self.assertGreater(len(info['parts']), 1)
        (out / (source.name + '.parts.sha256')).write_text(''.join(f'{p["sha256"]}  {p["name"]}\n' for p in info['parts']))
        (out / (source.name + '.sha256')).write_text(f'{info["sha256"]}  {source.name}\n')
        (out / (source.name.removesuffix('.xz') + '.sha256')).write_text(f'{hashlib.sha256(raw).hexdigest()}  {source.name.removesuffix(".xz")}\n')
        for name in ('merge.sh', 'verify.sh'):
            shutil.copyfile(TOOLS / name, out / name)
        return source, out, info, raw

    def test_split_reassembly_hash_and_retained_source(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            source, out, info, raw = self.prepare_fixture(Path(td))
            original_hash = image.digest(source)
            self.assertTrue(all(p['bytes'] <= 64 for p in info['parts']))
            result = subprocess.run(['bash', out / 'merge.sh'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(image.digest(out / source.name), original_hash)
            self.assertEqual(image.digest(source), original_hash)
            (out / source.name.removesuffix('.xz')).write_bytes(raw)
            result = subprocess.run(['bash', out / 'verify.sh'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Verified 2 full image', result.stdout)
            result = subprocess.run(['bash', out / 'merge.sh'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('nothing overwritten', result.stderr)

    def test_missing_and_corrupt_part_fail_before_output(self):
        for corruption in ('missing', 'corrupt', 'extra-record'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
                source, out, info, _ = self.prepare_fixture(Path(td))
                part = out / info['parts'][0]['name']
                if corruption == 'missing':
                    part.unlink()
                elif corruption == 'corrupt':
                    part.write_bytes(b'corrupt')
                else:
                    with (out / (source.name + '.parts.sha256')).open('a') as f:
                        f.write('0' * 64 + '  ../../elsewhere\n')
                result = subprocess.run(['bash', out / 'merge.sh'], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((out / source.name).exists())
                self.assertFalse((out / (source.name + '.partial')).exists())

    def test_split_refuses_nonempty_directory_and_oversized_parts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as td:
            source, out, _, _ = self.prepare_fixture(Path(td))
            with self.assertRaisesRegex(ValueError, 'empty'):
                delivery.split_file(source, out)
            empty = Path(td) / 'empty'; empty.mkdir()
            with self.assertRaisesRegex(ValueError, '<=90 MiB'):
                delivery.split_file(source, empty, delivery.MAX_PART_BYTES + 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
