#!/usr/bin/env python3
"""Unprivileged filesystem tests; synthetic fixtures are NOT bootable kernels.

Optional real-payload retention case:
  ROCK5T_REAL_PAYLOAD=/path/to/exact-release \
  ROCK5T_REAL_INITRAMFS=/path/to/matching-initramfs.img \
  python3 test_kernel_generations.py

That case uses real bytes only for the previous generation. Its new generation
is deliberately synthetic. No test boots a kernel, runs pacman, or proves a
second actual uname -r. SIGKILL injection is not power-loss testing on FAT.
"""
import errno
import fcntl
import gzip
import importlib.machinery
import importlib.util
import json
import lzma
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / "rootfs/usr/local/sbin/rock5t-kernel"
loader = importlib.machinery.SourceFileLoader("kernel_generation_manager", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
kernel = importlib.util.module_from_spec(spec)
loader.exec_module(kernel)
OLD = "6.0.0-synthetic-fixture-a"
NEW = "6.0.0-synthetic-fixture-b"
THIRD = "6.0.0-synthetic-fixture-c"
DTB = "rockchip/rk3588-rock-5t.dtb"


def write_manifest(source, dtb=DTB):
    data = {"format": 1, "release": source.name, "dtb": dtb,
            "files": kernel.inventory(source, ("manifest.json",))}
    (source / "manifest.json").write_text(json.dumps(data))


def payload(root, release):
    source = root / "usr/lib/rock5t-kernel" / release
    (source / "modules/kernel").mkdir(parents=True)
    (source / "dtbs/rockchip").mkdir(parents=True)
    (source / "Image").write_bytes(bytes(56) + b"ARM\x64" + release.encode())
    (source / "dtbs" / DTB).write_bytes(bytes.fromhex("d00dfeed") + release.encode())
    (source / "modules/kernel/fixture.ko").write_bytes(b"NOT ELF; synthetic module fixture: " + release.encode())
    (source / "modules/modules.dep").write_text("kernel/fixture.ko:\n")
    write_manifest(source)
    return source


def crash_worker(root, release, initramfs, point):
    manager = kernel.KernelManager(Path(root), allow_unmounted=True)
    original_rename, original_replace, original_sync = kernel.os.rename, kernel.os.replace, kernel.sync_tree

    def die():
        os.kill(os.getpid(), signal.SIGKILL)

    def rename(source, destination):
        original_rename(source, destination)
        if point == "modules-published" and Path(destination) == manager.modules / release:
            die()
        if point == "generation-published" and Path(destination) == manager.generations / release:
            die()

    def replace(source, destination):
        if point == "menu-before-replace" and Path(destination) == manager.extlinux:
            die()
        original_replace(source, destination)
        if point == "menu-after-replace" and Path(destination) == manager.extlinux:
            die()
        if point == "backup-published" and Path(destination) == manager.extlinux.with_name("extlinux.conf.previous"):
            die()

    def sync_tree(directory):
        original_sync(directory)
        if point == "boot-staged" and Path(directory).parent == manager.generations:
            die()

    kernel.os.rename, kernel.os.replace, kernel.sync_tree = rename, replace, sync_tree
    manager.activate(release, Path(initramfs))
    raise AssertionError("requested crash point was not reached")


class Fixture(unittest.TestCase):
    temporary_parent = None

    def setUp(self):
        if self.temporary_parent:
            Path(self.temporary_parent).mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="rock5t-kernel-test-", dir=self.temporary_parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "boot").mkdir()
        (self.root / "etc/rock5t").mkdir(parents=True)
        (self.root / "etc/rock5t/kernel.json").write_text(json.dumps({"cmdline": "root=PARTUUID=11111111-2222-3333-4444-555555555555 rootwait rw"}))
        self.initrd = self.root / "synthetic-initramfs.img"
        self.initrd.write_bytes(b"NOT CPIO; synthetic initramfs fixture")
        self.m = kernel.KernelManager(self.root, allow_unmounted=True)

    def install(self, release):
        payload(self.root, release)
        return self.m.activate(release, self.initrd)

    def cli(self, action, *options, check=True):
        return subprocess.run([sys.executable, str(SCRIPT), action, "--root", str(self.root), "--allow-unmounted-boot", *options], check=check, text=True, capture_output=True)

    def snapshot(self, release):
        return {"boot": kernel.inventory(self.m.generations / release),
                "modules": kernel.inventory(self.m.modules / release)}

    def kill(self, point, release=NEW):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--crash-worker", str(self.root), release, str(self.initrd), point], text=True, capture_output=True)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)


