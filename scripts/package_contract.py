#!/usr/bin/env python3
"""Read-only installed-package contract shared by root and offline-image gates."""
import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED_COMMON = frozenset(('rtkit', 'wireless-regdb', 'iw'))
PAYLOAD_FILES = (
    '/usr/bin/iw',
    '/usr/lib/firmware/regulatory.db',
    '/usr/lib/firmware/regulatory.db.p7s',
    '/usr/lib/rtkit-daemon',
    '/usr/lib/systemd/system/rtkit-daemon.service',
    '/usr/share/dbus-1/system-services/org.freedesktop.RealtimeKit1.service',
)
NAME = re.compile(r'[a-zA-Z0-9@._+][a-zA-Z0-9@._+-]*')
VERSION = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9:._+~-]*')


def required_packages(profiles, variant):
    if variant not in ('cli', 'kde'):
        raise ValueError('Unknown package variant')
    def load(name):
        values = [line.split('#', 1)[0].strip()
                  for line in (Path(profiles) / (name + '.packages')).read_text().splitlines()]
        values = [value for value in values if value]
        if not values or any(not NAME.fullmatch(value) for value in values):
            raise ValueError('Invalid or empty package profile: ' + name)
        return set(values)
    required = load('cli')
    missing = REQUIRED_COMMON - required
    if missing:
        raise ValueError('Required common packages absent from profile: ' + ', '.join(sorted(missing)))
    if variant == 'kde':
        required |= load('kde')
    return required


def parse_manifest(text):
    packages = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 2 or not NAME.fullmatch(fields[0]) or not VERSION.fullmatch(fields[1]):
            raise ValueError('Invalid package manifest entry')
        name, version = fields
        if name in packages:
            raise ValueError('Duplicate package manifest entry: ' + name)
        packages[name] = version
    if not packages:
        raise ValueError('Empty package manifest')
    return packages


def validate_packages(text, variant, profiles, read_text, nonempty_file):
    """Check the embedded inventory against requirements, live pacman DB and files."""
    packages = parse_manifest(text)
    required = required_packages(profiles, variant)
    missing = required - packages.keys()
    if missing:
        raise ValueError('Missing required packages: ' + ', '.join(sorted(missing)))
    for name in sorted(required):
        version = packages[name]
        # The local database directory preserves the full version, including epoch.
        dirname = name + '-' + version
        desc = read_text('/var/lib/pacman/local/' + dirname + '/desc')
        fields = {}
        for group in desc.strip().split('\n\n'):
            lines = group.splitlines()
            if lines:
                fields[lines[0]] = lines[1:]
        if fields.get('%NAME%') != [name] or fields.get('%VERSION%') != [version]:
            raise ValueError('Package database disagrees with manifest: ' + name)
    for filename in PAYLOAD_FILES:
        if not nonempty_file(filename):
            raise ValueError('Required package payload missing or empty: ' + filename)
    return {
        'status': 'passed', 'variant': variant, 'installed_count': len(packages),
        'required_versions': {name: packages[name] for name in sorted(required)},
        'manifest_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'package_database_verified': True, 'payload_files_verified': list(PAYLOAD_FILES),
    }


def validate_root(root, variant, profiles, manifest):
    root = Path(root)
    return validate_packages(
        Path(manifest).read_text(), variant, profiles,
        lambda path: (root / path.lstrip('/')).read_text(),
        lambda path: (root / path.lstrip('/')).is_file()
        and (root / path.lstrip('/')).stat().st_size > 0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--variant', required=True, choices=('cli', 'kde'))
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--profiles', type=Path, default=Path(__file__).resolve().parents[1] / 'profiles')
    args = parser.parse_args()
    print(json.dumps(validate_root(args.root, args.variant, args.profiles, args.manifest), indent=2))


if __name__ == '__main__':
    main()
