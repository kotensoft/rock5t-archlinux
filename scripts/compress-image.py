#!/usr/bin/env python3
"""Resumable standard multi-stream XZ compression; verifies exact decompressed SHA256."""
import argparse,hashlib,json,os,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('image',type=pathlib.Path);p.add_argument('--xz',type=pathlib.Path,required=True);p.add_argument('--refresh-changed-parts',action='store_true');a=p.parse_args()
source=a.image.resolve();out=pathlib.Path(str(source)+'.xz');parts=pathlib.Path(str(source)+'.xz.parts');parts.mkdir(exist_ok=True)
manifest_path=pathlib.Path(str(source)+'.manifest.json');manifest=json.loads(manifest_path.read_text());expected=manifest['image_sha256']
def hashfile(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
if out.exists():raise SystemExit('Final compressed output already exists; refusing replacement')
chunk=256*1024*1024;rawhash=hashlib.sha256();records=[]
with source.open('rb') as f:
 i=0
 while data:=f.read(chunk):
  rawhash.update(data);rh=hashlib.sha256(data).hexdigest();part=parts/f'{i:04d}.xz';meta=parts/f'{i:04d}.json'
  reuse=False
  if part.exists() and meta.exists():
   info=json.loads(meta.read_text())
   reuse=info['raw_sha256']==rh and info['compressed_sha256']==hashfile(part)
   if not reuse and not a.refresh_changed_parts:raise SystemExit(f'Part {i} changed; abort')
  if not reuse:
   temp=part.with_suffix('.partial')
   with temp.open('wb') as o:subprocess.run([str(a.xz),'--threads=2','--memlimit-compress=1024MiB','-4','--check=crc64','--stdout'],input=data,stdout=o,check=True)
   subprocess.run([str(a.xz),'--test',str(temp)],check=True);temp.replace(part)
   info={'part':part.name,'raw_bytes':len(data),'raw_sha256':rh,'compressed_sha256':hashfile(part)};meta.write_text(json.dumps(info)+'\n')
  records.append(info);print(f'chunk {i+1}: {len(data)} raw bytes',flush=True);i+=1
if rawhash.hexdigest()!=expected:raise SystemExit('Source hash changed')
temp=pathlib.Path(str(out)+'.partial')
with temp.open('wb') as dest:
 for item in records:
  with (parts/item['part']).open('rb') as src:
   for b in iter(lambda:src.read(8*1024*1024),b''):dest.write(b)
 dest.flush();os.fsync(dest.fileno())
subprocess.run([str(a.xz),'--test',str(temp)],check=True)
h=hashlib.sha256()
proc=subprocess.Popen([str(a.xz),'-dc',str(temp)],stdout=subprocess.PIPE)
for b in iter(lambda:proc.stdout.read(8*1024*1024),b''):h.update(b)
if proc.wait()!=0 or h.hexdigest()!=expected:raise SystemExit('Decompressed SHA256 mismatch')
temp.replace(out);sha=hashfile(out);pathlib.Path(str(out)+'.sha256').write_text(f'{sha}  {out.name}\n')
manifest['compressed_sha256']=sha;manifest['compressed_bytes']=out.stat().st_size;manifest['compressed_decompressed_sha256_verified']=True
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'sha256':sha,'decompressed_verified':True}),flush=True)
