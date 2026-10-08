#!/usr/bin/env python3
"""Fetch or verify exact source archives. Never execute downloaded content."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]

def verify(path, item):
    if not path.is_file() or path.is_symlink() or path.stat().st_size != item['bytes']:
        return False
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest() == item['sha256']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=REPO)
    parser.add_argument('--fetch', action='store_true', help='download missing archives; default is verification only')
    args = parser.parse_args()
    root = args.source_root.resolve()
    lock = json.loads((REPO / 'sources.lock.json').read_text())
    for item in lock['archive_inputs']:
        path = root / item['path']
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise SystemExit('Unsafe source archive path')
        if path.exists():
            if not verify(path, item):
                raise SystemExit('Existing archive differs from lock: ' + item['path'])
        else:
            if not args.fetch:
                raise SystemExit('Missing source archive: ' + item['path'])
            url = urlsplit(item['url'])
            if url.scheme != 'https' or url.username or url.password:
                raise SystemExit('Expected public HTTPS archive URL')
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + '.partial')
            if temporary.exists():
                raise SystemExit('Partial file already exists; review it before retrying')
            subprocess.run(['curl', '--proto', '=https', '--proto-redir', '=https', '--fail',
                            '--location', '--retry', '3', '--connect-timeout', '30',
                            '--max-time', '900', item['url'], '--output', str(temporary)], check=True)
            if not verify(temporary, item):
                raise SystemExit('Downloaded source archive hash/size mismatch: ' + item['path'])
            temporary.rename(path)
        print('Verified ' + item['path'])

if __name__ == '__main__':
    main()
