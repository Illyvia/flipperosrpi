#!/usr/bin/env python3
"""Apply final board files, seal Pi stocks, regenerate BLS, and validate the image natively."""
import pathlib,subprocess,os,json,shutil,re,hashlib,sys
if os.environ.get("FLIPPER_PRIVATE_MOUNT_NS")!="1":
 os.execvp("unshare",["unshare","--mount","--propagation","private","env","FLIPPER_PRIVATE_MOUNT_NS=1",sys.executable,*sys.argv])
B=pathlib.Path(os.environ.get('FLIPPER_BUILD_ROOT', '/var/tmp/flipperos-rpi-full')).resolve();IMG=B/'flipperos-rpi4.img';M=B/'mnt';F=B/'firmware';P=B/'port/board-files'
NAMES=['Minimal','Desktop','TV-Media-Box','Router','No-Graphics'];BUILD='1328001'
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root required')
meta=json.loads((B/'image-board.json').read_text())
if subprocess.check_output(['losetup','-j',str(IMG)],text=True).strip():raise SystemExit('Image is still attached; wait for configuration to finish')
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
def out(*a):return subprocess.check_output(a,text=True).strip()
def ch(root,*a):return run('chroot',str(root),*a)
def write(p,s,mode=0o644):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.is_symlink():p.unlink()
 p.write_text(s);p.chmod(mode)
