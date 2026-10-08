import unittest
from check_emmc import REQUIRED, check_config, check_dtb_properties
from inspect_emmc_target import collect, reject_reasons


class EmmcTests(unittest.TestCase):
    def setUp(self):
        self.props = {'model': 'Radxa ROCK 5T', 'board_compatible': 'radxa,rock-5t rockchip,rk3588',
                      'compatible': 'rockchip,rk3588-dwcmshc', 'status': 'okay', 'bus-width': '8',
                      'properties': ['non-removable', 'no-sd', 'no-sdio']}
        self.target = {'type': 'MMC', 'cid': 'synthetic-test-cid', 'logical_sector_bytes': 512,
                       'capacity_bytes': 16 * 1024**3, 'read_only': 0,
                       'mounted': [], 'swap': [], 'holders': []}
        self.config = '\n'.join(k + '=y' for k in REQUIRED) + '\nCONFIG_LSM="capability,landlock"\n'

    def test_good_kernel_config(self):
        self.assertEqual(check_config(self.config), list(REQUIRED))

    def test_missing_or_modular_root_driver(self):
        for key in REQUIRED:
            for replacement in (key + '=m', '# ' + key + ' is not set'):
                with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                    check_config(self.config.replace(key + '=y', replacement))

    def test_landlock_default_required(self):
        with self.assertRaises(ValueError):
            check_config(self.config.replace('capability,landlock', 'capability'))

    def test_good_emmc_dtb(self):
        self.assertEqual(check_dtb_properties(self.props), self.props)

    def test_wrong_or_disabled_dtb(self):
        for key, value in [('status', 'disabled'), ('bus-width', '4'), ('model', 'Radxa ROCK 5B'),
                           ('board_compatible', 'rockchip,rk3588'), ('compatible', 'snps,dw-mshc'),
                           ('properties', ['non-removable'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_dtb_properties(dict(self.props, **{key: value}))

    def test_target_capacity_exact_and_bigger(self):
        self.assertEqual(reject_reasons(self.target, self.target['capacity_bytes']), [])
        self.assertEqual(reject_reasons(self.target, 1024), [])

    def test_target_capacity_insufficient_or_invalid(self):
        for size in (0, -1, self.target['capacity_bytes'] + 512):
            with self.subTest(size=size):
                self.assertTrue(reject_reasons(self.target, size))

    def test_wrong_medium_geometry_identity_and_readonly(self):
        for key, value in [('type', 'SD'), ('type', 'USB'), ('logical_sector_bytes', 4096),
                           ('cid', ''), ('read_only', 1), ('read_only', None)]:
            with self.subTest(key=key, value=value):
                self.assertTrue(reject_reasons(dict(self.target, **{key: value}), 1024))

    def test_non_user_area_paths_rejected_without_device_access(self):
        for target in ('/dev/null', '/dev/mmcblk0p1', '/dev/mmcblk0boot0', '/dev/mmcblk0boot1', '/dev/mmcblk0rpmb', '/dev/mtd0'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                collect(target)

    def test_active_target_rejected(self):
        for key in ('mounted', 'swap', 'holders'):
            with self.subTest(key=key):
                self.assertTrue(reject_reasons(dict(self.target, **{key: ['synthetic-active-child']}), 1024))


if __name__ == '__main__':
    unittest.main()
