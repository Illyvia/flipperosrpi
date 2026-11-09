#!/usr/bin/env python3
"""Fetch missing pinned upstream checkouts without overwriting existing work."""
import json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
for name,entry in json.loads((root/'sources.lock.json').read_text()).items():
 dest=root/'upstream'/name
 if not dest.exists():
  dest.parent.mkdir(exist_ok=True)
  subprocess.run(['git','clone','--no-checkout',entry['url'],str(dest)],check=True)
  subprocess.run(['git','-C',str(dest),'checkout','--detach',entry['commit']],check=True)
 actual=subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
 if actual!=entry['commit']:raise SystemExit(f'{name}: existing checkout has wrong revision; resolve manually')
 print(name,actual)
