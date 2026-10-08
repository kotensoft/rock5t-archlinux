#!/usr/bin/env python3
"""Offline tests for the public-release source fetch/bundle helpers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fetch', TOOLS/'fetch-kernel-sources.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

class SourceHelpers(unittest.TestCase):
    def test_archive_verification_rejects_bad_hash_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'archive'
            p.write_bytes(b'fixture source')
            rec = {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertTrue(fetch.verify(p, rec))
            self.assertFalse(fetch.verify(p, dict(rec, bytes=0)))
            self.assertFalse(fetch.verify(p, dict(rec, sha256='0'*64)))
            link = Path(d)/'link'; link.symlink_to(p)
            self.assertFalse(fetch.verify(link, rec))

    def test_bundle_contains_only_manifest_and_locked_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); repo = root/'repo'; (repo/'tools').mkdir(parents=True)
            script = repo/'tools/make-kernel-source-bundle.py'
            script.write_bytes((TOOLS/script.name).read_bytes())
            source = root/'inputs'; source.mkdir()
            archive = source/'upstream.tar.gz'; archive.write_bytes(b'synthetic upstream bytes')
            (repo/'unlisted-secret-fixture').write_text('DO_NOT_COPY')
            lock = {'archive_inputs': [{'path': archive.name, 'bytes': archive.stat().st_size,
                                       'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}]}
            (repo/'sources.lock.json').write_text(json.dumps(lock))
            names = ['sources.lock.json', 'tools/'+script.name]
            (repo/'SOURCE-SHA256SUMS').write_text(''.join(hashlib.sha256((repo/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names))
            out = root/'sources.tar'
            command = [sys.executable, str(script), '--source-root', str(source), '--output', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with tarfile.open(out) as tf:
                self.assertEqual(set(tf.getnames()), {'rock5t-source/'+n for n in names} |
                    {'rock5t-source/SOURCE-SHA256SUMS', 'rock5t-source/upstream.tar.gz', 'BUNDLE-SHA256SUMS'})
                self.assertTrue(all(m.uid == 0 and m.gid == 0 for m in tf.getmembers()))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            (repo/'sources.lock.json').write_text('{}')
            command[-1] = str(root/'tampered.tar')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
