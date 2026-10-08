#!/usr/bin/env python3
"""Restore the two signed ALARM rootfs file capabilities lost by plain GNU tar extraction."""
import argparse,base64,importlib.util,json,pathlib,subprocess,hashlib,os
p=argparse.ArgumentParser();p.add_argument('rootfs',type=pathlib.Path);p.add_argument('--image',type=pathlib.Path);a=p.parse_args();base=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('pack',base/'packaging-work/rock5t_image.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);tools=mod.Tools(base/'host-tools/root')
values={'newuidmap':'AQAAAoAAAAAAAAAAAAAAAAAAAAA','newgidmap':'AQAAAkAAAAAAAAAAAAAAAAAAAAA'}
for name,value in values.items():
 payload=base64.b64decode(value+'=');tmp=base/'vm'/f'{name}.cap';tmp.write_bytes(payload)
 tools.run('debugfs','-w','-R',f'ea_set -f {tmp} /usr/bin/{name} security.capability',a.rootfs)
 check=base/'vm'/f'{name}.check';tools.run('debugfs','-R',f'ea_get -f {check} /usr/bin/{name} security.capability',a.rootfs)
 if check.read_bytes()!=payload:raise SystemExit('Capability verification failed')
tools.run('e2fsck','-f','-n',a.rootfs)
if a.image:
 manifest_path=pathlib.Path(str(a.image)+'.manifest.json');m=json.loads(manifest_path.read_text());size=a.rootfs.stat().st_size
 if m['root']['bytes']!=size:raise SystemExit('Wrong source filesystem length')
 changed=0
 with a.rootfs.open('rb') as src,a.image.open('r+b') as dest:
  pos=0
  while b:=src.read(4*1024*1024):
   dest.seek(mod.ROOT_START+pos);old=dest.read(len(b))
   if old!=b:dest.seek(mod.ROOT_START+pos);dest.write(b);changed+=1
   pos+=len(b)
  dest.flush();os.fsync(dest.fileno())
 m['root']['sha256']=mod.digest(a.rootfs);m['validation']=mod.verify(a.image,m,tools,rootfs=a.rootfs);m['image_sha256']=mod.digest(a.image)
 for k in list(m):
  if k.startswith('compressed_'):del m[k]
 m['restored_file_capabilities']={'newuidmap':'cap_setuid=ep','newgidmap':'cap_setgid=ep','source':'PAX attributes in authenticated ALARM 2026-08-05 rootfs'}
 manifest_path.write_text(json.dumps(m,indent=2)+'\n');pathlib.Path(str(a.image)+'.sha256').write_text(f"{m['image_sha256']}  {a.image.name}\n")
 pathlib.Path(str(a.image)+'.validation.json').write_text(json.dumps({'result':m['validation'],'tool_results':tools.logs},indent=2)+'\n')
 print(json.dumps({'changed_4MiB_blocks':changed,'image_sha256':m['image_sha256'],'root_sha256':m['root']['sha256']}),flush=True)
else:print('Source root filesystem capabilities restored and verified',flush=True)
