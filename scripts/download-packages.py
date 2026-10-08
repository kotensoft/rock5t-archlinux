#!/usr/bin/env python3
"""Fetch URLs emitted by pacman -Sp. pacman verifies all signatures on install."""
import argparse, concurrent.futures, hashlib, json, pathlib, subprocess, urllib.parse
p=argparse.ArgumentParser();p.add_argument('url_list',type=pathlib.Path);p.add_argument('--cache',type=pathlib.Path,default=pathlib.Path('arch-packages'));a=p.parse_args();a.cache.mkdir(parents=True,exist_ok=True)
urls=[x.strip() for x in a.url_list.read_text().splitlines() if x.startswith(('http://','https://'))]
def fetch(url):
 name=pathlib.Path(urllib.parse.urlsplit(url).path).name
 if '/' in name or not name.endswith(('.pkg.tar.xz','.pkg.tar.zst','.pkg.tar.gz')): raise ValueError(url)
 dest=a.cache/name
 if not dest.exists():
  temp=dest.with_suffix(dest.suffix+'.part')
  subprocess.run(['curl','--fail','--location','--retry','3','--retry-delay','2','--connect-timeout','30','--max-time','600','--silent','--show-error',url,'--output',str(temp)],check=True)
  temp.replace(dest)
 h=hashlib.sha256()
 with dest.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return {'url':url,'filename':name,'bytes':dest.stat().st_size,'sha256':h.hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 results=list(pool.map(fetch,urls))
manifest=a.cache/(a.url_list.stem+'.manifest.json');manifest.write_text(json.dumps(results,indent=2)+'\n');print(f'Downloaded/checked {len(results)} packages; {manifest}')
