"""Read-only evidence collector, invoked in the disposable guest after local sudo."""
import grp
import json
import os
from pathlib import Path
import platform
import pwd
import re
import subprocess
import termios


def run(*args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=120)
    return p.returncode, p.stdout.strip()


def read(path):
    return Path(path).read_text().strip()


def main():
    # Refuse to collect password/account state on the host or an unrelated VM.
    assert platform.machine() == "aarch64" and os.geteuid() == 0
    assert read("/etc/hostname") == "rock5t-vm-test"
    assert run("findmnt", "-n", "-o", "SOURCE", "/")[1] == "/dev/vda2"
    checks = {}
    for package in ('rtkit', 'wireless-regdb', 'iw'):
        checks['required_package_' + package] = run('pacman', '-Q', package)[0] == 0
    checks['iw_executable'] = run('iw', '--version')[0] == 0
    checks['wireless_regdb_payload'] = all(
        Path('/usr/lib/firmware/' + name).is_file()
        and Path('/usr/lib/firmware/' + name).stat().st_size > 0
        for name in ('regulatory.db', 'regulatory.db.p7s'))
    checks['rtkit_dbus_activation'] = run(
        'busctl', '--system', 'get-property', 'org.freedesktop.RealtimeKit1',
        '/org/freedesktop/RealtimeKit1', 'org.freedesktop.RealtimeKit1',
        'MaxRealtimePriority')[0] == 0
    details = {"uname": platform.release(), "hostname": read("/etc/hostname")}
    state = Path("/var/lib/rock5t")
    checks["provisioned_marker"] = (state / "provisioned").is_file()
    checks["provisioned_user"] = "user=vmcheck" in read(state / "provisioned").splitlines()
    checks["pending_user_removed"] = not (state / "pending-user").exists()
    checks["temporary_network_gate_removed"] = not Path("/run/rock5t-network-ready").exists()
    checks["expected_kernel"] = platform.release() == "6.18.44-current-rockchip64-landlock1"
    accounts = {p.pw_name: p for p in pwd.getpwall()}
    checks["alarm_removed"] = "alarm" not in accounts
    checks["administrator_nonroot"] = accounts["vmcheck"].pw_uid != 0
    checks["administrator_in_wheel"] = "vmcheck" in grp.getgrnam("wheel").gr_mem
    shadow = {line.split(":")[0]: line.split(":")[1]
              for line in Path("/etc/shadow").read_text().splitlines()}
    checks["root_locked"] = shadow["root"].startswith(("!", "*"))
    checks["administrator_password_set"] = bool(shadow["vmcheck"]) and not shadow["vmcheck"].startswith(("!", "*"))
    del shadow
    checks["hostname_applied"] = platform.node() == "rock5t-vm-test"
    checks["hosts_applied"] = "127.0.1.1 rock5t-vm-test" in read("/etc/hosts").splitlines()
    checks["machine_id_generated"] = bool(re.fullmatch(r"[0-9a-f]{32}", read("/etc/machine-id")))
    host_keys = [Path("/etc/ssh") / ("ssh_host_" + kind + "_key") for kind in ("rsa", "ecdsa", "ed25519")]
    checks["ssh_host_keys_generated_private"] = all(p.is_file() and (p.stat().st_mode & 0o777) == 0o600 for p in host_keys)
    choices = json.loads(read(state / "ssh-choices.json"))
    checks["ssh_choices_off_off"] = choices == {"user": "vmcheck", "start_now": False, "enable_boot": False, "password_login": False}
    details["ssh_service_active"] = run("systemctl", "is-active", "sshd.service")[1]
    details["ssh_service_enabled"] = run("systemctl", "is-enabled", "sshd.service")[1]
    checks["ssh_service_inactive"] = details["ssh_service_active"] == "inactive"
    checks["ssh_service_disabled"] = details["ssh_service_enabled"] == "disabled"
    checks["ssh_socket_inactive"] = run("systemctl", "is-active", "sshd.socket")[0] != 0
    ssh_result = subprocess.run(["sshd", "-T", "-C", "user=vmcheck,host=rock5t,addr=192.0.2.1"],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    code, effective = ssh_result.returncode, ssh_result.stdout.strip()
    details["ssh_T_exit"] = code
    details["ssh_T_stderr"] = ssh_result.stderr.strip()
    values = {}
    details["ssh_T_original_field_names"] = []
    for line in effective.splitlines():
        key, value = line.split(None, 1)
        if key.lower() in {"permitrootlogin", "passwordauthentication", "kbdinteractiveauthentication",
                           "permitemptypasswords", "authenticationmethods", "allowusers", "denyusers"}:
            details["ssh_T_original_field_names"].append(key)
        key = key.lower()
        values[key] = values.get(key, "") + " " + value
    details["ssh_T_selected_values"] = {k: v for k, v in values.items() if k.lower() in {
        "permitrootlogin", "passwordauthentication", "kbdinteractiveauthentication", "permitemptypasswords",
        "authenticationmethods", "allowusers", "denyusers"}}
    details["managed_ssh_policy"] = read("/etc/ssh/sshd_config.d/05-rock5t-access.conf")
    if code != 0:
        absolute = subprocess.run(["/usr/bin/sshd", "-T", "-C", "user=vmcheck,host=rock5t,addr=192.0.2.1"],
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        details["ssh_T_absolute_exit"] = absolute.returncode
        details["ssh_T_absolute_stderr"] = absolute.stderr.strip()
    checks["ssh_policy_valid"] = code == 0 and all(values.get(k, "").strip() == v for k, v in {
        "permitrootlogin": "no", "passwordauthentication": "no", "kbdinteractiveauthentication": "no",
        "permitemptypasswords": "no", "authenticationmethods": "publickey", "allowusers": "vmcheck"}.items())
    checks["ssh_root_alarm_denied"] = {"root", "alarm"}.issubset(values.get("denyusers", "").split())
    checks["no_user_authorized_keys"] = not Path("/home/vmcheck/.ssh/authorized_keys").exists()
    checks["sudoers_valid"] = run("visudo", "-c")[0] == 0
    sudo_rules = [line.strip() for line in read("/etc/sudoers.d/10-rock5t-wheel").splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
    checks["wheel_requires_sudo_password"] = sudo_rules == ["%wheel ALL=(ALL:ALL) ALL"]
    checks["package_secret_key_generated"] = "sec:" in run("gpg", "--homedir", "/etc/pacman.d/gnupg", "--batch", "--with-colons", "--list-secret-keys")[1]
    checks["both_package_keyrings_present"] = all(Path("/usr/share/pacman/keyrings/" + k + ".gpg").stat().st_size > 0 for k in ("archlinuxarm", "archlinux"))
    details["root_partition_sectors"] = int(read("/sys/class/block/vda2/size"))
    details["failed_units"] = run("systemctl", "--failed", "--no-legend", "--plain", "--no-pager")[1]
    details["firstboot_tty1"] = run("systemctl", "show", "rock5t-firstboot@tty1.service", "-p", "Result", "-p", "ExecMainStatus")[1]
    details["firstboot_ttyS2"] = run("systemctl", "show", "rock5t-firstboot@ttyS2.service", "-p", "Result", "-p", "ExecMainStatus")[1]
    checks["tty1_firstboot_success"] = "Result=success" in details["firstboot_tty1"] and "ExecMainStatus=0" in details["firstboot_tty1"]
    details["variant"] = read("/etc/rock5t/variant")
    details["kernel_cmdline"] = read("/proc/cmdline")
    details["plm_active"] = run("systemctl", "is-active", "plasmalogin.service")[1]
    details["plm_state"] = run("systemctl", "show", "plasmalogin.service", "-p", "ActiveState", "-p", "SubState", "-p", "Result", "-p", "ExecMainStatus", "-p", "NRestarts")[1]
    details["plm_journal"] = run("journalctl", "-b", "-u", "plasmalogin.service", "--no-pager", "-n", "100", "-o", "cat")[1]
    details["kwin_journal"] = run("journalctl", "-b", "_COMM=kwin_wayland", "--no-pager", "-n", "60", "-o", "cat")[1]
    details["display_manager_target"] = str(Path("/etc/systemd/system/display-manager.service").resolve())
    details["dri_nodes"] = sorted(str(p) for p in Path("/dev/dri").glob("*"))
    details["display_processes"] = run("pgrep", "-af", "plasmalogin|kwin_wayland")[1]
    checks["kde_variant"] = details["variant"] == "kde"
    checks["approved_rt_cmdline_preserved"] = "rt_group_sched=0" in details["kernel_cmdline"].split()
    checks["plm_service_active"] = details["plm_active"] == "active"
    checks["plm_is_display_manager"] = details["display_manager_target"] == "/usr/lib/systemd/system/plasmalogin.service"
    report = {"checks": checks, "details": details, "all_checks_pass": all(checks.values())}
    with open("/dev/ttyAMA0", "w") as output:
        output.write("\nFIRSTBOOT_VM_RESULT=" + json.dumps(report, sort_keys=True) + "\n")
        output.flush()
        termios.tcdrain(output.fileno())
    subprocess.run(["sync"], check=True)
    subprocess.run(["systemctl", "poweroff"], check=True)


if __name__ == "__main__":
    main()
