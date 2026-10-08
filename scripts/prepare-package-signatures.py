#!/usr/bin/env python3
import base64,concurrent.futures,pathlib,subprocess,tarfile
base=pathlib.Path(__file__).resolve().parent.parent
records={}
for db in (base/'vm').glob('*.db'):
 with tarfile.open(db) as t:
  for ent in t:
   if ent.name.endswith('/desc'):
    fields=t.extractfile(ent).read().decode().split('\n\n'); d={x.split('\n',1)[0].strip('%'):x.split('\n',1)[1].strip() for x in fields if '\n' in x}
    if 'FILENAME' in d:records[d['FILENAME']]=d
urls={}
for p in (base/'vm').glob('*-urls.txt'):
 for url in p.read_text().splitlines():
  if url.startswith(('http://','https://')):urls[url.rsplit('/',1)[-1]]=url
cache=base/'arch-packages';missing=[]
for name,url in urls.items():
 dest=cache/(name+'.sig')
 if dest.exists():continue
 sig=records.get(name,{}).get('PGPSIG')
 if sig:dest.write_bytes(base64.b64decode(sig))
 else:missing.append((url+'.sig',dest))
def fetch(item):
 url,p=item
 subprocess.run(['curl','--fail','--location','--retry','3','--connect-timeout','20','--max-time','90','--silent','--show-error',url,'-o',str(p)],check=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:list(ex.map(fetch,missing))
print(f'Prepared {len(urls)} detached signatures, {len(missing)} fetched, others from pacman databases')
