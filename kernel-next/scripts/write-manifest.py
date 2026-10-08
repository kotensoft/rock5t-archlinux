#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re

n = pathlib.Path(__file__).resolve().parent.parent
p = n / "payload"
release = (n / "build/board/include/config/kernel.release").read_text().strip()
old = n.parent / "research/deb-root"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(root):
    return sorted(str(f.relative_to(root)) for f in root.rglob("*.ko"))

old_modules = inventory(old / "lib/modules/6.18.44-current-rockchip64")
new_modules = inventory(p / f"usr/lib/modules/{release}")
missing = sorted(set(old_modules) - set(new_modules))
added = sorted(set(new_modules) - set(old_modules))
files = {}
for f in sorted(p.rglob("*")):
    if f.is_file() and f.name != "provenance.json":
        files[str(f.relative_to(p))] = {"bytes": f.stat().st_size, "sha256": sha(f)}
dtb = "boot/dtbs/rockchip/rk3588-rock-5t.dtb"
old_dtb = old / "boot/dtb-6.18.44-current-rockchip64/rockchip/rk3588-rock-5t.dtb"
log_path = n / "logs/qemu-landlock.log"
log = log_path.read_text(errors="replace") if log_path.exists() else ""
tests = dict(re.findall(r"UPSTREAM_SELFTEST_EXIT=([^:\s]+):(\d+)", log))
test_details = {}
for name, body, exitcode in re.findall(
    r"UPSTREAM_SELFTEST_BEGIN=([^\s]+)\s+(.*?)UPSTREAM_SELFTEST_EXIT=[^:\s]+:(\d+)",
    log, re.S
):
    totals = re.findall(r"# Totals:([^\r\n]+)", body)
    test_details[name] = {
        "exit_code": int(exitcode),
        "totals": {key: int(value) for key, value in re.findall(r"(\w+):(\d+)", totals[-1])} if totals else {},
    }
required_tests = {"base_test", "scoped_test", "scoped_signal_test", "scoped_abstract_unix_test",
                  "ptrace_test", "fs_test_layout0_layout1", "net_test_selected"}
