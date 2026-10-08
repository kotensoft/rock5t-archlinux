#!/usr/bin/env python3
"""Mock-only firstboot/Wi-Fi/SSH regression tests. Never change host services."""
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / 'rootfs/usr/local/sbin'


def module(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(SCRIPTS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    loaded = importlib.util.module_from_spec(spec)
    loader.exec_module(loaded)
    return loaded


network = module('rock5t-configure-network')
ssh = module('rock5t-configure-ssh')


def result(code=0, stdout=''):
    return SimpleNamespace(returncode=code, stdout=stdout)


class NetworkTests(unittest.TestCase):
    def configure(self, answers, devices='wlan0:wifi\neth0:ethernet\n', failures=None):
        calls = []
        remaining = list(failures or [])
        def runner(args, capture=False):
            calls.append((args, capture))
            if args[-2:] == ['device', 'status']:
                return result(stdout=devices)
            if remaining and remaining[0](args):
                remaining.pop(0)
                return result(1)
            return result()
        answers = iter(answers)
        with patch('builtins.print'):
            network.configure(runner, lambda prompt: next(answers))
        return calls

    def test_skip_does_not_touch_network_state(self):
        self.assertEqual(self.configure(['']), [])

    def test_scan_then_connect_uses_hidden_secret_prompt(self):
        calls = self.configure(['yes', '', 'Home Wi-Fi'])
        self.assertTrue(any(args[-2:] == ['--rescan', 'yes'] for args, _ in calls))
        connect, capture = next((args, capture) for args, capture in calls if 'connect' in args)
        self.assertEqual(connect, ['nmcli', '--ask', '--colors', 'no', '--wait', '90', 'device', 'wifi',
                                   'connect', 'Home Wi-Fi', 'ifname', 'wlan0', 'hidden', 'no'])
        self.assertFalse(capture)
        self.assertNotIn('password', connect)
        self.assertNotIn('--show-secrets', connect)

    def test_hidden_ssid_and_special_characters_are_one_argument(self):
        calls = self.configure(['y', 'hidden', 'Space " $(not-a-shell)'])
        connect = next(args for args, _ in calls if 'connect' in args)
        self.assertIn('Space " $(not-a-shell)', connect)
        self.assertEqual(connect[-2:], ['hidden', 'yes'])
        self.assertFalse(any('list' in args for args, _ in calls))

    def test_connection_failure_can_retry(self):
        calls = self.configure(['y', 's', 'Wrong', 'r', 'h', 'Correct'],
                               failures=[lambda args: 'connect' in args])
        self.assertEqual(sum('connect' in args for args, _ in calls), 2)

    def test_failed_connection_can_be_skipped(self):
        calls = self.configure(['y', 's', 'Failed', 's'], failures=[lambda args: 'connect' in args])
        self.assertEqual(sum('connect' in args for args, _ in calls), 1)
        self.assertFalse(any('stop' in args or 'off' in args for args, _ in calls))

    def test_no_wifi_adapter_can_skip(self):
        calls = self.configure(['y', 's'], devices='eth0:ethernet\n')
        self.assertFalse(any('connect' in args for args, _ in calls))

    def test_service_failure_can_skip(self):
        calls = self.configure(['y', 's'], failures=[lambda args: args[0] == 'systemctl'])
        self.assertEqual(len(calls), 1)

    def test_scan_failure_can_skip(self):
        calls = self.configure(['y', 's', 's'], failures=[lambda args: 'list' in args])
        self.assertFalse(any('connect' in args for args, _ in calls))

    def test_invalid_multiple_interface_choice_is_retried(self):
        calls = self.configure(['y', 'not-a-device', 'wlan1', 'h', 'SSID'], devices='wlan0:wifi\nwlan1:wifi\n')
        connect = next(args for args, _ in calls if 'connect' in args)
        self.assertIn('wlan1', connect)
        self.assertNotIn('not-a-device', connect)

    def test_ssid_length_and_controls_are_rejected(self):
        calls = self.configure(['y', 'h', 'a'*33, 'h', 'tab\tname', 'h', 'Good'])
        connects = [args for args, _ in calls if 'connect' in args]
        self.assertEqual(len(connects), 1)
        self.assertIn('Good', connects[0])

    def test_escaped_terse_device_names(self):
        self.assertEqual(network.escaped_fields(r'wl\:an\\0:wifi'), ['wl:an\\0', 'wifi'])

    def test_firstboot_rejects_pty_and_requires_temporary_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed, ready = Path(tmp)/'complete', Path(tmp)/'ready'
            with patch.object(network.os, 'geteuid', return_value=0), \
                 patch.object(network.sys.stdin, 'isatty', return_value=True), \
                 patch.object(network.sys.stdout, 'isatty', return_value=True), \
                 patch.object(network.sys.stderr, 'isatty', return_value=True), \
                 patch.object(network.os, 'ttyname', return_value='/dev/pts/0'):
                with self.assertRaisesRegex(RuntimeError, 'tty1 or ttyS2'):
                    network.require_terminal(True, completed, ready)
            with patch.object(network.os, 'geteuid', return_value=0), \
                 patch.object(network.sys.stdin, 'isatty', return_value=True), \
                 patch.object(network.sys.stdout, 'isatty', return_value=True), \
                 patch.object(network.sys.stderr, 'isatty', return_value=True), \
                 patch.object(network.os, 'ttyname', return_value='/dev/ttyS2'):
                with self.assertRaisesRegex(RuntimeError, 'not ready'):
                    network.require_terminal(True, completed, ready)
                ready.touch()
                network.require_terminal(True, completed, ready)
                completed.touch()
                with self.assertRaisesRegex(RuntimeError, 'not ready'):
                    network.require_terminal(True, completed, ready)
                network.require_terminal(False, completed, ready)

    def test_redirected_output_is_refused(self):
        with patch.object(network.os, 'geteuid', return_value=0), \
             patch.object(network.sys.stdin, 'isatty', return_value=True), \
             patch.object(network.sys.stdout, 'isatty', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'redirect'):
                network.require_terminal()


class SSHTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calls = []
        self.insecure = False
        self.fail_enable = False
        self.socket_enabled = False
        self.manager = ssh.SSHManager(self.root, self.runner, lambda name: SimpleNamespace(pw_uid=1000))
        self.choices = {'user': 'alice', 'start_now': False, 'enable_boot': False, 'password_login': False}

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, args, capture=False):
        self.calls.append(args)
        if args[:2] == ['sshd', '-T']:
            config = self.manager.config.read_text()
            lines = [line.lower() for line in config.splitlines() if line and not line.startswith('#')]
            output = '\n'.join(lines).replace('denyusers root alarm', 'denyusers root\ndenyusers alarm')
            if self.insecure:
                output = output.replace('permitrootlogin no', 'permitrootlogin yes')
            return result(stdout=output)
        if args[:2] == ['systemctl', 'is-enabled']:
            return result(0 if self.socket_enabled else 1, 'enabled\n' if self.socket_enabled else 'not-found\n')
        if args == ['systemctl', 'is-active', 'sshd.socket']:
            return result(0 if self.socket_enabled else 3, 'active' if self.socket_enabled else 'inactive')
        if self.fail_enable and args[:2] == ['systemctl', 'enable']:
            return result(1)
        return result()

    def provision(self):
        self.manager.provisioned.parent.mkdir(parents=True, exist_ok=True)
        self.manager.provisioned.write_text('user=alice\ncreated=testing\n')

    def test_all_no_defaults(self):
        answers = iter(['', ''])
        with patch('builtins.print'):
            self.assertEqual(ssh.choose('alice', lambda prompt: next(answers)), self.choices)

    def test_password_requires_explicit_choice(self):
        answers = iter(['y', 'n', ''])
        with patch('builtins.print'):
            choices = ssh.choose('alice', lambda prompt: next(answers))
        self.assertTrue(choices['start_now'])
        self.assertFalse(choices['password_login'])
        answers = iter(['y', 'yes', 'yes'])
        with patch('builtins.print'):
            choices = ssh.choose('alice', lambda prompt: next(answers))
        self.assertTrue(choices['password_login'])

    def test_firstboot_stage_persists_but_never_starts_sshd(self):
        self.choices.update(start_now=True, enable_boot=True, password_login=True)
        self.manager.configure(self.choices, staged=True)
        self.assertEqual(json.loads(self.manager.choices_path.read_text()), self.choices)
        self.assertIn(['systemctl', 'enable', 'sshd.service'], self.calls)
        self.assertFalse(any('reload-or-restart' in args or 'start' in args for args in self.calls))
        self.assertEqual(self.manager.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.manager.choices_path.stat().st_mode & 0o777, 0o600)
        self.assertIn('PermitRootLogin no', self.manager.config.read_text())
        self.assertIn('AllowUsers alice', self.manager.config.read_text())
        self.assertIn('AuthenticationMethods publickey password', self.manager.config.read_text())
        self.assertFalse(list(self.manager.config.parent.glob('.rock5t-ssh-*')))

    def test_current_start_is_blocked_until_marker(self):
        self.choices.update(start_now=True)
        with self.assertRaisesRegex(RuntimeError, 'before local provisioning'):
            self.manager.configure(self.choices)
        with self.assertRaisesRegex(RuntimeError, 'before local provisioning'):
            self.manager.set_current(self.choices)
        self.assertEqual(self.calls, [])

    def test_apply_checks_marker_user_before_start(self):
        self.choices.update(start_now=True)
        self.manager.configure(self.choices, staged=True)
        self.provision()
        self.manager.provisioned.write_text('user=bob\n')
        with self.assertRaisesRegex(RuntimeError, 'do not match'):
            self.manager.apply_firstboot()
        self.assertNotIn(['systemctl', 'reload-or-restart', 'sshd.service'], self.calls)

    def test_apply_starts_only_after_provisioning(self):
        self.choices.update(start_now=True)
        self.manager.configure(self.choices, staged=True)
        self.provision()
        self.manager.apply_firstboot()
        self.assertIn(['systemctl', 'reload-or-restart', 'sshd.service'], self.calls)
        self.assertIn(['systemctl', 'is-active', '--quiet', 'sshd.service'], self.calls)

    def test_boot_only_does_not_start_current_service(self):
        self.choices.update(enable_boot=True)
        self.provision()
        self.manager.configure(self.choices)
        self.assertIn(['systemctl', 'enable', 'sshd.service'], self.calls)
        self.assertIn(['systemctl', 'stop', 'sshd.service'], self.calls)
        self.assertNotIn(['systemctl', 'reload-or-restart', 'sshd.service'], self.calls)

    def test_now_only_does_not_enable_future_boots(self):
        self.choices.update(start_now=True)
        self.provision()
        self.manager.configure(self.choices)
        self.assertIn(['systemctl', 'disable', 'sshd.service'], self.calls)
        self.assertIn(['systemctl', 'reload-or-restart', 'sshd.service'], self.calls)

    def test_no_disables_both_and_keeps_key_only_policy(self):
        self.provision()
        self.manager.configure(self.choices)
        self.assertIn(['systemctl', 'disable', 'sshd.service'], self.calls)
        self.assertIn(['systemctl', 'stop', 'sshd.service'], self.calls)
        self.assertIn('PasswordAuthentication no', self.manager.config.read_text())

    def test_existing_socket_activation_is_disabled(self):
        self.socket_enabled = True
        self.provision()
        self.manager.configure(self.choices)
        self.assertIn(['systemctl', 'disable', '--now', 'sshd.socket'], self.calls)

    def test_policy_conflict_restores_previous_file_and_never_enables(self):
        self.manager.config.parent.mkdir(parents=True)
        self.manager.config.write_text('# previous safe policy\n')
        self.insecure = True
        with self.assertRaisesRegex(RuntimeError, 'conflicts'):
            self.manager.configure(self.choices, staged=True)
        self.assertEqual(self.manager.config.read_text(), '# previous safe policy\n')
        self.assertFalse(any(args[0] == 'systemctl' for args in self.calls))
        self.assertFalse(self.manager.choices_path.exists())

    def test_policy_conflict_removes_new_file(self):
        self.insecure = True
        with self.assertRaises(RuntimeError):
            self.manager.configure(self.choices, staged=True)
        self.assertFalse(self.manager.config.exists())

    def test_boot_enable_failure_is_not_recorded_as_success(self):
        self.fail_enable = True
        self.choices.update(enable_boot=True)
        with self.assertRaises(RuntimeError):
            self.manager.configure(self.choices, staged=True)
        self.assertFalse(self.manager.choices_path.exists())

    def test_invalid_users_and_boolean_strings_are_rejected(self):
        for user in ('root', 'alarm', 'alice\nPermitRootLogin yes', 'UPPER', '-option'):
            with self.assertRaises(ValueError):
                ssh.validate_choices(dict(self.choices, user=user), lambda name: SimpleNamespace(pw_uid=1000))
        with self.assertRaises(ValueError):
            ssh.validate_choices(dict(self.choices, start_now='false'), lambda name: SimpleNamespace(pw_uid=1000))
        with self.assertRaises(ValueError):
            ssh.validate_choices(self.choices, lambda name: SimpleNamespace(pw_uid=0))

    def test_offline_default_runner_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'mocked command runner'):
            ssh.SSHManager(self.root)


