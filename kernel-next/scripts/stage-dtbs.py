#!/usr/bin/env python3
import pathlib
import shutil

n = pathlib.Path(__file__).resolve().parent.parent
source = n / "linux-6.18.44"
build = n / "build/board"
prefix = pathlib.Path("arch/arm64/boot/dts")
destination = n / "payload/boot/dtbs"
count = 0
for line in (build / prefix / "dtbs-list").read_text().splitlines():
    item = pathlib.Path(line)
    if item.is_absolute():
        relative = item.relative_to(source / prefix)
        origin = item
    else:
        relative = item.relative_to(prefix)
        origin = build / item
    if ".." in relative.parts or not origin.is_file():
        raise SystemExit(f"Invalid DTB install entry: {line}")
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin, target)
    target.chmod(0o644)
    count += 1
print(f"Staged all {count} dtbs-list entries, including original overlay documentation.")
