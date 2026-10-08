#!/usr/bin/env python3
import hashlib,json,os,pathlib,subprocess
B=pathlib.Path('/mnt/host'); K='6.18.44-current-rockchip64-landlock1'; results={}
def run(*args):return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for variant in ('cli','kde'):
 r=pathlib.Path('/mnt')/variant; checks={}
 def check(name,value):
  checks[name]=bool(value)
  if not value:raise RuntimeError(f'{variant}: {name}')
 check('root_locked',any(l.startswith('root:!:') for l in (r/'etc/shadow').read_text().splitlines()))
 check('factory_account_absent',not any(l.startswith(('alarm:','sddm:')) for l in (r/'etc/passwd').read_text().splitlines()))
 check('empty_machine_id',(r/'etc/machine-id').read_bytes()==b'')
 for p in ('etc/pacman.d/gnupg','var/lib/rock5t/provisioned','var/lib/rock5t/pending-user','var/lib/rock5t/ssh-choices.json','etc/ssh/sshd_config.d/05-rock5t-access.conf','var/lib/systemd/random-seed','var/lib/NetworkManager/secret_key'):
  check('no_'+p,not (r/p).exists())
 check('no_host_private_keys',not list((r/'etc/ssh').glob('ssh_host_*')))
 check('no_saved_wifi',not list((r/'etc/NetworkManager/system-connections').iterdir()))
 check('no_home_accounts',not list((r/'home').iterdir()))
 check('no_debug_root_keys',not (r/'root/.ssh').exists())
 for p in [r/'etc/sudoers',*(r/'etc/sudoers.d').glob('*')]:
  if p.is_file():check('no_NOPASSWD_'+p.name,not any('NOPASSWD' in l and not l.lstrip().startswith('#') for l in p.read_text().splitlines()))
 check('sshd_not_enabled',not any(p.is_symlink() and p.name in ('sshd.service','sshd.socket','sshd@.service') for p in (r/'etc/systemd/system').glob('*.wants/*')))
 check('networkmanager_enabled',(r/'etc/systemd/system/multi-user.target.wants/NetworkManager.service').is_symlink())
 check('landlock_config','CONFIG_SECURITY_LANDLOCK=y\n' in (r/f'usr/lib/rock5t-kernel/{K}/config').read_text())
 check('rt_group_sched_parameter','rt_group_sched=0' in json.loads((r/'etc/rock5t/kernel.json').read_text())['cmdline'])
 budget=(r/'etc/sysctl.d/90-rock5t-realtime-budget.conf').read_text()
 check('bounded_rt_budget','950000' in budget and '1000000' in budget and '-1' not in budget)
 check('ddr_license',digest(r/'usr/share/licenses/rock5t-bootloader/LICENSE.TXT')==digest(B/'next-version/rockchip-ddr-LICENSE.TXT'))
 for name in ('rock5t-firstboot','rock5t-configure-network','rock5t-configure-ssh','rock5t-kernel'):
  p=r/'usr/local/sbin'/name
  check('source_matches_'+name,digest(p)==digest(B/'overlay-work/rootfs/usr/local/sbin'/name) and p.stat().st_uid==0 and p.stat().st_mode&0o777==0o755)
 caps=run('getcap',str(r/'usr/bin/newuidmap'),str(r/'usr/bin/newgidmap'))
 check('signed_rootfs_capabilities','newuidmap cap_setuid=ep' in caps and 'newgidmap cap_setgid=ep' in caps)
 installed=set(l.split()[0] for l in (B/f'vm/next/packages-{variant}-final.txt').read_text().splitlines())
 check('no_generic_kernel_or_legacy_desktop',not {'linux-aarch64','sddm','sddm-kcm','firefox'}&installed)
 if variant=='kde':
  wanted={l for l in (B/'profiles/kde.packages').read_text().splitlines() if l and not l.startswith('#')}
  check('all_direct_kde_packages',wanted<=installed)
  check('only_plm_display_manager',os.readlink(r/'etc/systemd/system/display-manager.service')=='/usr/lib/systemd/system/plasmalogin.service')
  check('plm_vendor_pam',(r/'usr/lib/pam.d/plasmalogin').is_file())
  check('chromium_flags',(r/'etc/skel/.config/chromium-flags.conf').read_text()=='--enable-features=AcceleratedVideoDecoder\n')
  check('ac_no_idle_suspend',run('chroot',str(r),'env','HOME=/run/rock5t-qa-unused','XDG_CONFIG_HOME=/run/rock5t-qa-unused','XDG_CONFIG_DIRS=/etc/xdg','kreadconfig6','--file','powerdevilrc','--group','AC','--group','SuspendAndShutdown','--key','AutoSuspendAction')=='0')
  check('no_unrequested_gui_apps',not {'kate','kwrite','okular','gwenview','ark','vlc','libreoffice-fresh'}&installed)
 results[variant]={'checks':checks,'passed':len(checks),'package_count':len(installed)}
print(json.dumps(results,indent=2))
