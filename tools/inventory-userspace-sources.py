#!/usr/bin/env python3
"""Inventory exact package metadata and corresponding-source gaps, without installation."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from urllib.parse import unquote, urlsplit

RECIPE_RE = re.compile(r'^[0-9a-f]{64}$')
PACKAGE_RE = re.compile(r'^[a-z0-9@][a-z0-9@+_.-]*$')
SOURCE_LICENSE = re.compile(r'(?:AGPL|LGPL|GPL|MPL|EPL|CDDL|CPL|EUPL|OSL|SSPL)', re.I)

def sha(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()

def fields(data):
    result = {}
    for line in data.decode('utf-8', errors='strict').splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition(' = ')
        if separator:
            result.setdefault(key, []).append(value)
    return result

def one(mapping, name):
    values = mapping.get(name, [])
    if len(values) > 1:
        raise ValueError('Unexpected repeated identity field: ' + name)
    return values[0] if values else None

def archive_metadata(path):
    """Read only metadata headers. Never extract paths or execute package scripts."""
    proc = None
    try:
        if path.name.endswith('.zst'):
            zstd = shutil.which('zstd')
            if not zstd:
                raise ValueError('zstd executable required to read this package')
            proc = subprocess.Popen([zstd, '-q', '-dc', str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            archive = tarfile.open(fileobj=proc.stdout, mode='r|')
        else:
            archive = tarfile.open(path, mode='r|*')
        found = {}
        with archive:
            for member in archive:
                name = member.name.removeprefix('./')
                if name in ('.PKGINFO', '.BUILDINFO'):
                    if not member.isfile() or member.size > 2 * 1024 * 1024:
                        raise ValueError('Unexpected package metadata type/size')
                    handle = archive.extractfile(member)
                    if handle is None:
                        raise ValueError('Unreadable package metadata')
                    found[name] = fields(handle.read())
                if len(found) == 2:
                    break
                # makepkg places metadata first; do not decompress the payload just to find a missing header.
                if archive.offset > 8 * 1024 * 1024:
                    break
        if '.PKGINFO' not in found:
            raise ValueError('Missing .PKGINFO in package header region')
        return found
    finally:
        if proc:
            if proc.stdout:
                proc.stdout.close()
            proc.terminate()
            proc.wait()

def inspect_package(path):
    try:
        meta = archive_metadata(path)
        pkg, build = meta['.PKGINFO'], meta.get('.BUILDINFO', {})
        name, version = one(pkg, 'pkgname'), one(pkg, 'pkgver')
        base = one(pkg, 'pkgbase') or name
        if not name or not version or not PACKAGE_RE.fullmatch(name) or not PACKAGE_RE.fullmatch(base):
            raise ValueError('Invalid package identity')
        recipe = one(build, 'pkgbuild_sha256sum')
        if recipe and not RECIPE_RE.fullmatch(recipe):
            raise ValueError('Invalid .BUILDINFO PKGBUILD hash')
        for field, actual in [('pkgname', name), ('pkgbase', base), ('pkgver', version), ('pkgarch', one(pkg, 'arch'))]:
            recorded = one(build, field)
            if recorded and recorded != actual:
                raise ValueError('.BUILDINFO identity disagrees with .PKGINFO: ' + field)
        license_values = pkg.get('license', [])
        signature = path.with_name(path.name + '.sig')
        return {'pkgname': name, 'pkgbase': base, 'version': version, 'architecture': one(pkg, 'arch'),
                'licenses_declared': license_values, 'upstream_url': one(pkg, 'url'),
                'archive_filename': path.name, 'archive_bytes': path.stat().st_size,
                'archive_sha256': sha(path), 'detached_signature_present': signature.is_file(),
                'detached_signature_sha256': sha(signature) if signature.is_file() else None,
                'signature_verification': 'not_repeated_by_this_read_only_inventory',
                'buildinfo_present': '.BUILDINFO' in meta, 'pkgbuild_sha256_expected': recipe,
                'buildtool': one(build, 'buildtool'), 'buildtool_version': one(build, 'buildtoolver'),
                'metadata_status': 'exact_cached_package',
                'license_review': 'source_license_declared' if any(SOURCE_LICENSE.search(x) for x in license_values)
                                  else 'other_or_incomplete_top_level_license_metadata',
                'license_files_in_payload': 'not_inspected_header_only',
                'source_status': 'not_collected_or_verified', 'source_evidence': [],
                'missing_evidence': ['original_recipe_provenance_unresolved_despite_recorded_digest' if recipe else 'original_recipe_provenance_without_recorded_digest',
                                     'complete_recipe_auxiliary_files_and_patches',
                                     'all_exact_source_archives_or_VCS_snapshots_and_submodules',
                                     'source_hash_signature_checks_and_complete_license_inventory']}
    except Exception as exc:
        return {'archive_filename': path.name, 'metadata_status': 'read_error',
                'error': type(exc).__name__ + ': ' + str(exc)}

def repository_metadata(path):
    """Read an existing pacman sync DB as a fallback; never mark binary metadata verified."""
    records = {}
    with tarfile.open(path, 'r|*') as archive:
        for member in archive:
            if not member.name.endswith('/desc') or not member.isfile():
                continue
            if member.size > 2 * 1024 * 1024:
                raise ValueError('Unexpected repository metadata size')
            data = archive.extractfile(member).read().decode('utf-8')
            info = {}
            for block in data.strip().split('\n\n'):
                lines = block.splitlines()
                if len(lines) >= 2 and lines[0].startswith('%') and lines[0].endswith('%'):
                    info[lines[0].strip('%')] = lines[1:]
            name, version = one(info, 'NAME'), one(info, 'VERSION')
            if not name or not version or not PACKAGE_RE.fullmatch(name):
                continue
            base = one(info, 'BASE') or name
            if not PACKAGE_RE.fullmatch(base):
                raise ValueError('Invalid repository package base')
            licenses = info.get('LICENSE', [])
            records[(name, version)] = {
                'pkgname': name, 'pkgbase': base, 'version': version, 'architecture': one(info, 'ARCH'),
                'licenses_declared': licenses, 'upstream_url': one(info, 'URL'),
                'archive_filename': one(info, 'FILENAME'),
                'archive_sha256_expected_from_repository': one(info, 'SHA256SUM'),
                'repository_database_filename': path.name,
                'metadata_status': 'exact_repository_index_only',
                'signature_verification': 'not_repeated_by_this_read_only_inventory',
                'buildinfo_present': False, 'pkgbuild_sha256_expected': None,
                'license_review': 'source_license_declared' if any(SOURCE_LICENSE.search(x) for x in licenses)
                                  else 'other_or_incomplete_top_level_license_metadata',
                'license_files_in_payload': 'not_inspected',
                'source_status': 'not_collected_or_verified', 'source_evidence': [],
                'missing_evidence': ['exact_binary_package_BUILDINFO_and_recorded_PKGBUILD_digest',
                    'complete_recipe_auxiliary_files_and_patches',
                    'all_exact_source_archives_or_VCS_snapshots_and_submodules',
                    'source_hash_signature_checks_and_complete_license_inventory']}
    return records

def route_evidence(path):
    """Accept only evidence whose referenced local material bytes still match."""
    document = json.loads(path.read_text())
    if document.get('schema_version') != 1 or not isinstance(document.get('entries'), list):
        raise ValueError('Unsupported source-route evidence schema')
    entries = {}
    for entry in document['entries']:
        base, version = entry['pkgbase'], entry['version']
        if not PACKAGE_RE.fullmatch(base) or not isinstance(version, str):
            raise ValueError('Invalid source-route identity')
        for artifact in entry.get('actual_materials_obtained', []):
            name = artifact['file_basename']
            if Path(name).name != name or name in ('.', '..'):
                raise ValueError('Source evidence requires safe local basenames')
            local = path.parent/name
            if (not local.is_file() or local.is_symlink() or local.stat().st_size != artifact['bytes']
                    or sha(local) != artifact['sha256']):
                raise ValueError('Source evidence file differs from recorded bytes: ' + name)
        if (base, version) in entries:
            raise ValueError('Duplicate source-route entry')
        entries[(base, version)] = {k: entry.get(k, []) for k in
            ('actual_materials_obtained', 'actual_material_gaps', 'provenance_gaps')}
        entries[(base, version)]['observed_at_utc'] = entry.get('observed_at_utc')
    return entries

def parse_assignment(value):
    label, equals, filename = value.partition('=')
    if not equals or not re.fullmatch(r'[a-z0-9_-]+', label):
        raise argparse.ArgumentTypeError('Use a lowercase label=filename')
    return label, Path(filename)

def load_package_list(path):
    result = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not PACKAGE_RE.fullmatch(parts[0]):
            raise ValueError('Expected pacman -Q output with one package and version per line')
        result.append(tuple(parts))
    if len(result) != len(set(result)):
        raise ValueError('Duplicate package/version in package list')
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, action='append', required=True)
    p.add_argument('--repository-db', type=Path, action='append', default=[], help='existing sync database for explicitly labeled metadata fallback')
    p.add_argument('--variant', type=parse_assignment, action='append', default=[], help='label=pacman-Q-file')
    p.add_argument('--planned-url-list', type=parse_assignment, action='append', default=[], help='label=pacman-Sp-URL-file; never treated as installed')
    p.add_argument('--stage', choices=['provisional', 'final'], default='provisional')
    p.add_argument('--route-evidence', type=Path, help='reviewed source-route JSON with sibling material files; hashes are rechecked')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--csv', type=Path)
    p.add_argument('--summary', type=Path)
    p.add_argument('--workers', type=int, default=2)
    a = p.parse_args()
    if not 1 <= a.workers <= 8:
        p.error('--workers must be 1 through 8')
    if a.stage == 'final' and (not a.variant or a.planned_url_list):
        p.error('Final inventory requires installed package lists and no prospective URL lists')
    paths = []
    for cache in a.cache:
        if cache.is_symlink() or not cache.is_dir():
            p.error('Cache must be a regular existing directory')
        paths.extend(x for x in cache.iterdir() if x.is_file() and not x.is_symlink()
                     and re.search(r'\.pkg\.tar\.(?:xz|zst|gz)$', x.name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        cached = list(pool.map(inspect_package, sorted(set(paths))))
    errors = [x for x in cached if x['metadata_status'] == 'read_error']
    index = {}
    for record in cached:
        if record['metadata_status'] != 'read_error':
            index.setdefault((record['pkgname'], record['version']), []).append(record)
    repository_index, repository_inputs = {}, []
    for database in a.repository_db:
        if not database.is_file() or database.is_symlink():
            p.error('Repository DB must be a regular existing file')
        records = repository_metadata(database)
        for identity, record in records.items():
            if identity in repository_index and repository_index[identity].get('archive_sha256_expected_from_repository') != record.get('archive_sha256_expected_from_repository'):
                p.error('Conflicting exact repository package hashes')
            repository_index[identity] = record
        repository_inputs.append({'filename': database.name, 'sha256': sha(database), 'records': len(records)})
    selected, inputs = {}, []
    for label, path in a.variant:
        if any(i['label'] == label for i in inputs):
            p.error('Duplicate inventory label')
        packages = load_package_list(path)
        inputs.append({'label': label, 'kind': 'installed_package_list', 'filename': path.name,
                       'sha256': sha(path), 'package_count': len(packages)})
        for identity in packages:
            selected.setdefault(identity, {'installed_variants': [], 'planned_variants': []})['installed_variants'].append(label)
    planned_missing = []
    for label, path in a.planned_url_list:
        if any(i['label'] == label for i in inputs):
            p.error('Duplicate inventory label')
        filenames = {unquote(Path(urlsplit(line.strip()).path).name) for line in path.read_text().splitlines()
                     if line.startswith(('https://', 'http://'))}
        inputs.append({'label': label, 'kind': 'planned_package_URL_list', 'filename': path.name,
                       'sha256': sha(path), 'package_count': len(filenames)})
        matched = set()
        for identity, candidates in index.items():
            if any(c['archive_filename'] in filenames for c in candidates):
                selected.setdefault(identity, {'installed_variants': [], 'planned_variants': []})['planned_variants'].append(label)
                matched.update(c['archive_filename'] for c in candidates if c['archive_filename'] in filenames)
        planned_missing.extend({'planned_variant': label, 'archive_filename': filename} for filename in sorted(filenames - matched))
    if not inputs:
        selected = {identity: {'installed_variants': [], 'planned_variants': []} for identity in index}
    records = []
    for identity, membership in sorted(selected.items()):
        candidates = index.get(identity, [])
        if not candidates and identity in repository_index:
            record = dict(repository_index[identity])
        elif not candidates:
            record = {'pkgname': identity[0], 'pkgbase': None, 'version': identity[1],
                      'metadata_status': 'exact_package_missing_from_cache', 'licenses_declared': [],
                      'pkgbuild_sha256_expected': None, 'source_status': 'not_collected_or_verified',
                      'source_evidence': [], 'missing_evidence': ['exact_binary_package_metadata_and_BUILDINFO',
                      'complete_exact_corresponding_source_and_license_materials']}
        else:
            record = dict(candidates[0])
            hashes = {c['archive_sha256'] for c in candidates}
            if len(hashes) > 1:
                record['metadata_status'] = 'conflicting_exact_package_archives'
                record['candidate_archive_sha256'] = sorted(hashes)
        record.update(membership)
        if identity[0] == 'linux-rock5t':
            record['source_status'] = 'separate_kernel_source_lock_required'
            record['source_evidence'] = ['sources.lock.json', 'docs/SOURCES.md']
            record['missing_evidence'] = ['verify_exact_installed_custom_kernel_version_matches_source_lock']
        records.append(record)
    source_routes = route_evidence(a.route_evidence) if a.route_evidence else {}
    matched_routes = set()
    for row in records:
        identity = (row.get('pkgbase') or row['pkgname'], row['version'])
        if identity in source_routes:
            row['source_route_review'] = source_routes[identity]
            row['source_status'] = 'partial_materials_retrieved_and_hashed'
            matched_routes.add(identity)
    grouped = {}
    for row in records:
        key = (row.get('pkgbase') or row['pkgname'], row['version'], row.get('pkgbuild_sha256_expected'))
        group = grouped.setdefault(key, {'pkgbase_or_unresolved_name': key[0], 'version': key[1],
            'pkgbuild_sha256_expected': key[2], 'pkgbase_verified': bool(row.get('pkgbase')),
            'package_names': [], 'source_status': row['source_status']})
        group['package_names'].append(row['pkgname'])
    source_groups = sorted(grouped.values(), key=lambda x: (x['pkgbase_or_unresolved_name'], x['version']))
    summary = {'packages_selected': len(records), 'source_recipe_groups': len(source_groups), 'cache_archives_inspected': len(cached),
               'metadata_read_errors': len(errors), 'planned_archives_missing': len(planned_missing),
               'exact_binary_package_metadata_missing': sum(x['metadata_status'] in ('exact_package_missing_from_cache', 'exact_repository_index_only') for x in records),
               'repository_index_only': sum(x['metadata_status'] == 'exact_repository_index_only' for x in records),
               'all_exact_package_metadata_missing': sum(x['metadata_status'] == 'exact_package_missing_from_cache' for x in records),
               'conflicting_package_archives': sum(x['metadata_status'] == 'conflicting_exact_package_archives' for x in records),
               'buildinfo_PKGBUILD_hash_recorded': sum(bool(x.get('pkgbuild_sha256_expected')) for x in records),
               'packages_declaring_source_licenses': sum(x.get('license_review') == 'source_license_declared' for x in records),
               'source_recipe_groups_with_route_evidence': len(matched_routes),
               'verified_complete_userspace_source_sets': 0}
    output = {'schema_version': 1, 'inventory_stage': a.stage, 'inputs': inputs, 'repository_database_inputs': repository_inputs, 'summary': summary,
              'interpretation': 'Package metadata only. A recipe digest mismatch is provenance uncertainty, not an automatic legal conclusion. A homepage, expected recipe digest or detached signature file is not corresponding source or a verification result. Top-level package licenses can omit bundled components. Planned URL lists do not establish installed state. No release-compliance assertion is made.',
              'source_route_evidence_input': {'filename': a.route_evidence.name, 'sha256': sha(a.route_evidence)} if a.route_evidence else None,
              'packages': records, 'source_recipe_groups': source_groups, 'cache_metadata_errors': errors, 'planned_archives_missing': planned_missing}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
    if a.csv:
        a.csv.parent.mkdir(parents=True, exist_ok=True)
        columns = ['pkgname', 'pkgbase', 'version', 'installed_variants', 'planned_variants', 'licenses_declared',
                   'upstream_url', 'pkgbuild_sha256_expected', 'archive_sha256', 'metadata_status', 'source_status']
        with a.csv.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader()
            for row in records:
                writer.writerow({k: '; '.join(row[k]) if isinstance(row.get(k), list) else row.get(k, '') for k in columns})
    if a.summary:
        a.summary.parent.mkdir(parents=True, exist_ok=True)
        text = '# Userspace source inventory\n\nStage: ' + a.stage + '\n\n'
        text += '\n'.join('- ' + key + ': ' + str(value) for key, value in summary.items()) + '\n\n'
        text += 'No userspace source set is marked complete by this metadata-only tool.\n'
        text += '\n## Exact binary package metadata missing\n\n'
        missing = [x for x in records if x['metadata_status'] in ('exact_package_missing_from_cache', 'exact_repository_index_only')]
        text += '\n'.join('- ' + x['pkgname'] + ' ' + x['version'] + ' (' + x['metadata_status'] + ')' for x in missing) or '- None'
        text += '\n\nFor every unresolved package, establish the relevant recipe, all auxiliary files and patches, pinned source archives/VCS snapshots and submodules, and required licenses. A matching recorded PKGBUILD digest is strong provenance evidence; a mismatch alone does not determine whether corresponding-source materials are sufficient. Archive evidence separately.\n'
        a.summary.write_text(text)
    print(json.dumps(summary, indent=2))
    if errors or planned_missing or any(x['metadata_status'] == 'conflicting_exact_package_archives' for x in records):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
