#!/usr/bin/env python3
"""Package complete pinned kernel/boot-stack sources plus audited build sources, outside Git."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

REPO = Path(__file__).resolve().parents[1]
EPOCH = 1787027546

def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, default=REPO)
    p.add_argument('--output', type=Path, required=True, help='new .tar path outside this repository')
    a = p.parse_args()
    out = a.output.resolve()
    if out.is_relative_to(REPO) or out.exists() or out.suffix != '.tar':
        raise SystemExit('Choose a new .tar filename outside the repository')
    root = a.source_root.resolve()
    entries = []
    for line in (REPO / 'SOURCE-SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = REPO / name
        if not path.resolve().is_relative_to(REPO) or path.is_symlink() or sha(path) != expected:
            raise SystemExit('Source-tree manifest mismatch: ' + name)
        entries.append((path, 'rock5t-source/' + name))
    entries.append((REPO / 'SOURCE-SHA256SUMS', 'rock5t-source/SOURCE-SHA256SUMS'))
    for item in json.loads((REPO / 'sources.lock.json').read_text())['archive_inputs']:
        path = root / item['path']
        if (not path.resolve().is_relative_to(root) or path.is_symlink()
                or not path.is_file() or path.stat().st_size != item['bytes'] or sha(path) != item['sha256']):
            raise SystemExit('Pinned archive mismatch: ' + item['path'])
        entries.append((path, 'rock5t-source/' + item['path']))
    # No filesystem walk: only manifest-listed repository text and pinned source archives.
    checksums = ''.join(sha(path) + '  ' + name + '\n' for path, name in entries)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as handle, tarfile.open(fileobj=handle, mode='w') as tf:
        for path, name in entries:
            info = tf.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = EPOCH
            info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            with path.open('rb') as src:
                tf.addfile(info, src)
        info = tarfile.TarInfo('BUNDLE-SHA256SUMS')
        info.size = len(checksums.encode())
        info.mtime = EPOCH
        tf.addfile(info, io.BytesIO(checksums.encode()))
    digest = sha(out)
    with Path(str(out) + '.sha256').open('x') as f:
        f.write(digest + '  ' + out.name + '\n')
    print(json.dumps({'filename': out.name, 'bytes': out.stat().st_size, 'sha256': digest,
                      'scope': 'kernel and open-source boot-stack inputs plus audited build sources; excludes proprietary DDR bytes and userspace package sources'}))

if __name__ == '__main__':
    main()
