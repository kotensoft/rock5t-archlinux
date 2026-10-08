#!/usr/bin/env python3
"""Actual unmodified CLI image firstboot in an isolated ephemeral QEMU snapshot.

Run only after the builder declares all supplied image artifacts ready.
No network, host share, serial stdin, credential log, or global process cleanup.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import secrets
import shutil
import select
import stat
import struct
import subprocess
import time
import zlib

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent.parent
TOOLS = BUILD / "host-tools/root"
USER = "vmcheck"
HOSTNAME = "rock5t-vm-test"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def root_partition(path):
    with open(path, "rb") as f:
        f.seek(512)
        header = f.read(512)
        if header[:8] != b"EFI PART":
            raise ValueError("Completed raw GPT image required")
        entries_lba, count, size = struct.unpack_from("<QII", header, 72)
        if count < 2 or size < 128 or size > 4096:
            raise ValueError("Unexpected GPT partition layout")
        f.seek(entries_lba * 512 + size)
        entry = f.read(size)
        first, last = struct.unpack_from("<QQ", entry, 32)
        if first <= 0 or last < first or (last + 1) * 512 > path.stat().st_size:
            raise ValueError("Invalid root partition bounds")
        return {"index": 2, "first_lba": first, "last_lba": last, "sectors": last - first + 1}


def keycodes(char):
    special = {"\n": "ret", " ": "spc", "-": "minus", "=": "equal", "[": "bracket_left", "]": "bracket_right",
               ";": "semicolon", "'": "apostrophe", "`": "grave_accent", "\\": "backslash", ",": "comma", ".": "dot", "/": "slash"}
    shifted = dict(zip("!@#$%^&*()_+{}:\"~|<>?", "1234567890-=[];'`\\,./"))
    if "a" <= char <= "z" or "0" <= char <= "9":
        return [char]
    if "A" <= char <= "Z":
        return ["shift", char.lower()]
    if char in shifted:
        return ["shift", *keycodes(shifted[char])]
    if char in special:
        return [special[char]]
    raise ValueError("Unsupported keyboard character")


class QMP:
    def __init__(self, path, process):
        self.process = process
        self.input = os.open(str(path) + ".in", os.O_RDWR | os.O_NONBLOCK)
        self.output = os.open(str(path) + ".out", os.O_RDWR | os.O_NONBLOCK)
        self.buffer = b""
        greeting = json.loads(self.readline())
        if "QMP" not in greeting:
            raise RuntimeError("Invalid QMP greeting")
        self.call("qmp_capabilities")

    def readline(self):
        deadline = time.monotonic() + 30
        while b"\n" not in self.buffer:
            if self.process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("QMP FIFO closed or timed out")
            ready, _, _ = select.select([self.output], [], [], 1)
            if ready:
                self.buffer += os.read(self.output, 65536)
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line

    def call(self, command, args=None):
        request = {"execute": command}
        if args is not None:
            request["arguments"] = args
        # Never log the QMP stream: it contains disposable password keystrokes.
        os.write(self.input, json.dumps(request).encode() + b"\r\n")
        while True:
            raw = self.readline()
            if not raw:
                raise RuntimeError("QMP connection closed")
            result = json.loads(raw)
            if "error" in result:
                raise RuntimeError("QMP command failed: " + command)
            if "return" in result:
                return result["return"]

    def keys(self, codes):
        self.call("send-key", {"keys": [{"type": "qcode", "data": c} for c in codes], "hold-time": 12})
        time.sleep(.045)

    def type(self, text):
        for char in text:
            self.keys(keycodes(char))

    def close(self):
        os.close(self.input)
        os.close(self.output)


def environment(tmpdir):
    env = os.environ.copy()
    env.update(LD_LIBRARY_PATH=str(TOOLS / "usr/lib/x86_64-linux-gnu"),
               QEMU_MODULE_DIR=str(TOOLS / "usr/lib/x86_64-linux-gnu/qemu"),
               TMPDIR=str(tmpdir))
    return env


def check_host():
    config = (BUILD / "kernel-next/provenance/final-kernel.config").read_text()
    required = ["CONFIG_VT=y", "CONFIG_DRM_FBDEV_EMULATION=y", "CONFIG_FRAMEBUFFER_CONSOLE=y",
                "CONFIG_DRM_VIRTIO_GPU=m", "CONFIG_VIRTIO_INPUT=m"]
    assert all(line in config.splitlines() for line in required)
    help_text = subprocess.check_output([str(TOOLS / "usr/bin/qemu-system-aarch64"), "-device", "help"],
                                        env=environment(HERE), text=True)
    assert all('name "' + d + '"' in help_text for d in ("virtio-gpu-pci", "virtio-keyboard-pci", "virtio-rng-pci"))
    assert shutil.which("tesseract")
    for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" + " !@#$%^&*()_+-=[]{};:'\"`~\\|,<.>/?\n":
        keycodes(c)
    compile((HERE / "verify_guest.py").read_text(), "verify_guest.py", "exec")
    return {"required_kernel_config": required, "qemu_devices_available": True,
            "ocr_available": True, "keyboard_mapping_checked": True, "guest_collector_syntax_checked": True,
            "guest_boot_performed": False}


class Test:
    def __init__(self, args):
        self.args = args
        self.out = HERE / ("run-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
        self.out.mkdir(mode=0o700)
        self.tmp = self.out / "tmp"
        self.tmp.mkdir(mode=0o700)
        # The password stays exclusively in process memory and the guest snapshot.
        self.password = "V" + secrets.token_hex(14) + "q9"
        self.result = {"scope": "Generic QEMU ARM64 userspace only; no ROCK5T hardware, bootloader, DTB or peripherals tested", "status": "running", "stages": []}
        self.process = None
        self.qmp = None
        self.last_text = ""

    def stage(self, name):
        self.result["stages"].append({"name": name, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        (self.out / "result.json").write_text(json.dumps(self.result, indent=2) + "\n")
        print(name, flush=True)

    def screen(self, save=None):
        image = self.tmp / "current.ppm"
        ocr_image = self.tmp / "ocr.png"
        self.qmp.call("screendump", {"filename": str(image)})
        try:
            from PIL import Image, ImageOps
            with Image.open(image) as raw:
                prepared = ImageOps.invert(raw.convert("RGB"))
                prepared.resize((prepared.width * 2, prepared.height * 2), Image.Resampling.NEAREST).save(ocr_image)
            p = subprocess.run(["tesseract", str(ocr_image), "stdout", "--psm", "6"],
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
            text = p.stdout
            if self.password in text or self.password.lower() in text.lower():
                raise RuntimeError("Unexpected echoed credential; screenshot discarded")
            self.last_text = text
            (self.out / "last-screen.txt").write_text(text)
            if save:
                from PIL import Image
                with Image.open(image) as im:
                    im.save(self.out / (save + ".png"))
                (self.out / (save + ".txt")).write_text(text)
            return text
        finally:
            image.unlink(missing_ok=True)
            ocr_image.unlink(missing_ok=True)

    def wait_screen(self, pattern, name, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("QEMU exited while waiting for " + name)
            text = self.screen()
            overrides = HERE / "prompt-patterns.json"
            current_pattern = json.loads(overrides.read_text()).get(name, pattern) if overrides.exists() else pattern
            if re.search(current_pattern, text, re.I):
                self.screen(save=name)
                self.stage(name)
                return text
            time.sleep(2)
        self.screen(save="blocked-" + name)
        raise RuntimeError("Timed out waiting for " + name)

    def line(self, text=""):
        self.qmp.type(text + "\n")
        time.sleep(.35)

    def launch(self):
        a = self.args
        self.result["image"] = str(a.image)
        self.result["root_partition"] = root_partition(a.image)
        self.stage("hashing_inputs")
        self.result["sha256_before"] = {"image": sha256(a.image), "kernel": sha256(a.kernel), "initrd": sha256(a.initrd)}
        command = [str(TOOLS / "usr/bin/qemu-system-aarch64"), "-M", "virt", "-cpu", "cortex-a72", "-accel", "tcg",
                   "-m", "2048", "-smp", "2", "-nodefaults", "-display", "none", "-nic", "none",
                   "-L", str(TOOLS / "usr/share/qemu"), "-serial", "file:serial.log", "-monitor", "none",
                   "-qmp", "pipe:qmp", "-kernel", str(a.kernel), "-initrd", str(a.initrd),
                   "-append", "root=/dev/vda2 rootfstype=ext4 rw rootwait console=ttyAMA0,115200 console=tty1 loglevel=4 systemd.show_status=false",
                   "-snapshot", "-drive", "if=none,id=image,file=" + str(a.image) + ",format=raw",
                   "-device", "virtio-blk-pci,drive=image", "-device", "virtio-gpu-pci,xres=1280,yres=800",
                   "-device", "virtio-keyboard-pci", "-object", "rng-random,id=rng0,filename=/dev/urandom",
                   "-device", "virtio-rng-pci,rng=rng0", "-no-reboot"]
        self.result["qemu_command"] = command
        # Snapshot writes cannot exceed 768 MiB, leaving room within the 1 GiB budget.
        def limits():
            resource.setrlimit(resource.RLIMIT_FSIZE, (768 << 20, 768 << 20))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        for suffix in ("in", "out"):
            os.mkfifo(self.out / ("qmp." + suffix), mode=0o600)
        with open(self.out / "qemu.log", "wb") as output:
            self.process = subprocess.Popen(command, cwd=self.out, env=environment(self.tmp), stdin=subprocess.DEVNULL,
                                            stdout=output, stderr=subprocess.STDOUT, preexec_fn=limits)
        self.qmp = QMP(self.out / "qmp", self.process)
        self.result["qemu_blocks"] = self.qmp.call("query-block")
        self.stage("boot_started_snapshot_only")

    def execute(self):
        self.launch()
        self.wait_screen(r"Press Enter to set up", "01-firstboot-prompt", timeout=300)
        self.line()
        self.wait_screen(r"New administrator username", "02-username-prompt")
        self.line(USER)
        self.wait_screen(r"New password:", "03-password-prompt")
        self.line(self.password)
        self.wait_screen(r"Retype new password:", "04-repeat-password-prompt")
        self.line(self.password)
        self.wait_screen(r"Hostname\s*\[", "05-hostname-prompt")
        self.line(HOSTNAME)
        self.wait_screen(r"Configure Wi.?Fi now", "06-wifi-prompt", timeout=900)
        self.line("n")
        self.wait_screen(r"Start SSH when setup finishes", "07-ssh-current-prompt")
        self.line("n")
        self.wait_screen(r"Start SSH automatically on future boots", "08-ssh-boot-prompt")
        self.line("n")
        self.wait_screen(r"Expand\s*\[y/N\]", "09-root-expand-prompt")
        self.line("n")
        self.wait_screen(r"Setup complete|login:", "10-provisioning-complete", timeout=300)
        try:
            self.wait_screen(r"login:", "11-login-prompt", timeout=150)
        except RuntimeError as error:
            if "Timed out" not in str(error):
                raise
            self.qmp.keys(["ctrl", "alt", "f2"])
            self.wait_screen(r"login:", "11-login-prompt-tty2", timeout=60)
        self.line(USER)
        self.wait_screen(r"Password:", "12-login-password-prompt")
        self.line(self.password)
        self.wait_screen(r"vmcheck@rock[5s]+t-vm-test", "13-administrator-login")
        self.line("sudo -v")
        self.wait_screen(r"password for vmcheck", "14-sudo-password-prompt")
        self.line(self.password)
        time.sleep(2)
        # A unique marker detects a missing/wrong sudo password without false matching an older prompt.
        self.line("sudo -n true && printf '\\nLOCAL_SUDO_READY\\n'")
        self.wait_screen(r"(?m)^LOCAL_SUDO_READY\s*$", "15-sudo-login-ready")
        source = (HERE / "verify_guest.py").read_bytes()
        payload = base64.b64encode(zlib.compress(source, 9)).decode()
        command = "sudo -n python3 -c 'import base64,zlib;exec(zlib.decompress(base64.b64decode(\"" + payload + "\")))'"
        self.line(command)
        self.stage("16-verifying-guest-defaults")
        deadline = time.monotonic() + 240
        serial = self.out / "serial.log"
        while time.monotonic() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            match = re.search(r"FIRSTBOOT_VM_RESULT=(\{[^\r\n]+\})", text)
            if match:
                self.result["guest"] = json.loads(match.group(1))
                break
            if self.process.poll() is not None:
                raise RuntimeError("VM exited without a guest verification result")
            time.sleep(2)
        else:
            self.screen(save="blocked-guest-verification")
            raise RuntimeError("Guest verification result not observed on read-only serial output")
        expected = self.result["root_partition"]["sectors"]
        actual = self.result["guest"]["details"]["root_partition_sectors"]
        self.result["guest"]["checks"]["root_partition_not_expanded"] = actual == expected
        self.result["guest"]["all_checks_pass"] = all(self.result["guest"]["checks"].values())
        self.process.wait(timeout=90)
        self.result["status"] = "passed" if self.result["guest"]["all_checks_pass"] else "failed_checks"
        self.stage("17-guest-poweroff-and-verification-finished")

    def cleanup(self):
        if self.process is not None and self.process.poll() is None:
            try:
                if self.qmp:
                    self.qmp.call("quit")
                self.process.wait(timeout=15)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
        if self.qmp:
            self.qmp.close()
        if "sha256_before" in self.result:
            self.result["image_sha256_after"] = sha256(self.args.image)
            self.result["base_image_unchanged"] = self.result["image_sha256_after"] == self.result["sha256_before"]["image"]
            if not self.result["base_image_unchanged"]:
                self.result["status"] = "failed_base_image_changed"
        self.password = None
        # These paths belong to this run only. No PID searches or global cleanup.
        shutil.rmtree(self.tmp)
        for suffix in ("in", "out"):
            (self.out / ("qmp." + suffix)).unlink(missing_ok=True)
        self.result["snapshot_destroyed"] = self.process is None or self.process.poll() is not None
        self.result["qemu_returncode"] = None if self.process is None else self.process.returncode
        (self.out / "result.json").write_text(json.dumps(self.result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-host", action="store_true")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--initrd", type=Path)
    parser.add_argument("--ready", action="store_true", help="Confirm the builder has completed these artifacts")
    args = parser.parse_args()
    host = check_host()
    if args.check_host:
        print(json.dumps(host, indent=2))
        return 0
    if not args.ready or any(getattr(args, k) is None for k in ("image", "kernel", "initrd")):
        parser.error("--ready and completed --image, --kernel, --initrd paths are required")
    for name in ("image", "kernel", "initrd"):
        path = getattr(args, name).resolve(strict=True)
        if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size == 0:
            parser.error("Inputs must be nonempty regular files, never physical block devices")
        setattr(args, name, path)
    test = Test(args)
    try:
        test.execute()
    except Exception as error:
        test.result["status"] = "blocked"
        test.result["blocker"] = str(error)
        print("Test blocked: " + str(error), flush=True)
    finally:
        test.cleanup()
    print("Result: " + str(test.out / "result.json"), flush=True)
    return 0 if test.result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
