#!/usr/bin/env python3
"""Read-only Linux target inspection; NEVER installs or changes a disk.

Run on the board only when requested. Passing is a snapshot, not permission to
write and not a guarantee that another process will not mount the device later.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat


def reject_reasons(evidence, image_bytes):
    reasons = []
    if evidence.get('type') != 'MMC':
        reasons.append('Target is not a native MMC device; SD/USB/NVMe are unsupported by this inspector')
    if not evidence.get('cid'):
        reasons.append('Missing MMC CID; target identity is not established')
    if evidence.get('logical_sector_bytes') != 512:
        reasons.append('Image requires 512-byte logical sectors; do not change eMMC sector configuration')
    if image_bytes <= 0 or evidence.get('capacity_bytes', 0) < image_bytes:
        reasons.append('Target is smaller than the complete uncompressed image or size is invalid')
    if evidence.get('read_only') != 0:
        reasons.append('Target is read-only or read-only state is unknown')
    for key in ('mounted', 'swap', 'holders'):
        if evidence.get(key):
            reasons.append('Target or child has active ' + key + ': ' + ', '.join(evidence[key]))
    return reasons


def collect(device):
    canonical = Path(os.path.realpath(device))
    if not re.fullmatch(r'mmcblk[0-9]+', canonical.name) or canonical.parent != Path('/dev'):
        raise ValueError('Select the whole native eMMC user-area disk, never a partition, boot0, boot1 or rpmb')
    st = canonical.stat()
    if not stat.S_ISBLK(st.st_mode):
        raise ValueError('Target is not a block device')
    node = Path('/sys/class/block') / canonical.name
    if (node / 'partition').exists():
        raise ValueError('Target is a partition')
    if (node / 'dev').read_text().strip() != f'{os.major(st.st_rdev)}:{os.minor(st.st_rdev)}':
        raise ValueError('Device/sysfs identity mismatch')
    children = [node] + sorted(node.glob(canonical.name + 'p*'))
    ids = {(child / 'dev').read_text().strip() for child in children}
    mounted = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        if len(fields) > 4 and fields[2] in ids:
            mounted.append(fields[4])
    swap = []
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        # A swap file on the target is covered by the mounted-filesystem gate.
        name = line.split()[0]
        item = Path(name).stat()
        if stat.S_ISBLK(item.st_mode) and f'{os.major(item.st_rdev)}:{os.minor(item.st_rdev)}' in ids:
            swap.append(name)
    holders = [child.name + ':' + h.name for child in children for h in (child / 'holders').iterdir()]
    return {'device': str(canonical), 'type': (node / 'device/type').read_text().strip(),
            'cid': (node / 'device/cid').read_text().strip(),
            'capacity_bytes': int((node / 'size').read_text()) * 512,
            'logical_sector_bytes': int((node / 'queue/logical_block_size').read_text()),
            'read_only': int((node / 'ro').read_text()),
            'mounted': mounted, 'swap': swap, 'holders': holders}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--image-bytes', type=int, required=True,
                        help='Complete decompressed .img size from the verified release manifest')
    args = parser.parse_args()
    try:
        evidence = collect(args.device)
        reasons = reject_reasons(evidence, args.image_bytes)
        print(json.dumps({'status': 'blocked' if reasons else 'read-only-check-passed',
                          'writes_performed': False, 'reasons': reasons, 'evidence': evidence,
                          'limitations': ['Only this mount namespace is checked; run on the host, not in a container.',
                                         'Recheck identity and all mounts immediately before a manual write.']}, indent=2))
        return bool(reasons)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
