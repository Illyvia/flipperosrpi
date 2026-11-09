#!/usr/bin/env python3
"""Receive verified official Flipper OS stocks into a NEW Pi disk-image file, natively."""
import hashlib,json,os,pathlib,subprocess,sys
if os.environ.get("FLIPPER_PRIVATE_MOUNT_NS")!="1":
 os.execvp("unshare",["unshare","--mount","--propagation","private","env","FLIPPER_PRIVATE_MOUNT_NS=1",sys.executable,*sys.argv])
B=pathlib.Path(sys.argv[1]).resolve()
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Run as root on native ARM64 Linux; no emulation')
if len(B.parts) < 3 or B.is_symlink():raise SystemExit('Use a dedicated absolute build directory below a parent directory')
B.mkdir(exist_ok=True); IMG=B/'flipperos-rpi4.img'; M=B/'mnt';F=B/'firmware';M.mkdir(exist_ok=True);F.mkdir(exist_ok=True)
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def fetch(u):return json.loads(subprocess.check_output(['curl','-fsSL','--retry','3',u]))
base='https://dl-linux-images.flipp.dev/rootfs/'
index=fetch(base+'manifest.json'); picked=None
for d in sorted(index['directories'],key=lambda x:x['mtime'],reverse=True):
 if 'scripts=d21ab22ac67f02c2e817d2b6e7b99d2cc615bd90' not in d['name']:continue
 manifest=fetch(base+d['name']+'manifest.json')
 if manifest['build']['number']==1328:picked=base+d['name'];break
if picked is None:raise SystemExit('Pinned upstream build 1328 is unavailable')
(B/'upstream-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if not IMG.exists():
 fd=os.open(IMG,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(fd,8*1024**3);os.close(fd)
 run('parted','-s',str(IMG),'mklabel','msdos','mkpart','primary','fat32','1MiB','513MiB','mkpart','primary','btrfs','513MiB','100%','set','1','boot','on')
 (B/'owned-image.json').write_text(json.dumps({'image':str(IMG),'bytes':8*1024**3}))
else:
 marker=json.loads((B/'owned-image.json').read_text())
 if marker!={'image':str(IMG),'bytes':8*1024**3} or IMG.stat().st_size!=8*1024**3:raise SystemExit('Image ownership guard failed')
loop=subprocess.check_output(['losetup','--find','--show','--partscan',str(IMG)],text=True).strip()
try:
 actual=subprocess.check_output(['losetup','-n','-O','BACK-FILE',loop],text=True).strip()
 if pathlib.Path(actual).resolve()!=IMG:raise SystemExit('Loop backing-file guard failed')
 p1,p2=loop+'p1',loop+'p2';run('udevadm','settle')
 if not (B/'formatted').exists():
  run('mkfs.vfat','-F','32','-n','FLIPBOOT',p1);run('mkfs.btrfs','-L','flipperos-rpi',p2);(B/'formatted').touch()
 run('mount',p2,str(M),'-o','subvolid=5,compress=zstd:3,noatime')
 run('mount',p1,str(F)); S=M/'@stock-snapshots'
 if not S.exists():run('btrfs','subvolume','create',str(S))
 for name in ['Minimal','Desktop','TV-Media-Box','Router','No-Graphics']:
  fn=name+'_1328_stock'+('_pack.zst' if name=='Minimal' else '_inc_pack.zst')
  info=next(x for x in manifest['files'] if x['path']==fn)
  dest=S/('@'+name+'_1328_stock'); mark=B/(name+'.verified')
  if mark.exists() and dest.exists():print('Already verified',name,flush=True);continue
  if dest.exists():raise SystemExit('Unverified received stock exists: '+str(dest))
  print('Receiving official',name,info['size'],'compressed bytes',flush=True)
  curl=subprocess.Popen(['curl','-fSL','--retry','3',picked+fn],stdout=subprocess.PIPE)
  dec=subprocess.Popen(['zstd','-dc'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
  recv=subprocess.Popen(['btrfs','receive',str(S)],stdin=dec.stdout);dec.stdout.close()
  sha=hashlib.sha256()
  try:
   while True:
    block=curl.stdout.read(1024*1024)
    if not block:break
    sha.update(block);dec.stdin.write(block)
  finally:dec.stdin.close();curl.stdout.close()
  codes=(curl.wait(),dec.wait(),recv.wait())
  if codes!=(0,0,0) or sha.hexdigest()!=info['sha256']:raise SystemExit('Stock receive/checksum failed: '+name+' '+str(codes))
  mark.write_text(sha.hexdigest()+'\n');print('Verified',name,sha.hexdigest(),flush=True)
 # Shared subvolumes match upstream layout.
 for sv in ['boot','@home','@snapshots','@var-log','@var-cache']:
  if not (M/sv).exists():run('btrfs','subvolume','create',str(M/sv))
 print('OFFICIAL STOCK IMPORT COMPLETE',flush=True)
 run('btrfs','filesystem','usage',str(M))
finally:
 subprocess.run(['umount',str(F)])
 subprocess.run(['umount',str(M)])
 subprocess.run(['losetup','-d',loop])
