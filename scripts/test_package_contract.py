#!/usr/bin/env python3
"""Safe package completeness regressions; no host installs, mounts or services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import package_contract as contract

BASE = Path(__file__).resolve().parents[1]
EVIDENCE = BASE / 'evidence' if (BASE / 'evidence').is_dir() else BASE / 'release-repo/evidence'


def fixture(root, variant='cli', profiles=BASE / 'profiles'):
    packages = {name: '1.0-1' for name in contract.required_packages(profiles, variant)}
    packages['pipewire'] = '1:1.6.9-1'  # Exercise the epoch-bearing local DB directory.
    manifest = ''.join(name + ' ' + version + '\n' for name, version in sorted(packages.items()))
    for name, version in packages.items():
        path = root / 'var/lib/pacman/local' / (name + '-' + version) / 'desc'
        path.parent.mkdir(parents=True)
        path.write_text('%NAME%\n' + name + '\n\n%VERSION%\n' + version + '\n\n')
    for filename in contract.PAYLOAD_FILES:
        path = root / filename.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture, not an installed executable\n')
    path = root / 'usr/share/rock5t-build/packages.txt'
    path.parent.mkdir(parents=True)
    path.write_text(manifest)
    return manifest


class PackageContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, variant='kde'):
        return contract.validate_root(self.root, variant, BASE / 'profiles',
                                      self.root / 'usr/share/rock5t-build/packages.txt')

    def test_both_profiles_require_all_common_packages(self):
        for variant in ('cli', 'kde'):
            self.assertTrue(contract.REQUIRED_COMMON <= contract.required_packages(BASE / 'profiles', variant))

    def test_missing_source_requirement_fails_closed(self):
        profiles = self.root / 'profiles'
        shutil.copytree(BASE / 'profiles', profiles)
        for name in sorted(contract.REQUIRED_COMMON):
            with self.subTest(package=name):
                original = (BASE / 'profiles/cli.packages').read_text()
                (profiles / 'cli.packages').write_text(original.replace(name + '\n', ''))
                with self.assertRaisesRegex(ValueError, 'absent from profile'):
                    contract.required_packages(profiles, 'kde')

    def test_valid_cli_and_kde_with_epoch_package(self):
        for variant in ('cli', 'kde'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture(root, variant)
                result = contract.validate_root(root, variant, BASE / 'profiles', root / 'usr/share/rock5t-build/packages.txt')
                self.assertEqual(result['status'], 'passed')
                self.assertTrue(result['package_database_verified'])
                if variant == 'kde':
                    self.assertEqual(result['required_versions']['pipewire'], '1:1.6.9-1')

    def test_each_omitted_package_rejected_in_both_variants(self):
        for variant in ('cli', 'kde'):
            for name in sorted(contract.REQUIRED_COMMON):
                with self.subTest(variant=variant, package=name), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    text = fixture(root, variant)
                    manifest = root / 'usr/share/rock5t-build/packages.txt'
                    manifest.write_text(''.join(line + '\n' for line in text.splitlines() if not line.startswith(name + ' ')))
                    with self.assertRaisesRegex(ValueError, 'Missing required packages: ' + name):
                        contract.validate_root(root, variant, BASE / 'profiles', manifest)

    def test_base_package_required_in_kde(self):
        text = fixture(self.root, 'kde')
        manifest = self.root / 'usr/share/rock5t-build/packages.txt'
        manifest.write_text(text.replace('cloud-guest-utils 1.0-1\n', ''))
        with self.assertRaisesRegex(ValueError, 'Missing required packages: cloud-guest-utils'):
            self.validate()

    def test_forged_manifest_missing_database_fails(self):
        fixture(self.root, 'kde')
        (self.root / 'var/lib/pacman/local/rtkit-1.0-1/desc').unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

    def test_wrong_database_name_or_version_fails(self):
        fixture(self.root, 'kde')
        desc = self.root / 'var/lib/pacman/local/rtkit-1.0-1/desc'
        for content in ('%NAME%\nwrong\n\n%VERSION%\n1.0-1\n', '%NAME%\nrtkit\n\n%VERSION%\n2.0-1\n'):
            desc.write_text(content)
            with self.assertRaisesRegex(ValueError, 'database disagrees'):
                self.validate()

    def test_missing_or_empty_required_payload_fails(self):
        fixture(self.root, 'kde')
        for filename in contract.PAYLOAD_FILES:
            with self.subTest(path=filename):
                path = self.root / filename.lstrip('/')
                path.write_bytes(b'')
                with self.assertRaisesRegex(ValueError, 'payload missing or empty'):
                    self.validate()
                path.unlink()
                with self.assertRaisesRegex(ValueError, 'payload missing or empty'):
                    self.validate()
                path.write_text('restored fixture')

    def test_malformed_duplicate_or_path_injection_manifest_fails(self):
        for text in ('', 'rtkit\n', '../rtkit 1.0-1\n', 'rtkit ../../etc\n', 'rtkit 1\nrtkit 1\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                contract.parse_manifest(text)

    def test_historical_released_manifests_rejected(self):
        for variant in ('cli', 'kde'):
            text = (EVIDENCE / ('packages-' + variant + '-final.txt')).read_text()
            self.assertFalse(contract.REQUIRED_COMMON & contract.parse_manifest(text).keys())
            with self.assertRaisesRegex(ValueError, 'Missing required packages: iw, rtkit, wireless-regdb'):
                contract.validate_packages(text, variant, BASE / 'profiles',
                                           lambda path: self.fail('must reject manifest before DB reads'),
                                           lambda path: self.fail('must reject manifest before payload reads'))

    def test_install_gate_and_all_image_gates_reference_contract(self):
        for name in ('finalize-target.sh', 'next-finish-kde-root.sh'):
            self.assertIn('package_contract.py --root', (BASE / 'scripts' / name).read_text())
        self.assertIn('validate_root(r,variant', (BASE / 'scripts/qa-next-roots.py').read_text())
        source = (BASE / 'packaging-work/release_image.py').read_text()
        self.assertIn('packages = validate_image_packages(rootfs, variant, tools)', source)
        self.assertIn("'package_contract': packages", source)
        for path in ('verify_guest.py', 'kde-smoke/verify_guest.py'):
            source = (BASE / 'next-version/firstboot-vm-test' / path).read_text()
            self.assertIn("for package in ('rtkit', 'wireless-regdb', 'iw')", source)
            self.assertIn("checks['rtkit_dbus_activation']", source)

    def test_install_gate_common_packages_and_failed_query(self):
        profiles = self.root / 'profiles'
        shutil.copytree(BASE / 'profiles', profiles)
        cmdline = self.root / 'cmdline'
        cmdline.write_text('rock5t.builder=1\n')
        source = (BASE / 'scripts/profile-packages.sh').read_text().replace('/proc/cmdline', str(cmdline)).replace('/mnt/host/profiles', str(profiles))
        script = self.root / 'install.sh'
        script.write_text(source + '\ninstall_profile "$1"\n')
        mock = self.root / 'pacman'
        mock.write_text('#!' + sys.executable + '\nimport json,os,sys\nwith open(os.environ["CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\nif sys.argv[1]=="-Qq": sys.exit(1)\nif sys.argv[1]=="-Q" and os.environ.get("FAIL_QUERY"): sys.exit(1)\n')
        mock.chmod(0o755)
        calls = self.root / 'calls'
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'], CALLS=str(calls))
        for variant in ('cli', 'kde'):
            calls.write_text('')
            result = subprocess.run(['bash', str(script), variant], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = [json.loads(line) for line in calls.read_text().splitlines()]
            for flag in ('-S', '-Q'):
                selected = next(command for command in commands if command[0] == flag)
                self.assertTrue(contract.required_packages(profiles, variant) <= set(selected))
            result = subprocess.run(['bash', str(script), variant], env=dict(env, FAIL_QUERY='1'), capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        (profiles / 'cli.packages').write_text((profiles / 'cli.packages').read_text().replace('rtkit\n', ''))
        calls.write_text('')
        result = subprocess.run(['bash', str(script), 'kde'], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.read_text(), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
