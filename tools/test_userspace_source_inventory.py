#!/usr/bin/env python3
"""Read-only inventory tests using small synthetic tar metadata fixtures."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('inventory-userspace-sources.py')
spec = importlib.util.spec_from_file_location('inventory', SCRIPT)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def package(directory, version='1.2-3', buildversion=None):
    path = directory/('fixture-'+version+'-any.pkg.tar.xz')
    pkg = f'pkgname = fixture\npkgbase = fixture-base\npkgver = {version}\narch = any\nlicense = GPL-2.0-only\nurl = https://example.org/\npackager = PRIVATE_PERSON_FIXTURE\n'
    build = f'pkgname = fixture\npkgbase = fixture-base\npkgver = {buildversion or version}\npkgarch = any\npkgbuild_sha256sum = '+ 'a'*64 +'\nbuilddir = PRIVATE_BUILD_PATH\nstartdir = PRIVATE_START_PATH\ninstalled = PRIVATE_BUILD_DEPENDENCY\n'
    with tarfile.open(path, 'w:xz') as tf:
        for name, data in [('.BUILDINFO', build), ('.PKGINFO', pkg)]:
            info = tarfile.TarInfo(name); raw = data.encode(); info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
    return path

class InventoryTests(unittest.TestCase):
    def test_metadata_allowlist_excludes_build_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = package(Path(tmp)); row = subject.inspect_package(p)
            self.assertEqual(row['metadata_status'], 'exact_cached_package')
            self.assertEqual(row['pkgbase'], 'fixture-base')
            self.assertEqual(row['pkgbuild_sha256_expected'], 'a'*64)
            self.assertEqual(row['source_status'], 'not_collected_or_verified')
            self.assertEqual(row['license_review'], 'source_license_declared')
            self.assertNotIn('PRIVATE_', json.dumps(row))

    def test_buildinfo_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = subject.inspect_package(package(Path(tmp), buildversion='9.9-1'))
            self.assertEqual(row['metadata_status'], 'read_error')

    def test_exact_version_and_missing_package_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cache = root/'cache'; cache.mkdir()
            package(cache, '1.2-3'); package(cache, '1.3-1')
            package_list = root/'installed.txt'; package_list.write_text('fixture 1.2-3\nmissing 4.0-1\n')
            output = root/'inventory.json'
            command = [sys.executable, str(SCRIPT), '--cache', str(cache), '--variant', 'cli='+str(package_list),
                       '--stage', 'final', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.read_text())
            self.assertEqual(data['summary']['packages_selected'], 2)
            self.assertEqual(data['summary']['source_recipe_groups'], 2)
            self.assertEqual(data['summary']['exact_binary_package_metadata_missing'], 1)
            self.assertEqual(data['summary']['verified_complete_userspace_source_sets'], 0)
            self.assertEqual(data['packages'][0]['version'], '1.2-3')
            self.assertNotIn('PRIVATE_', output.read_text())
            self.assertNotIn(str(root), output.read_text())

    def test_repository_fallback_never_claims_binary_BUILDINFO(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root/'core.db'
            content = '%NAME%\nfixture\n\n%BASE%\nfixture-base\n\n%VERSION%\n1.2-3\n\n%LICENSE%\nLGPL-2.1-or-later\n\n%PACKAGER%\nPRIVATE_PERSON_FIXTURE\n'
            with tarfile.open(db, 'w:gz') as tf:
                raw = content.encode(); info = tarfile.TarInfo('fixture-1.2-3/desc'); info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))
            row = subject.repository_metadata(db)[('fixture', '1.2-3')]
            self.assertEqual(row['metadata_status'], 'exact_repository_index_only')
            self.assertFalse(row['buildinfo_present'])
            self.assertIsNone(row['pkgbuild_sha256_expected'])
            self.assertNotIn('PRIVATE_', json.dumps(row))

    def test_source_route_evidence_hash_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); material = root/'source-fixture'; material.write_bytes(b'fixture source')
            evidence = root/'evidence.json'
            data = {'schema_version': 1, 'entries': [{'pkgbase': 'fixture', 'version': '1.2-3',
                    'actual_materials_obtained': [{'file_basename': material.name,
                        'bytes': material.stat().st_size, 'sha256': subject.sha(material)}],
                    'actual_material_gaps': ['more files'], 'provenance_gaps': ['not established']}]}
            evidence.write_text(json.dumps(data))
            self.assertIn(('fixture', '1.2-3'), subject.route_evidence(evidence))
            material.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                subject.route_evidence(evidence)

    def test_package_list_rejects_extra_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'packages.txt'; path.write_text('fixture 1.2-3 extra\n')
            with self.assertRaises(ValueError):
                subject.load_package_list(path)

if __name__ == '__main__':
    unittest.main(verbosity=2)