MOCK = r'''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['FAKE_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root/'commands.jsonl').open('a') as log:
    log.write(json.dumps([name]+args)+'\n')
state = root/'state'
if name == 'tty':
    print('/dev/tty1')
elif name == 'getent':
    if not (root/'account').exists(): sys.exit(2)
    print('alice:x:1000:1000::/home/alice:/bin/bash')
elif name == 'useradd':
    (root/'account').touch()
elif name == 'pacman-key' and args == ['--populate', 'archlinuxarm', 'archlinux'] and os.environ.get('FAIL_TRUST') == '1':
    sys.exit(1)
elif name == 'rock5t-configure-network':
    assert (root/'network-ready').exists()
    assert not (state/'provisioned').exists()
    if os.environ.get('FAIL_NETWORK') == '1': sys.exit(130)
elif name == 'rock5t-configure-ssh':
    if args[0] == '--firstboot-stage': assert not (state/'provisioned').exists()
    if args[0] == '--apply-firstboot': assert (state/'provisioned').exists()
'''


class FirstbootShellTests(unittest.TestCase):
    """Execute firstboot with every system-changing command replaced by a mock."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root/'bin'
        self.bin.mkdir()
        for command in ('tty', 'getent', 'useradd', 'usermod', 'passwd', 'hostnamectl',
                        'systemd-machine-id-setup', 'ssh-keygen', 'pacman-key', 'visudo',
                        'nmcli', 'systemctl', 'rock5t-configure-network', 'rock5t-configure-ssh',
                        'rock5t-grow-root'):
            (self.bin/command).write_text(MOCK)
            (self.bin/command).chmod(0o755)
        keyrings = self.root/'keyrings'
        keyrings.mkdir()
        for name in ('archlinuxarm.gpg', 'archlinux.gpg'):
            (keyrings/name).write_text('test-only public keyring')
        source = (SCRIPTS/'rock5t-firstboot').read_text()
        replacements = {
            'export PATH=/usr/bin:/usr/sbin': f'export PATH={self.bin}:/usr/bin:/usr/sbin',
            '/var/lib/rock5t': str(self.root/'state'),
            '/run/rock5t-network-ready': str(self.root/'network-ready'),
            '/run/rock5t-firstboot.lock': str(self.root/'firstboot.lock'),
            '/usr/local/sbin/': str(self.bin)+'/',
            '/usr/share/pacman/keyrings': str(keyrings),
            '/etc/hostname': str(self.root/'hostname'),
            '/etc/hosts': str(self.root/'hosts'),
            '/etc/sudoers.d/10-rock5t-wheel': str(self.root/'sudoers'),
        }
        for old, new in replacements.items():
            self.assertIn(old, source)
            source = source.replace(old, new)
        # A guard catches new absolute writes introduced into the production script.
        self.assertNotIn('> /etc/', source)
        self.assertNotIn('/var/lib/rock5t', source)
        self.script = self.root/'firstboot'
        self.script.write_text(source)
        self.env = dict(os.environ, FAKE_ROOT=str(self.root))

    def tearDown(self):
        self.temp.cleanup()

    def run_setup(self, text='\nalice\nrock-test\nn\n', **flags):
        return subprocess.run(['/usr/bin/bash', str(self.script), 'tty1'], input=text,
                              text=True, capture_output=True, env=dict(self.env, **flags), timeout=15)

    def calls(self):
        return [json.loads(line) for line in (self.root/'commands.jsonl').read_text().splitlines()]

    def test_complete_orders_secure_identity_network_ssh_and_commit(self):
        outcome = self.run_setup()
        self.assertEqual(outcome.returncode, 0, outcome.stdout+outcome.stderr)
        self.assertTrue((self.root/'state/provisioned').exists())
        self.assertFalse((self.root/'state/pending-user').exists())
        self.assertFalse((self.root/'network-ready').exists())
        calls = self.calls()
        network_pos = calls.index(['rock5t-configure-network', '--firstboot'])
        self.assertLess(calls.index(['passwd', 'alice']), network_pos)
        self.assertLess(calls.index(['pacman-key', '--populate', 'archlinuxarm', 'archlinux']), network_pos)
        self.assertLess(calls.index(['visudo', '-cf', str(self.root/'sudoers')]), network_pos)
        self.assertLess(network_pos, calls.index(['rock5t-configure-ssh', '--firstboot-stage', 'alice']))
        self.assertIn(['rock5t-configure-ssh', '--apply-firstboot'], calls)
        self.assertIn(['systemctl', '--no-block', 'start', 'rock5t-provisioned.target'], calls)

    def test_interrupted_trust_reuses_pending_user_and_resets_password(self):
        first = self.run_setup(FAIL_TRUST='1')
        self.assertNotEqual(first.returncode, 0)
        self.assertTrue((self.root/'state/pending-user').exists())
        self.assertFalse((self.root/'state/provisioned').exists())
        self.assertFalse(any(call[0] == 'rock5t-configure-network' for call in self.calls()))
        second = self.run_setup('\nrock-retry\nn\n')
        self.assertEqual(second.returncode, 0, second.stdout+second.stderr)
        self.assertEqual(sum(call[0] == 'useradd' for call in self.calls()), 1)
        self.assertEqual(self.calls().count(['usermod', '--lock', 'alice']), 2)
        self.assertEqual(self.calls().count(['passwd', 'alice']), 2)

    def test_interrupted_network_closes_gate_and_retry_restores_networking(self):
        first = self.run_setup(FAIL_NETWORK='1')
        self.assertEqual(first.returncode, 130, first.stdout+first.stderr)
        self.assertFalse((self.root/'network-ready').exists())
        self.assertFalse((self.root/'state/provisioned').exists())
        self.assertIn(['nmcli', '--wait', '10', 'networking', 'off'], self.calls())
        self.assertIn(['systemctl', 'stop', 'NetworkManager.service'], self.calls())
        second = self.run_setup('\n\nn\n')
        self.assertEqual(second.returncode, 0, second.stdout+second.stderr)
        self.assertIn(['nmcli', '--wait', '15', 'networking', 'on'], self.calls())

    def test_stale_gate_is_closed_before_account_is_locked(self):
        (self.root/'network-ready').touch()
        outcome = self.run_setup()
        self.assertEqual(outcome.returncode, 0, outcome.stdout+outcome.stderr)
        calls = self.calls()
        self.assertLess(calls.index(['nmcli', '--wait', '10', 'networking', 'off']),
                        calls.index(['usermod', '--lock', 'alice']))

    def test_completed_device_does_not_change_network_or_account(self):
        (self.root/'state').mkdir()
        (self.root/'state/provisioned').write_text('user=alice\n')
        outcome = self.run_setup('')
        self.assertEqual(outcome.returncode, 0)
        self.assertFalse((self.root/'commands.jsonl').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
