#!/usr/bin/env python3
"""Split a validated versioned image into <=90 MiB files, retaining the full .xz."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'packaging-work'))
import release_image as release
import rock5t_image as image

MAX_PART_BYTES = 90 * image.MIB
ASSETS = ('merge.sh', 'merge.ps1', 'verify.sh', 'verify.ps1', '安装与恢复.zh-CN.txt')



def redact_build_paths(value, build_root=BASE):
    """Copy a JSON value, replacing only this build's absolute path prefix.

    $BUILD_ROOT denotes the directory containing packaging-work/output/vm. Hashes,
    byte counts, relative/device paths and validation outcomes remain unchanged.
    The original report is never rewritten.
    """
    prefix = str(Path(build_root).resolve())
    pattern = re.compile(re.escape(prefix) + r"(?=/|$|[\s'\"])")

    def clean(item):
        if isinstance(item, str):
            return pattern.sub('$BUILD_ROOT', item)
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                sanitized_key = clean(key)
                image.require(sanitized_key not in result, 'Redaction would collide JSON keys')
                result[sanitized_key] = clean(child)
            return result
        return item

    return clean(value)


def export_json_report(source, destination, build_root=BASE):
    """Write a sanitized delivery copy while retaining the original verbatim."""
    value = json.loads(source.read_text())
    with destination.open('x') as outgoing:
        outgoing.write(json.dumps(redact_build_paths(value, build_root), indent=2) + '\n')


def split_file(source, destination, part_bytes=MAX_PART_BYTES):
    image.regular(source, 'Source compressed file')
    image.require(re.fullmatch(r'[A-Za-z0-9._-]+\.img\.xz', source.name), 'Unsafe image filename')
    image.require(0 < part_bytes <= MAX_PART_BYTES, 'Parts must be <=90 MiB')
    image.require(destination.is_dir() and not any(destination.iterdir()), 'Delivery directory must be empty')
    before = source.stat()
    rows, joined = [], hashlib.sha256()
    with source.open('rb') as incoming:
        index = 1
        while True:
            data = incoming.read(part_bytes)
            if not data:
                break
            image.require(index <= 999, 'Too many parts for three-digit numbering')
            name = f'{source.name}.part{index:03d}'
            with (destination / name).open('xb') as outgoing:
                outgoing.write(data)
            joined.update(data)
            rows.append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            index += 1
    after = source.stat()
    image.require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                  (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Source changed while splitting')
    image.require(rows and sum(row['bytes'] for row in rows) == before.st_size, 'Empty or incomplete source')
    return {'schema': 1, 'filename': source.name, 'bytes': before.st_size, 'sha256': joined.hexdigest(),
            'maximum_part_bytes': part_bytes, 'parts': rows}


def prepare(variant, version, destination, part_bytes=MAX_PART_BYTES):
    _, raw = release.release_paths(variant, version)
    source = Path(str(raw) + '.xz')
    manifest = json.loads(Path(str(raw) + '.manifest.json').read_text())
    evidence = manifest.get('release_preflight', {})
    image.require(evidence.get('status') == 'passed' and evidence.get('version') == version and evidence.get('variant') == variant,
                  'Missing validated release/variant evidence')
    image.require(manifest.get('validation', {}).get('status') == 'passed' and
                  manifest.get('compressed_decompressed_sha256_verified') is True, 'Missing disk/round-trip validation')
    image.require(manifest['partition_ids'] == release.expected_ids(variant, version), 'Release partition IDs mismatch')
    image.require(not destination.exists(), 'Refusing to replace an existing delivery folder')
    # A fresh read proves the retained compressed source still yields the validated raw bytes.
    release.verify_compressed(source, manifest['image_sha256'])
    destination.mkdir(parents=True)
    parts = split_file(source, destination, part_bytes)
    image.require(parts['sha256'] == manifest['compressed_sha256'] and parts['bytes'] == manifest['compressed_bytes'],
                  'Retained compressed source differs from image manifest')
    parts.update(version=version, variant=variant, kernel_release=release.KERNEL, hardware_tested=False,
                 raw_filename=raw.name, raw_bytes=manifest['disk_bytes'], raw_sha256=manifest['image_sha256'])
    (destination / (source.name + '.parts.sha256')).write_text(''.join(f'{p["sha256"]}  {p["name"]}\n' for p in parts['parts']))
    (destination / (source.name + '.parts.json')).write_text(json.dumps(redact_build_paths(parts), indent=2) + '\n')
    (destination / (source.name + '.sha256')).write_text(f'{parts["sha256"]}  {source.name}\n')
    (destination / (raw.name + '.sha256')).write_text(f'{manifest["image_sha256"]}  {raw.name}\n')
    for suffix in ('.manifest.json', '.validation.json'):
        export_json_report(Path(str(raw) + suffix), destination / (raw.name + suffix))
    for asset in ASSETS:
        shutil.copyfile(Path(__file__).parent / asset, destination / asset)
    # Script/report checksums are useful integrity checks, not independent signatures.
    small = sorted(p for p in destination.iterdir() if p.is_file() and not re.search(r'\.part[0-9]{3}$', p.name))
    (destination / 'DELIVERY-SHA256SUMS.txt').write_text(''.join(f'{image.digest(p)}  {p.name}\n' for p in small))
    return {'delivery': str(destination), 'parts': len(parts['parts']), 'maximum_part_bytes': part_bytes,
            'compressed_sha256': parts['sha256'], 'full_compressed_retained': str(source), 'hardware_tested': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant', required=True, choices=('cli', 'kde'))
    p.add_argument('--version', default=release.VERSION)
    p.add_argument('--destination', type=Path)
    p.add_argument('--part-size-mib', type=int, default=90, choices=range(1, 91))
    args = p.parse_args()
    try:
        destination = args.destination or BASE / 'delivery' / args.version / args.variant
        print(json.dumps(prepare(args.variant, args.version, destination, args.part_size_mib * image.MIB), indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
