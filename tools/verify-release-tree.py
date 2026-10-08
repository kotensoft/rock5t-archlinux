#!/usr/bin/env python3
"""Audit a source-only checkout; optionally refresh its file checksum manifest."""
import argparse
import ast
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = ('.img', '.xz', '.gz', '.ext4', '.qcow2', '.iso', '.deb', '.pyc', '.log',
                      '.ko', '.dtb', '.dtbo', '.elf', '.bin', '.o', '.a', '.so', '.gpg',
                      '.kbx', '.key', '.pem', '.p12', '.pfx', '.sig', '.partial', '.part')
# RFC 5737 documentation examples and standard QEMU SLIRP are intentional fixtures.
ALLOWED_PRIVATE_IPS = {'10.0.2.2', '10.0.2.3', '10.0.2.15'}


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-manifest', action='store_true')
    a = p.parse_args()
    issues, files = [], []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if '.git' in rel.parts:
            continue
        if path.is_symlink():
            issues.append(str(rel) + ': symlink is not allowed in source snapshot')
            continue
        if not path.is_file() or str(rel) == 'SOURCE-SHA256SUMS':
            continue
        files.append((path, str(rel)))
        if path.stat().st_size > 5 * 1024 * 1024:
            issues.append(str(rel) + ': source file exceeds 5 MiB review limit')
        if path.name.endswith(FORBIDDEN_SUFFIXES) or path.name in ('.env', '.git-credentials', '.netrc'):
            issues.append(str(rel) + ': prohibited artifact or secret filename')
        raw = path.read_bytes()
        if b'\x00' in raw:
            issues.append(str(rel) + ': binary NUL byte')
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            issues.append(str(rel) + ': expected UTF-8 source text')
            continue
        for pattern, label in [
            (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE' + r' KEY-----', 'private-key material'),
            (r'gh[pousr]_[A-Za-z0-9]{30,}', 'GitHub credential'),
            (r'github_pat_[A-Za-z0-9_]{30,}', 'GitHub credential'),
            (r'AKIA[A-Z0-9]{16}', 'cloud access key'),
            (r'https?://[^\s/]+:[^\s/@]+@', 'credential-bearing URL'),
            (r'/(?:Users|workspace)/[^\s"\']+', 'host-specific path'),
            (r'libfile_[a-f0-9]{24,}', 'private file identifier'),
        ]:
            if re.search(pattern, text):
                issues.append(str(rel) + ': ' + label)
        # Only the explicitly documented test fixtures may contain synthetic home paths.
        if re.search(r'/home/[^\s"\']+', text) and not (str(rel).startswith('overlay-work/tests/') or str(rel) in ('tools/verify-release-tree.py', 'next-version/firstboot-vm-test/verify_guest.py')):
            issues.append(str(rel) + ': home-directory path requires review')
        for value in re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', text):
            try:
                ip = ipaddress.ip_address(value)
            except ValueError:
                continue
            is_rfc1918 = any(ip in network for network in map(ipaddress.ip_network,
                            ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
            if is_rfc1918 and value not in ALLOWED_PRIVATE_IPS:
                issues.append(str(rel) + ': unreviewed private network address')
        if path.suffix == '.py':
            try:
                ast.parse(text, filename=str(rel))
            except SyntaxError:
                issues.append(str(rel) + ': Python syntax error')
        if path.suffix == '.sh' or raw.startswith(b'#!/bin/bash') or raw.startswith(b'#!/usr/bin/env bash'):
            if subprocess.run(['bash', '-n', str(path)], capture_output=True).returncode:
                issues.append(str(rel) + ': shell syntax error')
    # This verifier's RFC1918 range definitions are review rules, not collected addresses.
    issues = [x for x in issues if x != 'tools/verify-release-tree.py: unreviewed private network address']
    digest_lines = ''.join(sha(path) + '  ' + rel + '\n'
                           for path, rel in files)
    manifest = ROOT / 'SOURCE-SHA256SUMS'
    if not issues and a.write_manifest:
        manifest.write_text(digest_lines)
    elif not manifest.exists() or manifest.read_text() != digest_lines:
        issues.append('SOURCE-SHA256SUMS: absent or differs; review then use --write-manifest')
    print(json.dumps({'files_checked': len(files), 'bytes_checked': sum(p.stat().st_size for p, _ in files),
                      'issues': issues, 'passed': not issues}, indent=2))
    raise SystemExit(bool(issues))

if __name__ == '__main__':
    main()