abi_match = re.search(r"LANDLOCK_ABI (\d+)", log)
lsm_match = re.search(r"ACTIVE_LSM ([^\r\n]+)", log)
tested_image_sha = (n / "provenance/qemu-tested-image.sha256").read_text().split()[0]
pacman_report_path = n / "pacman-smoke/RESULT.json"
pacman_report = json.loads(pacman_report_path.read_text()) if pacman_report_path.exists() else None
result = {
    "schema_version": 1,
    "status": "compiled_local_test_payload",
    "kernel_release": release,
    "kernelrelease": release,
    "linux_commit": "1efe5d048a391de3ead2804b2e7f86376c356cc5",
    "armbian_commit": "fd4ebfd1e107d5b89f7a672c7d609789565753b2",
    "patchset_hash": "d9e569eab50e60b3",
    "linux": {
        "version": "6.18.44",
        "upstream_commit": "1efe5d048a391de3ead2804b2e7f86376c356cc5",
        "archive_url": "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.44.tar.xz",
        "archive_sha256": sha(n / "linux-6.18.44.tar.xz"),
        "signature_valid_fingerprint": "647F28654894E3BD457199BE38DBBDC86092693E",
        "key_bootstrap": "HTTPS from official kernel.org developer key repository",
    },
    "armbian": {
        "framework_commit": "fd4ebfd1e107d5b89f7a672c7d609789565753b2",
        "framework_archive_sha256": sha(n / "armbian-fd4ebfd1.tar.gz"),
        "matched_binary_release": "26.8.3",
        "matched_kernel_identifiers": {
            "framework_bash": "4990fb4ba983d439",
            "drivers": "539705d8_ceaab8e6",
            "patches": "d9e569eab50e60b3",
            "source_config": "40fcc37a0d6cf7d4",
            "config_hooks": "2153b201d2f3d096",
            "variables": "c22207b66dc5dd57157df2cd7b9c20559b2ed8ac44b9c3c3b9704002c06b8921",
            "extension_hooks": "01ba",
        },
        "driver_harness_entries": 21,
        "driver_patch_count": 48,
        "board_patch_count": 240,
        "patched_source_tree_sha1": (n / "provenance/patched-source-tree-hash.txt").read_text().strip(),
        "dts_overlay_autopatcher": "original Armbian patching.py",
        "driver_sources": json.loads((n / "provenance/driver-sources.lock.json").read_text()),
        "caveat": "Matching component hashes do not identify a unique original worker checkout. Driver skip list is not in package identifiers; default current branch skips none and every applicable driver is preserved.",
    },
    "baseline_config_sha256": sha(old / "boot/config-6.18.44-current-rockchip64"),
    "configuration_delta": (n / "provenance/config-delta.txt").read_text().splitlines(),
    "rt_policy": {
        "CONFIG_RT_GROUP_SCHED": "y",
        "boot_parameter": "rt_group_sched=0",
        "sched_rt_runtime_us": 950000,
        "sched_rt_period_us": 1000000,
    },
    "regression_checks": {
        "rock5t_dtb_matches_original_exactly": files[dtb]["sha256"] == sha(old_dtb),
        "original_module_count": len(old_modules),
        "new_module_count": len(new_modules),
        "missing_module_paths": missing,
        "additional_module_paths": added,
    },
    "validation": {
        "compile_image_modules_dtbs": (n / "logs/kernel-build.exit").read_text().strip() == "0",
        "qemu_machine": "virt, cortex-a72, TCG; not ROCK5T hardware",
        "qemu_tested_image_sha256": tested_image_sha,
        "payload_image_matches_qemu_tested_image": files["boot/Image"]["sha256"] == tested_image_sha,
        "qemu_landlock_smoke_pass": "ROCK5T_KERNEL_QEMU_SMOKE_PASS" in log,
        "running_landlock_abi": int(abi_match.group(1)) if abi_match else None,
        "running_active_lsm": lsm_match.group(1) if lsm_match else None,
        "qemu_test_run_finished": "ALL_QEMU_TESTS_FINISHED" in log,
        "original_kernel_negative_control_pass": "ORIGINAL_KERNEL_LANDLOCK_NEGATIVE_CONTROL_PASS" in (n / "logs/qemu-original-negative.log").read_text(errors="replace"),
        "upstream_selftest_exit_codes": tests,
        "upstream_selftest_details": test_details,
        "all_requested_qemu_tests_pass": "ROCK5T_KERNEL_QEMU_SMOKE_PASS" in log and "ALL_QEMU_TESTS_FINISHED" in log and required_tests.issubset(tests) and all(tests[name] == "0" for name in required_tests),
        "hardware_boot_tested": False,
        "hardware_video_or_codec_tested": False,
        "installed_on_user_machine": False,
        "installation_image_built_or_released": False,
    },
    "files": files,
}
if pacman_report is not None:
    result["validation"]["actual_pacman_default_sandbox"] = {
        "kernel_image_matches_this_payload": pacman_report["kernel_image_sha256"] == files["boot/Image"]["sha256"],
        "conclusions": pacman_report["conclusions"],
        "core_only_package_acceptance": pacman_report.get("core_only_package_acceptance"),
        "full_report": "../pacman-smoke/RESULT.json",
        "full_report_sha256": sha(pacman_report_path),
    }
(p / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
(n / "provenance/module-inventory-delta.json").write_text(json.dumps(result["regression_checks"], indent=2) + "\n")
print(json.dumps({"release": release, "module_count": len(new_modules), "missing_module_count": len(missing), "dtb_exact_match": result["regression_checks"]["rock5t_dtb_matches_original_exactly"]}))
if missing:
    raise SystemExit("Module inventory regression requires review")
