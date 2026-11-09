#!/usr/bin/env python3
"""Replace the RK-only Mesa builds in all Pi stocks with Raspberry Pi's signed packages."""
import os,sys,pathlib,subprocess,json
if os.environ.get('FLIPPER_PRIVATE_MOUNT_NS')!='1':os.execvp('unshare',['unshare','--mount','--propagation','private','env','FLIPPER_PRIVATE_MOUNT_NS=1',sys.executable,*sys.argv])
B=pathlib.Path(os.environ.get('FLIPPER_BUILD_ROOT', '/var/tmp/flipperos-rpi-full')).resolve();M=B/'mnt';F=B/'firmware';IMG=B/'flipperos-rpi4.img';NAMES=['Minimal','Desktop','TV-Media-Box','Router','No-Graphics']
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root required')
if subprocess.check_output(['losetup','-j',str(IMG)],text=True).strip():raise SystemExit('Image is attached')
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def out(*a):return subprocess.check_output(a,text=True).strip()
def ch(root,*a):return run('chroot',str(root),*a,env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','LC_ALL':'C'})
loop=out('losetup','--find','--show','--partscan',str(IMG));p1,p2=loop+'p1',loop+'p2'
try:
 if pathlib.Path(out('losetup','-n','-O','BACK-FILE',loop)).resolve()!=IMG:raise SystemExit('Wrong loop backing file')
 run('udevadm','settle');run('mount','-t','btrfs','-o','subvolid=5,compress=zstd:3,noatime',p2,str(M));run('mount',p1,str(F))
 for name in NAMES:
  if (B/(name+'.mesa-configured')).exists():continue
  root=M/'@stock-snapshots'/('@'+name+'_1328001_stock');run('btrfs','property','set',str(root),'ro','false');mounts=[]
  try:
   for src,dst in [(M/'boot',root/'boot'),(F,root/'boot/firmware'),(M/'@var-cache',root/'var/cache'),(M/'@var-log',root/'var/log'),('/dev',root/'dev'),('/sys',root/'sys')]:
    run('mount','--bind',str(src),str(dst));run('mount','--make-rslave',str(dst));mounts.append(dst)
   run('mount','-t','proc','proc',str(root/'proc'));mounts.append(root/'proc');run('mount','-t','tmpfs','tmpfs',str(root/'run'));mounts.append(root/'run')
   pin=root/'etc/apt/preferences.d/flipper-rpi-mesa';pin.parent.mkdir(parents=True,exist_ok=True);pin.write_bytes((B/'port/board-files/etc/apt/preferences.d/flipper-rpi-mesa').read_bytes())
   policy=root/'usr/sbin/policy-rc.d';policy.write_text('#!/bin/sh\nexit 101\n');policy.chmod(0o755)
   ch(root,'apt-get','update','-qq')
   rows=out('chroot',str(root),'dpkg-query','-W','-f=${binary:Package}|${source:Package}|${Status}\n')
   packages=[x.split('|')[0] for x in rows.splitlines() if '|mesa|' in x and x.endswith('install ok installed')]
   if 'mesa-vulkan-drivers' not in packages:packages.append('mesa-vulkan-drivers')
   print('Installing Pi Mesa in',name,packages,flush=True)
   ch(root,'apt-get','install','-y','--allow-downgrades',*[x+'/trixie' for x in packages])
   ch(root,'test','-e','/usr/lib/aarch64-linux-gnu/dri/v3d_dri.so')
   report=out('chroot',str(root),'dpkg-query','-W','-f=${binary:Package} ${Version}\n',*packages)
   (B/(name+'.mesa-packages')).write_text(report+'\n');policy.unlink()
  finally:
   for dst in reversed(mounts):subprocess.run(['umount',str(dst)])
  run('btrfs','property','set',str(root),'ro','true');(B/(name+'.mesa-configured')).touch();print('V3D packages validated for',name,flush=True)
 print('PI MESA CONFIGURATION COMPLETE',flush=True)
finally:
 subprocess.run(['umount',str(F)]);subprocess.run(['umount',str(M)]);subprocess.run(['losetup','-d',loop])