class KernelTransitions(Fixture):
    def setUp(self):
        super().setUp()
        self.install(OLD)
        self.original = self.snapshot(OLD)
        self.menu = self.m.extlinux.read_bytes()

    def assert_old_unchanged(self):
        self.assertEqual(self.snapshot(OLD), self.original)

    def test_complete_retention_after_payload_removal_and_third_upgrade(self):
        shutil.rmtree(self.m.payloads / OLD)
        self.install(NEW)
        second = self.snapshot(NEW)
        shutil.rmtree(self.m.payloads / NEW)
        self.install(THIRD)
        self.assertEqual(self.m.preflight(), {"current": THIRD, "previous": NEW})
        self.assertEqual(self.snapshot(NEW), second)
        self.assert_old_unchanged()
        self.assertEqual(set(self.original["boot"]), {"Image", "board.dtb", "initramfs.img", "generation.json"})
        self.assertIn("LABEL rock5t-previous", self.m.extlinux.read_text())
        self.assertIn(f"LINUX /rock5t/{NEW}/Image", self.m.extlinux.read_text())
        self.assertIn(f"FDT /rock5t/{NEW}/board.dtb", self.m.extlinux.read_text())
        self.assertIn(f"INITRD /rock5t/{NEW}/initramfs.img", self.m.extlinux.read_text())

    def test_removed_package_and_incomplete_replacement_leave_runtime_intact(self):
        shutil.rmtree(self.m.payloads / OLD)
        source = payload(self.root, NEW)
        (source / "Image").unlink()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.preflight()["current"], OLD)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.assert_old_unchanged()

    def test_depmod_failure_only_mutates_unpublished_staging_and_retries(self):
        payload(self.root, NEW)
        calls = []
        def fail_depmod(args):
            calls.append(args)
            self.assertEqual(args[:3], ["depmod", "-a", "-b"])
            self.assertEqual(args[4:6], ["-m", "/lib/modules"])
            staged = Path(args[3]) / "lib/modules" / NEW
            (staged / "modules.dep").write_text("partial index")
            raise subprocess.CalledProcessError(1, args)
        self.m.runner = fail_depmod
        with self.assertRaises(subprocess.CalledProcessError):
            self.m.activate(NEW)
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.m.modules / NEW).exists())
        self.assertEqual(list(self.m.modules.glob(".rock5t-modules-*")), [])
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.m.activate(NEW, self.initrd)
        self.assert_old_unchanged()

    def test_partial_initramfs_failure_preserves_selection_and_reuses_verified_modules(self):
        payload(self.root, NEW)
        def failing(args):
            if args[0] == "depmod":
                staged = Path(args[3]) / "lib/modules" / NEW
                (staged / "modules.dep.bin").write_bytes(b"synthetic regenerated index")
            else:
                Path(args[-1]).write_bytes(b"partial initramfs")
                raise subprocess.CalledProcessError(1, args)
        self.m.runner = failing
        with self.assertRaises(subprocess.CalledProcessError):
            self.m.activate(NEW)
        prepared = kernel.inventory(self.m.modules / NEW)
        self.assertFalse((self.m.generations / NEW).exists())
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        calls = []
        def retry(args):
            calls.append(args[0])
            self.assertEqual(args[0], "mkinitcpio")
            Path(args[-1]).write_bytes(b"synthetic successful initramfs")
        self.m.runner = retry
        self.m.activate(NEW)
        self.assertEqual(calls, ["mkinitcpio"])
        self.assertEqual(kernel.inventory(self.m.modules / NEW), prepared)
        self.assertEqual(self.m.preflight()["previous"], OLD)
        self.assert_old_unchanged()

    def test_retry_rejects_corrupt_published_modules_even_with_valid_source_marker(self):
        payload(self.root, NEW)
        self.kill("modules-published")
        (self.m.modules / NEW / "kernel/fixture.ko").write_bytes(b"corrupted after interrupted staging")
        with self.assertRaisesRegex(ValueError, "prepared module checksum mismatch"):
            self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.assertEqual(self.m.preflight()["current"], OLD)
        self.assert_old_unchanged()

    def test_mkinitcpio_mutation_of_published_modules_is_detected(self):
        payload(self.root, NEW)
        def mutating(args):
            if args[0] == "mkinitcpio":
                (self.m.modules / NEW / "kernel/fixture.ko").write_bytes(b"unexpected mutation")
                Path(args[-1]).write_bytes(b"synthetic initramfs")
        self.m.runner = mutating
        with self.assertRaisesRegex(ValueError, "prepared module checksum mismatch"):
            self.m.activate(NEW)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.assert_old_unchanged()

    def test_sigkill_at_commit_boundaries_is_retriable(self):
        for point in ("modules-published", "boot-staged", "generation-published", "backup-published", "menu-before-replace", "menu-after-replace"):
            with self.subTest(point=point):
                # Keep each interruption independent while using real process death.
                with tempfile.TemporaryDirectory(prefix="rock5t-kernel-crash-") as folder:
                    original_root, original_m, original_initrd = self.root, self.m, self.initrd
                    try:
                        shutil.copytree(self.root, folder, dirs_exist_ok=True)
                        self.root = Path(folder)
                        self.initrd = self.root / self.initrd.name
                        self.m = kernel.KernelManager(self.root, allow_unmounted=True)
                        payload(self.root, NEW)
                        self.kill(point)
                        expected = NEW if point == "menu-after-replace" else OLD
                        self.assertEqual(self.m.preflight()["current"], expected)
                        self.assert_old_unchanged()
                        self.cli("activate", "--release", NEW, "--initramfs", str(self.initrd))
                        self.assertEqual(self.m.preflight(), {"current": NEW, "previous": OLD})
                        self.assert_old_unchanged()
                        self.cli("rollback")
                        self.assertEqual(self.m.preflight(), {"current": OLD, "previous": NEW})
                    finally:
                        self.root, self.m, self.initrd = original_root, original_m, original_initrd

    def test_boot_copy_changed_after_manifest_validation_is_rejected(self):
        source = payload(self.root, NEW)
        copyfile = kernel.shutil.copyfile
        def changing(src, dst, *args, **kwargs):
            result = copyfile(src, dst, *args, **kwargs)
            if Path(src) == source / "Image":
                Path(dst).write_bytes(b"corrupted during copy")
            return result
        with patch.object(kernel.shutil, "copyfile", side_effect=changing):
            with self.assertRaisesRegex(ValueError, "copied boot payload checksum mismatch"):
                self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)

    def test_module_copy_changed_after_manifest_validation_is_rejected(self):
        payload(self.root, NEW)
        copytree = kernel.shutil.copytree
        def changing(src, dst, *args, **kwargs):
            result = copytree(src, dst, *args, **kwargs)
            if Path(src).name == "modules":
                (Path(dst) / "kernel/fixture.ko").write_bytes(b"bad copy")
            return result
        with patch.object(kernel.shutil, "copytree", side_effect=changing):
            with self.assertRaisesRegex(ValueError, "copied module payload checksum mismatch"):
                self.m.activate(NEW, self.initrd)
        self.assertFalse((self.m.modules / NEW).exists())
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)

    def test_full_root_aborts_without_switching(self):
        payload(self.root, NEW)
        usage = kernel.shutil.disk_usage
        def capacity(path):
            value = usage(path)
            return value._replace(free=0) if Path(path) == self.m.modules else value
        with patch.object(kernel.shutil, "disk_usage", side_effect=capacity):
            with self.assertRaisesRegex(RuntimeError, "root filesystem space"):
                self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.assert_old_unchanged()

    def test_failed_fsync_before_generation_publication_does_not_switch(self):
        payload(self.root, NEW)
        sync = kernel.sync_tree
        def fail(path):
            if Path(path).parent == self.m.generations:
                raise OSError(errno.EIO, "injected storage flush failure")
            sync(path)
        with patch.object(kernel, "sync_tree", side_effect=fail):
            with self.assertRaises(OSError):
                self.m.activate(NEW, self.initrd)
        self.assertFalse((self.m.generations / NEW).exists())
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        self.m.activate(NEW, self.initrd)
        self.assert_old_unchanged()

    def test_failed_menu_commit_keeps_old_selection_and_retries_complete_generation(self):
        payload(self.root, NEW)
        replace = kernel.os.replace
        def fail(src, dst):
            if Path(dst) == self.m.extlinux:
                raise OSError(errno.ENOSPC, "injected full boot filesystem at final commit")
            replace(src, dst)
        with patch.object(kernel.os, "replace", side_effect=fail):
            with self.assertRaises(OSError):
                self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)
        generation = self.snapshot(NEW)
        self.m.activate(NEW, self.initrd)
        self.assertEqual(self.snapshot(NEW), generation)
        self.assert_old_unchanged()

    def test_failed_flush_after_menu_replace_reports_failure_but_status_recovers_commit(self):
        payload(self.root, NEW)
        sync = kernel.sync_dir
        def fail(path):
            if Path(path) == self.m.extlinux.parent and self.m.state()["current"] == NEW:
                raise OSError(errno.EIO, "injected directory flush failure after commit")
            sync(path)
        with patch.object(kernel, "sync_dir", side_effect=fail):
            with self.assertRaises(OSError):
                self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.preflight(), {"current": NEW, "previous": OLD})
        self.m.activate(NEW, self.initrd)
        self.assert_old_unchanged()

    def test_rollback_still_works_when_current_boot_image_is_corrupt(self):
        self.install(NEW)
        (self.m.generations / NEW / "Image").write_bytes(b"damaged")
        self.assertEqual(self.m.select_previous(), {"current": OLD, "previous": None})
        self.assertEqual(self.m.preflight()["current"], OLD)
        self.assertNotIn(f"LINUX /rock5t/{NEW}/", self.m.extlinux.read_text())
        self.assertTrue((self.m.generations / NEW).is_dir())
        self.assert_old_unchanged()

    def test_rollback_still_works_when_current_modules_are_missing(self):
        self.install(NEW)
        shutil.rmtree(self.m.modules / NEW)
        self.assertEqual(self.m.select_previous(), {"current": OLD, "previous": None})
        self.m.preflight()
        self.assert_old_unchanged()

    def test_rollback_refuses_corrupt_previous(self):
        self.install(NEW)
        original = self.m.extlinux.read_bytes()
        (self.m.generations / OLD / "initramfs.img").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.m.select_previous()
        self.assertEqual(self.m.extlinux.read_bytes(), original)

    def test_managed_comment_alone_does_not_authorize_different_boot_paths(self):
        self.m.extlinux.write_text(self.m.extlinux.read_text().replace(f"LINUX /rock5t/{OLD}/Image", "LINUX /unrelated/Image"))
        with self.assertRaisesRegex(RuntimeError, "boot menu or kernel.json changed"):
            self.m.preflight()

    def test_generation_manifest_cannot_omit_required_boot_file(self):
        base = self.m.generations / OLD
        meta = json.loads((base / "generation.json").read_text())
        (base / "initramfs.img").unlink()
        del meta["boot_files"]["initramfs.img"]
        (base / "generation.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "must retain"):
            self.m.preflight()

    def test_same_files_with_different_selected_dtb_are_not_idempotent(self):
        source = payload(self.root, NEW)
        alternate = source / "dtbs/rockchip/other.dtb"
        alternate.write_bytes(bytes.fromhex("d00dfeed") + b"different board")
        write_manifest(source)
        self.m.activate(NEW, self.initrd)
        write_manifest(source, "rockchip/other.dtb")
        with self.assertRaisesRegex(ValueError, "different selected DTB"):
            self.m.activate(NEW, self.initrd)

    def test_same_kernel_with_different_explicit_initramfs_is_rejected(self):
        self.initrd.write_bytes(b"different synthetic initramfs")
        with self.assertRaisesRegex(ValueError, "different initramfs"):
            self.m.activate(OLD, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)

    def test_reserved_module_record_cannot_come_from_payload(self):
        source = payload(self.root, NEW)
        (source / "modules/.rock5t-files.json").write_text("{}")
        write_manifest(source)
        with self.assertRaisesRegex(ValueError, "reserved"):
            self.m.activate(NEW, self.initrd)

    def test_manifest_cannot_select_a_dtb_outside_the_payload(self):
        source = payload(self.root, NEW)
        write_manifest(source, "../../outside.dtb")
        with self.assertRaisesRegex(ValueError, "invalid DTB relative path"):
            self.m.activate(NEW, self.initrd)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)

    def test_manifest_dtb_path_must_be_canonical(self):
        source = payload(self.root, NEW)
        write_manifest(source, "rockchip/./rk3588-rock-5t.dtb")
        with self.assertRaisesRegex(ValueError, "invalid DTB relative path"):
            self.m.activate(NEW, self.initrd)

    def test_cli_malformed_manifest_fails_without_traceback_or_menu_change(self):
        source = payload(self.root, NEW)
        (source / "manifest.json").write_text("[]")
        result = self.cli("activate", "--release", NEW, "--initramfs", str(self.initrd), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid payload manifest", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.m.extlinux.read_bytes(), self.menu)

    def test_cli_lock_serializes_status_with_updates(self):
        lockdir = self.root / "run/lock"
        lockdir.mkdir(parents=True)
        with (lockdir / "rock5t-kernel.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            process = subprocess.Popen([sys.executable, str(SCRIPT), "status", "--root", str(self.root), "--allow-unmounted-boot"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                time.sleep(0.1)
                self.assertIsNone(process.poll())
                fcntl.flock(lock, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(json.loads(stdout)["current"], OLD)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_legacy_generation_without_new_module_record_remains_usable(self):
        module_record = self.m.modules / OLD / kernel.MODULE_FILES
        module_record.unlink()
        base = self.m.generations / OLD
        meta = json.loads((base / "generation.json").read_text())
        meta["modules_sha256"] = kernel.digest(kernel.inventory(self.m.modules / OLD))
        (base / "generation.json").write_text(json.dumps(meta))
        self.assertEqual(self.m.preflight()["current"], OLD)
        self.m.activate(OLD, self.initrd)
        self.install(NEW)
        self.assertEqual(self.m.select_previous()["current"], OLD)

    def test_hooks_cover_install_upgrade_remove_with_preflight_abort(self):
        directory = BASE / "rootfs/etc/pacman.d/hooks"
        pre = (directory / "10-rock5t-kernel-check.hook").read_text()
        post = (directory / "99-rock5t-kernel-activate.hook").read_text()
        for operation in ("Install", "Upgrade", "Remove"):
            self.assertIn("Operation = " + operation, pre)
        self.assertIn("When = PreTransaction", pre)
        self.assertIn("AbortOnFail", pre)
        self.assertIn("Exec = /usr/local/sbin/rock5t-kernel preflight", pre)
        self.assertIn("When = PostTransaction", post)
        self.assertNotIn("Operation = Remove", post)
        self.assertNotIn("AbortOnFail", post)
        self.assertNotIn("--allow-unmounted-boot", pre + post)


@unittest.skipUnless(os.environ.get("ROCK5T_REAL_PAYLOAD") and os.environ.get("ROCK5T_REAL_INITRAMFS"), "set both ROCK5T_REAL_* paths to exercise real previous-generation bytes")
class RealPayloadRetention(Fixture):
    def test_real_previous_generation_survives_synthetic_update_interruption_and_rollback(self):
        real_source = Path(os.environ["ROCK5T_REAL_PAYLOAD"]).resolve()
        real_initramfs = Path(os.environ["ROCK5T_REAL_INITRAMFS"]).resolve()
        release = kernel.check_release(real_source.name)
        self.assertNotEqual(release, NEW)
        before = kernel.inventory(real_source)
        shutil.copytree(real_source, self.m.payloads / release)
        self.m.activate(release, real_initramfs)
        previous = self.snapshot(release)
        source_manifest = json.loads((real_source / "manifest.json").read_text())
        self.assertEqual(previous["boot"]["Image"], source_manifest["files"]["Image"])
        self.assertEqual(previous["boot"]["board.dtb"], source_manifest["files"]["dtbs/" + source_manifest["dtb"]])
        self.assertEqual(previous["boot"]["initramfs.img"], kernel.sha256(real_initramfs))
        for path, value in source_manifest["files"].items():
            if path.startswith("modules/"):
                self.assertEqual(previous["modules"][path[len("modules/"):]], value)
        shutil.rmtree(self.m.payloads / release)
        payload(self.root, NEW)
        self.kill("generation-published")
        self.assertEqual(json.loads(self.cli("status").stdout)["current"], release)
        self.cli("activate", "--release", NEW, "--initramfs", str(self.initrd))
        self.assertEqual(self.m.preflight(), {"current": NEW, "previous": release})
        shutil.rmtree(self.m.payloads / NEW)
        self.cli("rollback")
        self.assertEqual(self.m.preflight(), {"current": release, "previous": NEW})
        self.assertEqual(self.snapshot(release), previous)
        self.assertEqual(kernel.inventory(real_source), before)
        print(f"\nReal-payload retention verified: {release}; {len(previous['modules'])} retained module-tree files. Replacement {NEW} is SYNTHETIC and was never booted.")


TWO_REAL_INPUTS = ("ROCK5T_REAL_PAYLOAD", "ROCK5T_REAL_INITRAMFS", "ROCK5T_NEXT_PAYLOAD", "ROCK5T_NEXT_QEMU_INITRAMFS")


@unittest.skipUnless(all(os.environ.get(key) for key in TWO_REAL_INPUTS), "set all four ROCK5T_REAL/NEXT_* paths for optional two-real-payload retention; run only after the new payload is declared ready")
class TwoRealPayloadRetention(Fixture):
    """Two real kernels, filesystem transitions only; no board boot claim.

    The old input is already in manager layout. The new input has boot/Image,
    boot/config-RELEASE, boot/System.map-RELEASE, boot/dtbs,
    usr/lib/modules/RELEASE and provenance.json. Its
    supplied initramfs must be explicitly identified as a QEMU test initramfs.
    Conversion writes only a disposable fixture, never an input or a package.

    Example, from the build directory AFTER payload readiness is confirmed:
      ROCK5T_REAL_PAYLOAD="$PWD/work/kernel-pkg/usr/lib/rock5t-kernel/6.18.44-current-rockchip64" \
      ROCK5T_REAL_INITRAMFS="$PWD/boot-cli/rock5t/6.18.44-current-rockchip64/initramfs.img" \
      ROCK5T_NEXT_PAYLOAD="$PWD/kernel-next/payload" \
      ROCK5T_NEXT_QEMU_INITRAMFS="$PWD/kernel-next/build/landlock-tests.cpio.gz" \
      PYTHONDONTWRITEBYTECODE=1 python3 overlay-work/tests/test_kernel_generations.py TwoRealPayloadRetention
    """
    # Use workspace disk, not the smaller /tmp tmpfs. TemporaryDirectory cleanup
    # runs on success or assertion failure; inputs are copied without hardlinks.
    temporary_parent = BASE / "tests/.tmp"

    def source_inventory(self, directory):
        result = {}
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory).as_posix()
            if path.is_symlink():
                result[relative] = {"symlink": os.readlink(path)}
            elif path.is_file():
                result[relative] = kernel.sha256(path)
            elif not path.is_dir():
                self.fail(f"nonregular real-payload input: {relative}")
        return result

    def verify_embedded_release(self, source, release):
        self.assertIn(b"Linux version " + release.encode() + b" ", (source / "Image").read_bytes(), "Image lacks the claimed real release banner")
        count = 0
        for path in sorted((source / "modules").rglob("*")):
            if path.suffix == ".ko":
                data = path.read_bytes()
            elif path.name.endswith(".ko.xz"):
                data = lzma.decompress(path.read_bytes())
            elif path.name.endswith(".ko.gz"):
                data = gzip.decompress(path.read_bytes())
            elif path.name.endswith(".ko.zst"):
                zstd = shutil.which("zstd")
                self.assertIsNotNone(zstd, "zstd must already be available to inspect compressed real module vermagic")
                data = subprocess.run([zstd, "-q", "-d", "-c", str(path)], check=True, capture_output=True).stdout
            else:
                continue
            self.assertEqual(data[:6], b"\x7fELF\x02\x01", f"not a little-endian ELF64 module: {path.name}")
            self.assertEqual(data[18:20], b"\xb7\x00", f"not an AArch64 module: {path.name}")
            self.assertIn(b"vermagic=" + release.encode() + b" ", data, f"module release differs: {path.name}")
            count += 1
        self.assertGreater(count, 0, "real payload contains no inspected kernel modules")
        return count

    def convert_next_payload(self, source):
        module_root = source / "usr/lib/modules"
        releases = [path for path in module_root.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")]
        self.assertEqual(len(releases), 1, "next payload must contain exactly one real module release")
        release = kernel.check_release(releases[0].name)
        self.assertTrue((releases[0] / "modules.dep").is_file(), "next payload is not ready: modules.dep is missing")
        provenance = json.loads((source / "provenance.json").read_text())
        self.assertIsInstance(provenance, dict, "next payload provenance must be an object")
        self.assertEqual(provenance.get("kernel_release"), release, "next provenance release mismatch")
        self.assertIsInstance(provenance.get("files"), dict, "next provenance needs a file inventory")
        for name, record in provenance["files"].items():
            self.assertFalse(Path(name).is_absolute() or ".." in Path(name).parts, "unsafe provenance path")
            path = source / name
            self.assertTrue(path.is_file() and not path.is_symlink(), f"missing/nonregular provenance input: {name}")
            self.assertEqual(path.stat().st_size, record["bytes"], f"provenance size mismatch: {name}")
            self.assertEqual(kernel.sha256(path), record["sha256"], f"provenance digest mismatch: {name}")
        destination = self.m.payloads / release
        destination.mkdir(parents=True)
        for origin, name in (("boot/Image", "Image"), (f"boot/config-{release}", "config"), (f"boot/System.map-{release}", "System.map"), ("provenance.json", "provenance.json")):
            path = source / origin
            self.assertTrue(path.is_file() and not path.is_symlink(), f"missing/nonregular next input: {origin}")
            shutil.copyfile(path, destination / name)
        # modules_install may create build/source development links. They are not
        # runtime modules; omit only those exact top-level symlinks. Any other
        # symlink remains a hard error from manager inventory validation.
        def omit_development_links(directory, names):
            if Path(directory) == releases[0]:
                return [name for name in ("build", "source") if name in names and (Path(directory) / name).is_symlink()]
            return []
        shutil.copytree(releases[0], destination / "modules", symlinks=True, ignore=omit_development_links)
        shutil.copytree(source / "boot/dtbs", destination / "dtbs", symlinks=True)
        self.assertTrue((destination / "dtbs" / DTB).is_file(), "next payload lacks the ROCK5T DTB")
        write_manifest(destination)
        return destination

    def assert_retained_payload(self, release, manifest, initramfs):
        actual = self.snapshot(release)
        self.assertEqual(actual["boot"]["Image"], manifest["files"]["Image"])
        self.assertEqual(actual["boot"]["board.dtb"], manifest["files"]["dtbs/" + manifest["dtb"]])
        self.assertEqual(actual["boot"]["initramfs.img"], kernel.sha256(initramfs))
        for path, value in manifest["files"].items():
            if path.startswith("modules/"):
                self.assertEqual(actual["modules"][path[len("modules/"):]], value)
        return actual

    def test_two_real_payloads_survive_interrupted_upgrade_and_bidirectional_rollback(self):
        old_input, old_initramfs, next_input, next_initramfs = [Path(os.environ[key]).resolve() for key in TWO_REAL_INPUTS]
        for path in (old_initramfs, next_initramfs):
            self.assertTrue(path.is_file() and path.stat().st_size > 0, f"missing initramfs input: {path}")
        before_old, before_next = self.source_inventory(old_input), self.source_inventory(next_input)
        old_initramfs_hash, next_initramfs_hash = kernel.sha256(old_initramfs), kernel.sha256(next_initramfs)
        # Account for the actual sequence: delete the old package fixture before
        # copying the new one. Rename publication does not duplicate staging.
        # Round each file to filesystem blocks, then reserve 64 MiB for directory
        # entries, module inventory records, temporary menu files and headroom.
        block = os.statvfs(self.root).f_frsize
        def allocated(path):
            members = path.rglob("*") if path.is_dir() else [path]
            return sum(((entry.stat().st_size + block - 1) // block) * block for entry in members if entry.is_file() and not entry.is_symlink())
        old_manifest_input = json.loads((old_input / "manifest.json").read_text())
        next_releases = [entry for entry in (next_input / "usr/lib/modules").iterdir() if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith(".")]
        self.assertEqual(len(next_releases), 1, "next payload must contain exactly one real module release")
        old_runtime = allocated(old_input / "modules") + allocated(old_input / "Image") + allocated(old_input / "dtbs" / old_manifest_input["dtb"]) + allocated(old_initramfs)
        next_runtime = allocated(next_releases[0]) + allocated(next_input / "boot/Image") + allocated(next_input / "boot/dtbs" / DTB) + allocated(next_initramfs)
        peak = max(allocated(old_input) + old_runtime, old_runtime + allocated(next_input) + next_runtime)
        required = peak + 64 * 1024**2
        free = shutil.disk_usage(self.root).free
        print("\nTwo-real-payload space budget: " + json.dumps({"estimated_peak_bytes": peak, "required_with_margin_bytes": required, "available_bytes": free, "shortfall_bytes": max(0, required - free)}, sort_keys=True), flush=True)
        self.assertGreaterEqual(free, required, f"insufficient workspace budget: need {required} bytes, have {free}, shortfall {max(0, required - free)}")
        old_release = kernel.check_release(old_input.name)
        old_source = self.m.payloads / old_release
        shutil.copytree(old_input, old_source, symlinks=True)
        old_modules = self.verify_embedded_release(old_source, old_release)
        old_manifest = json.loads((old_source / "manifest.json").read_text())
        self.cli("activate", "--release", old_release, "--initramfs", str(old_initramfs))
        old_snapshot = self.assert_retained_payload(old_release, old_manifest, old_initramfs)
        shutil.rmtree(old_source)

        next_source = self.convert_next_payload(next_input)
        next_release = next_source.name
        self.assertNotEqual(old_release, next_release, "two-real-payload test requires genuinely distinct embedded releases")
        next_modules = self.verify_embedded_release(next_source, next_release)
        next_manifest = json.loads((next_source / "manifest.json").read_text())
        self.assertNotEqual(old_manifest["files"]["Image"], next_manifest["files"]["Image"], "replacement Image is identical to the original")
        self.initrd = next_initramfs
        self.kill("modules-published", next_release)
        self.assertEqual(json.loads(self.cli("status").stdout), {"current": old_release, "previous": None})
        self.assertEqual(self.snapshot(old_release), old_snapshot)
        self.kill("generation-published", next_release)
        self.assertEqual(json.loads(self.cli("status").stdout), {"current": old_release, "previous": None})
        next_snapshot = self.assert_retained_payload(next_release, next_manifest, next_initramfs)
        self.cli("activate", "--release", next_release, "--initramfs", str(next_initramfs))
        self.assertEqual(self.m.preflight(), {"current": next_release, "previous": old_release})
        shutil.rmtree(next_source)
        self.cli("rollback")
        self.assertEqual(self.m.preflight(), {"current": old_release, "previous": next_release})
        self.cli("rollback")
        self.assertEqual(self.m.preflight(), {"current": next_release, "previous": old_release})
        self.assertEqual(self.snapshot(old_release), old_snapshot)
        self.assertEqual(self.snapshot(next_release), next_snapshot)
        self.assertEqual(self.source_inventory(old_input), before_old)
        self.assertEqual(self.source_inventory(next_input), before_next)
        self.assertEqual(kernel.sha256(old_initramfs), old_initramfs_hash)
        self.assertEqual(kernel.sha256(next_initramfs), next_initramfs_hash)
        print("\nTwo-real-payload offline retention passed: " + json.dumps({
            "old_release": old_release, "next_release": next_release,
            "old_real_module_count": old_modules, "next_real_module_count": next_modules,
            "old_Image_sha256": old_snapshot["boot"]["Image"],
            "next_Image_sha256": next_snapshot["boot"]["Image"],
            "next_initramfs_kind": "QEMU TEST ONLY; NOT A ROCK5T BOARD INITRAMFS",
            "verified": "embedded release identity, retained bytes, menu selection, SIGKILL/retry, bidirectional offline rollback",
            "not_verified": "kernel boot, real uname -r execution, pacman hooks, board initramfs or ROCK5T hardware",
        }, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--crash-worker":
        crash_worker(*sys.argv[2:])
    else:
        unittest.main(verbosity=2)
