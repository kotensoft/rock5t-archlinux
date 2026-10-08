import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('gate', BASE / 'scripts/validate-next-kernel.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class KernelPackageGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BASE / 'next-version')
        self.root = Path(self.temp.name)
        self.release = '6.18.44-current-rockchip64-landlock1'
        (self.root / 'boot/dtbs/rockchip').mkdir(parents=True)
        (self.root / 'usr/lib/modules' / self.release).mkdir(parents=True)
        self.baseline = self.root / 'baseline'
        self.baseline.write_text('CONFIG_VIDEO_HANTRO=m\nCONFIG_RT_GROUP_SCHED=y\n')
        self.config = self.root / 'boot' / ('config-' + self.release)
        self.config.write_text(self.baseline.read_text() + 'CONFIG_SECURITY_LANDLOCK=y\nCONFIG_LSM="landlock,lockdown,yama,integrity,apparmor"\n')
        (self.root / 'boot/Image').write_bytes(bytes(56) + b'ARM\x64')
        (self.root / 'boot/dtbs/rockchip/rk3588-rock-5t.dtb').write_bytes(b'\xd0\x0d\xfe\xedradxa,rock-5t\0')
        (self.root / 'usr/lib/modules' / self.release / 'modules.builtin').write_text('fixture')
        self.prov = {'linux_commit': 'a' * 40, 'armbian_commit': 'b' * 40,
                     'patchset_hash': 'd9e569eab50e60b3', 'kernelrelease': self.release,
                     'baseline_config_sha256': 'df04c47ef19557272ed2a926f44ec2abea82fcffa334b484589bcbb54c9841a3'}
        self.write_prov()

    def tearDown(self):
        self.temp.cleanup()

    def write_prov(self):
        (self.root / 'provenance.json').write_text(json.dumps(self.prov))

    def check(self):
        return gate.validate(self.root, self.release, self.baseline)

    def test_complete_contract(self):
        self.assertEqual(self.check()['landlock_config'], 'enabled')

    def test_requires_compiled_and_default_lsm_landlock(self):
        for line in ['CONFIG_SECURITY_LANDLOCK=y\n', 'CONFIG_LSM="landlock,lockdown,yama,integrity,apparmor"\n']:
            original = self.config.read_text()
            self.config.write_text(original.replace(line, ''))
            with self.assertRaisesRegex(ValueError, 'Landlock'): self.check()
            self.config.write_text(original)

    def test_vpu_regression_rejected(self):
        self.config.write_text(self.config.read_text().replace('CONFIG_VIDEO_HANTRO=m', 'CONFIG_VIDEO_HANTRO=n'))
        with self.assertRaisesRegex(ValueError, 'regression'): self.check()

    def test_rt_semantics_regression_rejected(self):
        self.config.write_text(self.config.read_text().replace('CONFIG_RT_GROUP_SCHED=y', 'CONFIG_RT_GROUP_SCHED=n'))
        with self.assertRaisesRegex(ValueError, 'regression'): self.check()

    def test_provenance_full_commits_required(self):
        self.prov['armbian_commit'] = 'fd4ebfd1'
        self.write_prov()
        with self.assertRaisesRegex(ValueError, 'full provenance'): self.check()

    def test_reused_release_provenance_rejected(self):
        self.prov['kernelrelease'] = '6.18.44-current-rockchip64'
        self.write_prov()
        with self.assertRaisesRegex(ValueError, 'kernelrelease'): self.check()

    def test_missing_modules_rejected(self):
        (self.root / 'usr/lib/modules' / self.release / 'modules.builtin').unlink()
        with self.assertRaisesRegex(ValueError, 'module tree'): self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