loop=out('losetup','--find','--show','--partscan',str(IMG));p1,p2=loop+'p1',loop+'p2'
results=[]
try:
 if pathlib.Path(out('losetup','-n','-O','BACK-FILE',loop)).resolve()!=IMG:raise SystemExit('Wrong loop image')
 run('udevadm','settle');run('mount','-t','btrfs','-o','subvolid=5,compress=zstd:3,noatime',p2,str(M));run('mount',p1,str(F))
 if out('blkid','-s','UUID','-o','value',p2)!=meta['root_uuid']:raise SystemExit('Wrong image UUID')
 # Update the shared home once, and roots before taking their final writable snapshots.
 for src in (P/'home').rglob('*'):
  if src.is_file():
   dst=M/'@home'/src.relative_to(P/'home');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);dst.chmod(0o755 if src.read_bytes().startswith(b'#!') else 0o644)
 for name in NAMES:
  stock=M/'@stock-snapshots'/('@'+name+'_'+BUILD+'_stock');active=M/('@'+name)
  if not (B/(name+'.configured')).exists():raise SystemExit('Unfinished profile: '+name)
  run('btrfs','property','set',str(stock),'ro','false')
  for src in P.rglob('*'):
   rel=src.relative_to(P)
   if not src.is_file() or rel.parts[0]=='home':continue
   dst=stock/rel;dst.parent.mkdir(parents=True,exist_ok=True)
   if dst.is_symlink():dst.unlink()
   shutil.copyfile(src,dst);dst.chmod(0o755 if src.read_bytes().startswith(b'#!') else 0o644)
  run(sys.executable,B/'port/install-display.py',stock,'--profile',name,'--no-kernel')
  # Preserve this Pi's existing radio country and use its real UART console name.
  live_cmd=pathlib.Path('/proc/cmdline').read_text()
  country=re.search(r'(?:^|\s)cfg80211\.ieee80211_regdom=([A-Z0-9]{2})(?:\s|$)',live_cmd)
  cmdfile=stock/'etc/kernel/cmdline';cmd=cmdfile.read_text().strip()
  if country:
   cmd=re.sub(r'(?:^|\s)cfg80211\.ieee80211_regdom=\S+','',cmd)
   cmd+=' cfg80211.ieee80211_regdom='+country.group(1)
   write(stock/'etc/modprobe.d/flipper-rpi-wifi.conf','options cfg80211 ieee80211_regdom='+country.group(1)+'\n')
  uart=re.search(r'(?:^|\s)(console=tty(?:S|AMA)[0-9]+,[0-9]+)(?:\s|$)',live_cmd)
  cmd=re.sub(r'console=serial0,115200',uart.group(1) if uart else '',cmd)
  write(cmdfile,cmd+'\n')
  # A '+' in a Pi kernel release must not be mistaken for the BLS boot counter.
  lib=stock/'usr/lib/flipper-bls.sh';text=lib.read_text();text=text.replace('_id="$ENTRY_TOKEN-$KERNEL_VERSION"','_id="$ENTRY_TOKEN-$(printf %s "$KERNEL_VERSION" | tr + _)"');write(lib,text)
  lib=stock/'usr/lib/flipper-blsname.sh';text=lib.read_text().replace('${1%%-*}','${1%%[+-]*}');write(lib,text)
  run(sys.executable,B/'port/patch-bls-library.py',stock)
  shutil.copyfile(B/'artifacts/flipctl',stock/'usr/bin/flipctl');(stock/'usr/bin/flipctl').chmod(0o755)
  ver=(B/(name+'.kernel')).read_text().strip()
  ch(stock,'/etc/kernel/install.d/54-flipper-rpi-kernel.install','add',ver,'/boot/stage','/usr/lib/modules/'+ver+'/vmlinuz')
  # One generic Pi initramfs serves every profile; build it with the final helpers.
  if name=='Minimal':
   mounts=[];hook=stock/'etc/kernel/install.d/90-loaderentry.install';saved=hook.with_name(hook.name+'.finalize')
   try:
    for src,dst in [(M/'boot',stock/'boot'),(F,stock/'boot/firmware'),('/dev',stock/'dev'),('/sys',stock/'sys')]:
     run('mount','--bind',str(src),str(dst));run('mount','--make-rslave',str(dst));mounts.append(dst)
    run('mount','-t','proc','proc',str(stock/'proc'));mounts.append(stock/'proc')
    hook.rename(saved);hook.symlink_to('/dev/null')
    run('cp','--reflink=always',str(stock/'usr/lib/modules'/ver/'initrd'),str(stock/'boot'/('initrd.img-'+ver)))
    ch(stock,'update-initramfs','-u','-k',ver)
   finally:
    if saved.exists():hook.unlink();saved.rename(hook)
    for dst in reversed(mounts):subprocess.run(['umount',str(dst)])
   common=stock/'usr/lib/modules'/ver/'initrd';common_ver=ver
  else:
   if ver!=common_ver:raise SystemExit('Kernel changed during the build; cannot share the initramfs')
   run('cp','--reflink=always',str(common),str(stock/'usr/lib/modules'/ver/'initrd'))
  # Confirm the actual target DTs apply both overlays, not just that the files exist.
  dt=stock/'usr/lib'/('linux-image-'+ver)/'broadcom'
  for board in ['4-b','400']:
   for overlay in ['vc4-kms-v3d','rpi4-no-graphics']:
    dest=B/('validate-'+board+'-'+overlay+'.dtb')
    run('fdtoverlay','-i',str(dt/('bcm2711-rpi-'+board+'.dtb')),'-o',str(dest),str(dt/(overlay+'.dtbo')))
  packages=out('chroot',str(stock),'dpkg-query','-W','-f=${binary:Package} ${Status}\n','linux-image-*')
  installed=[x.split()[0] for x in packages.splitlines() if x.endswith('install ok installed')]
  if not installed or any('rpt-rpi-v8' not in x and x!='linux-image-rpi-v8' for x in installed):raise SystemExit('Non-Pi kernel remains installed: '+str(installed))
  if not (stock/'usr/lib/modules'/ver/'initrd').is_file():raise SystemExit('Missing profile initramfs')
  ch(stock,'test','-e','/usr/lib/aarch64-linux-gnu/dri/v3d_dri.so')
  mesa=out('chroot',str(stock),'dpkg-query','-W','-f=${Version}','libgl1-mesa-dri')
  run('systemd-analyze','--root='+str(stock),'verify','flipctl.service','flipper-rpi-identity.service','flipper-rpi-restore-order.service')
  # Only freshly built roots in this owned loop image are replaced, never the builder root.
  if active.exists():
   if out('findmnt','-fn','--nofsroot','-o','SOURCE','--target',str(active))!=p2:raise SystemExit('Profile deletion guard failed')
   run('btrfs','subvolume','delete',str(active))
  run('btrfs','property','set',str(stock),'ro','true');run('btrfs','subvolume','snapshot',str(stock),str(active))
  results.append({'profile':name,'kernel':ver,'packages':installed,'overlays_validated':['Pi 4B KMS','Pi 400 KMS','Pi 4B no-graphics','Pi 400 no-graphics'],'units_verified':True,'verified_units':['flipctl.service','flipper-rpi-identity.service','flipper-rpi-restore-order.service'],'mesa_version':mesa,'v3d_driver_present':True})
 # The source RK3576 golden stocks must not remain selectable as reset/update bases.
 for name in NAMES:
  old=M/'@stock-snapshots'/('@'+name+'_1328_stock')
  if old.exists():run('btrfs','subvolume','delete',str(old))
 actor=M/'@Minimal';mounts=[]
 try:
  for src,dst in [(M/'boot',actor/'boot'),(F,actor/'boot/firmware'),('/dev',actor/'dev'),('/sys',actor/'sys')]:
   dst.mkdir(parents=True,exist_ok=True);run('mount','--bind',str(src),str(dst));run('mount','--make-rslave',str(dst));mounts.append(dst)
  run('mount','-t','proc','proc',str(actor/'proc'));mounts.append(actor/'proc')
  entries=M/'boot/loader/entries';entries.mkdir(parents=True,exist_ok=True)
  for f in entries.glob('*.conf'):f.unlink()
  for name in NAMES:
   dst=actor/'run/port-profile';dst.mkdir(parents=True,exist_ok=True);run('mount','--bind',str(M/('@'+name)),str(dst));mounts.append(dst)
   ch(actor,'sh','-c','. /usr/lib/flipper-bls.sh; flipper_write_entry @'+name+' /run/port-profile')
   run('umount',str(mounts.pop()))
  # Factory profiles use their base bands; derived profiles get the following slots.
  slots={'Desktop':900,'TV-Media-Box':800,'Router':700,'Minimal':600,'No-Graphics':500}
  for name,slot in slots.items():
   write(M/('@'+name)/'etc/kernel/entry-token',f'{slot}-flipperos-{name}\n')
   for entry in entries.glob('*.conf'):
    if ('rootflags=subvol=@'+name) not in entry.read_text().split():continue
    renamed=entry.with_name(re.sub(r'^\d{3}-',str(slot)+'-',entry.name))
    if renamed!=entry:entry.rename(renamed)
  ch(actor,'set-boot-order','--init','-d',p2)
  ch(actor,'set-boot-order','--autoboot','@Minimal','-d',p2)
  # Exercise real profile tools against the image, without booting or emulating it.
  ch(actor,'create-profile','-y','-d',p2,'@Minimal','@PortValidation')
  ch(actor,'boot-profile','--dry-run','-d',p2,'@PortValidation')
  ch(actor,'delete-profile','-y','-d',p2,'@PortValidation')
  for name in NAMES:ch(actor,'boot-profile','--dry-run','-d',p2,'@'+name)
  # Render using the complete image userspace and target executable, on the physical Pi.
  ch(actor,'/usr/bin/flipctl','--png','/tmp/flipper-rpi-image.png','--screen','main')
  shutil.copyfile(actor/'tmp/flipper-rpi-image.png',B/'full-image-native-render.png');(actor/'tmp/flipper-rpi-image.png').unlink()
 finally:
  for dst in reversed(mounts):subprocess.run(['umount',str(dst)])
 # Every BLS path must resolve in this image and every profile must carry Pi metadata.
 entries=M/'boot/loader/entries'
 for f in entries.glob('*.conf'):
  for line in f.read_text().splitlines():
   a=line.split()
   if a and a[0] in ['linux','initrd','devicetree-overlay']:
    for path in a[1:]:
     if '..' in pathlib.PurePosixPath(path).parts or not (M/path.lstrip('/')).exists():raise SystemExit('Invalid boot entry path: '+line)
 for entry in entries.glob('*.conf'):
  if '+' in entry.stem and not re.fullmatch(r'.+\+[0-9]+(?:-[0-9]+)?',entry.stem):raise SystemExit('Malformed BLS counter: '+entry.name)
 if len(list(entries.glob('*.conf')))!=5:raise SystemExit('Expected exactly five initial profile boot entries')
 # Keep the rescue kernel/initramfs independent of the Btrfs partition.
 ver=(B/'Minimal.kernel').read_text().strip();rec=F/'recovery'
 shutil.copyfile(M/'@Minimal/usr/lib/modules'/ver/'vmlinuz',rec/'Image');shutil.copyfile(M/'@Minimal/usr/lib/modules'/ver/'initrd',rec/'initramfs')
 for dtb in (M/'@Minimal/usr/lib'/('linux-image-'+ver)/'broadcom').glob('*.dtb'):shutil.copyfile(dtb,F/dtb.name)
 # Rebuild the FAT rescue command from the same board-correct base command line.
 base_cmd=(M/'@Minimal/etc/kernel/cmdline').read_text().strip()
 rescue='load mmc 0:1 ${kernel_addr_r} recovery/Image; load mmc 0:1 ${ramdisk_addr_r} recovery/initramfs; setenv rescue_size ${filesize}; setenv bootargs '+base_cmd+' rootflags=subvol=@Minimal break=mount; booti ${kernel_addr_r} ${ramdisk_addr_r}:${rescue_size} ${fdt_addr}\n'
 write(B/'recovery-boot.cmd',rescue)
 run('mkimage','-A','arm64','-T','script','-C','none','-n','Flipper Pi recovery','-d',str(B/'recovery-boot.cmd'),str(rec/'boot.scr'))
 shutil.copyfile(B/'artifacts/u-boot.bin',F/'u-boot.bin')
 report={'source_build':1328,'pi_build':BUILD,'profiles':results,'profile_clone_delete_test':'passed','cold_boot_dry_runs':'passed for all five profiles','native_image_render':'passed','image_boot_tested':False,'qemu_used':False}
 (B/'validation.json').write_text(json.dumps(report,indent=2)+'\n');run('sync');print('NATIVE IMAGE VALIDATION PASSED',flush=True)
 run('btrfs','filesystem','usage',str(M))
 subprocess.run(['fstrim','-v',str(M)])
finally:
 subprocess.run(['umount',str(F)]);subprocess.run(['umount',str(M)]);subprocess.run(['losetup','-d',loop])
