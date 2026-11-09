#!/usr/bin/env python3
"""Adapt verified Flipper OS stocks to a Pi 4/400 image on native ARM64 Linux."""
import os,sys,pathlib,subprocess,shutil,json,gzip,time,re
if os.environ.get("FLIPPER_PRIVATE_MOUNT_NS")!="1":
 os.execvp("unshare",["unshare","--mount","--propagation","private","env","FLIPPER_PRIVATE_MOUNT_NS=1",sys.executable,*sys.argv])
B=pathlib.Path(os.environ.get('FLIPPER_BUILD_ROOT', '/var/tmp/flipperos-rpi-full')).resolve();M=B/'mnt';F=B/'firmware';PORT=B/'port';IMAGE=B/'flipperos-rpi4.img';BUILD='1328001'
DONOR=pathlib.Path(os.environ.get('FLIPPER_BOARD_INPUT', '/'))
NAMES=['Minimal','Desktop','TV-Media-Box','Router','No-Graphics']
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root is required; no QEMU')
if not all((B/(n+'.verified')).exists() for n in NAMES):raise SystemExit('Receive and verify all official stocks first')
if json.loads((B/'owned-image.json').read_text())['image']!=str(IMAGE):raise SystemExit('Image ownership check failed')
def run(*args,**kw):return subprocess.run(args,check=True,**kw)
def output(*args):return subprocess.check_output(args,text=True).strip()
def put(path,text,mode=0o644):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.is_symlink():path.unlink()
 path.write_text(text);path.chmod(mode)
def ch(root,*args):return run('chroot',str(root),*args,env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','LC_ALL':'C'})
def copy_board(root):
 for src in (PORT/'board-files').rglob('*'):
  if src.is_file():
   dst=root/src.relative_to(PORT/'board-files');dst.parent.mkdir(parents=True,exist_ok=True)
   if dst.is_symlink():dst.unlink()
   shutil.copyfile(src,dst);dst.chmod(0o755 if src.read_bytes().startswith(b'#!') else 0o644)
# Both image partitions are bootable: Pi firmware finds FAT, U-Boot also scans the Btrfs root.
with IMAGE.open('r+b') as fd:
 for offset in [446,462]:fd.seek(offset);fd.write(b'\x80')
loop=output('losetup','--find','--show','--partscan',str(IMAGE));p1,p2=loop+'p1',loop+'p2'
try:
 if pathlib.Path(output('losetup','-n','-O','BACK-FILE',loop)).resolve()!=IMAGE:raise SystemExit('Wrong loop backing file')
 run('udevadm','settle');run('mount','-t','btrfs','-o','subvolid=5,compress=zstd:3,noatime',p2,str(M));run('mount',p1,str(F))
 rootuuid=output('blkid','-s','UUID','-o','value',p2);fatuuid=output('blkid','-s','UUID','-o','value',p1)
 # Seed only board firmware, never the builder's cloud-init files or boot configuration.
 for src in (DONOR/'boot/firmware').iterdir():
  if src.is_file() and (src.suffix in ['.dat','.elf','.dtb'] or src.name in ['bootcode.bin','LICENCE.broadcom']):shutil.copyfile(src,F/src.name)
 if not (F/'overlays').exists():shutil.copytree(DONOR/'boot/firmware/overlays',F/'overlays')
 put(F/'config.txt','arm_64bit=1\\nenable_uart=1\\nkernel=u-boot.bin\\n'.replace('\\n','\n'))
 put(F/'cmdline.txt',f'console=tty1 root=UUID={rootuuid} rootfstype=btrfs rootflags=subvol=@Desktop rootwait rw net.ifnames=0\\n'.replace('\\n','\n'))
 # Receive upstream's shared home stream, including the KDE/Kodi user configuration.
 if not (B/'home.verified').exists():
  manifest=json.loads((B/'upstream-manifest.json').read_text());entry=next(x for x in manifest['files'] if x['path'].startswith('home_'))
  index=json.loads(subprocess.check_output(['curl','-fsSL','https://dl-linux-images.flipp.dev/rootfs/manifest.json']))
  directory=next(x['name'] for x in index['directories'] if 'tests=57cd4055846b5caaa3500cffda9d8a2f4d43be6c__scripts=d21ab22ac67f02c2e817d2b6e7b99d2cc615bd90' in x['name'])
  data=subprocess.check_output(['curl','-fsSL','https://dl-linux-images.flipp.dev/rootfs/'+directory+entry['path']])
  import hashlib
  if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise SystemExit('Home stream checksum mismatch')
  receive=M/'import-home';receive.mkdir(exist_ok=True)
  raw=subprocess.check_output(['zstd','-dc'],input=data)
  run('btrfs','receive',str(receive),input=raw)
  run('rsync','-a',str(receive/'@home')+'/',str(M/'@home')+'/');run('btrfs','subvolume','delete',str(receive/'@home'));receive.rmdir();(B/'home.verified').touch()
 for name in NAMES:
  stock=M/'@stock-snapshots'/('@'+name+'_'+BUILD+'_stock');base=M/'@stock-snapshots'/('@'+name+'_1328_stock')
  if (B/(name+'.configured')).exists():
   if not (M/('@'+name)).exists():run('btrfs','property','set',str(stock),'ro','true');run('btrfs','subvolume','snapshot',str(stock),str(M/('@'+name)))
   print('Already configured',name,flush=True);continue
  if not stock.exists():run('btrfs','subvolume','snapshot',str(base),str(stock))
  root=stock;mounts=[];disabled=[]
  try:
   def bind(src,dst):
    dst.mkdir(parents=True,exist_ok=True);run('mount','--bind',str(src),str(dst));run('mount','--make-rslave',str(dst));mounts.append(dst)
   bind(M/'boot',root/'boot');bind(F,root/'boot/firmware');bind(M/'@home',root/'home');bind(M/'@var-log',root/'var/log');bind(M/'@var-cache',root/'var/cache');bind('/dev',root/'dev');bind('/dev/pts',root/'dev/pts')
   (root/'proc').mkdir(exist_ok=True);run('mount','-t','proc','proc',str(root/'proc'));mounts.append(root/'proc')
   bind('/sys',root/'sys');run('mount','-o','remount,bind,ro',str(root/'sys'))
   # Prevent any package script from contacting the builder's systemd.
   (root/'run').mkdir(exist_ok=True);run('mount','-t','tmpfs','tmpfs',str(root/'run'));mounts.append(root/'run')
   put(root/'usr/sbin/policy-rc.d','#!/bin/sh\nexit 101\n',0o755)
   fstab=f'UUID={rootuuid} / btrfs defaults,noatime,compress=zstd:3 0 0\n'
   for mount,sv in [('/boot','boot'),('/home','@home'),('/var/log','@var-log'),('/var/cache','@var-cache')]:fstab+=f'UUID={rootuuid} {mount} btrfs noatime,compress=zstd:3,subvol={sv} 0 0\n'
   fstab+=f'UUID={fatuuid} /boot/firmware vfat defaults,umask=0077 0 2\n';put(root/'etc/fstab',fstab)
   put(root/'etc/kernel/cmdline',f'console=tty1 console=serial0,115200 root=UUID={rootuuid} rootfstype=btrfs rootwait rw net.ifnames=0\n')
   put(root/'etc/flipper-rpi-image.conf',f'ROOT_UUID={rootuuid}\nFIRMWARE_UUID={fatuuid}\n')
   put(root/'etc/resolv.conf',pathlib.Path('/etc/resolv.conf').read_text())
   put(root/'etc/apt/sources.list.d/raspi.sources',(DONOR/'etc/apt/sources.list.d/raspi.sources').read_text())
   key=root/'usr/share/keyrings/raspberrypi-archive-keyring.pgp';key.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(DONOR/'usr/share/keyrings/raspberrypi-archive-keyring.pgp',key)
   # Suppress upstream Rockchip entry generation while replacing its kernel packages.
   for path in (root/'etc/kernel/install.d').glob('*.install'):
    saved=path.with_name(path.name+'.rpi-disabled');path.rename(saved);path.symlink_to('/dev/null');disabled.append((path,saved))
   print('Installing Pi kernel/firmware into',name,flush=True)
   ch(root,'apt-get','update','-qq')
   ch(root,'apt-get','install','-y','--no-install-recommends','linux-image-rpi-v8','raspi-firmware','firmware-brcm80211','libpam-systemd','busybox-static','python3','sway','dbus-user-session')
   packages=subprocess.check_output(['chroot',str(root),'dpkg-query','-W','-f=${binary:Package} ${Status}\n','linux-image-*'],text=True)
   remove=[x.split()[0] for x in packages.splitlines() if x.endswith('install ok installed') and 'rpt-rpi-v8' not in x.split()[0] and x.split()[0]!='linux-image-rpi-v8']
   if remove:ch(root,'apt-get','purge','-y',*remove)
   for path,saved in disabled:
    if path.name!='90-loaderentry.install':path.unlink();saved.rename(path)
   disabled=[(path,saved) for path,saved in disabled if path.name=='90-loaderentry.install']
   copy_board(root)
   for lib,replacements in {
    'flipper-bls.sh':[('VENDOR=rockchip','VENDOR=broadcom'),('_id="$ENTRY_TOKEN-$KERNEL_VERSION"','_id="$ENTRY_TOKEN-$(printf \'%s\' \"$KERNEL_VERSION\" | tr \'+\' \'_\')"')],
    'flipper-blsname.sh':[('FLIPPER_BLS_MIN_KERNEL:-7.0','FLIPPER_BLS_MIN_KERNEL:-6.18'),('${1%%-*}','${1%%[+-]*}')],
   }.items():
    path=root/'usr/lib'/lib;txt=path.read_text()
    for old,new in replacements:
     if old not in txt and new not in txt:raise SystemExit('Upstream board patch anchor missing: '+old)
     txt=txt.replace(old,new)
    put(path,txt)
   # Keep update/rollback tooling but require a board-specific feed, never RK3576 artifacts.
   update=root/'usr/local/sbin/update-profile';txt=update.read_text();txt=txt.replace('URL="${FLIPPER_UPDATE_URL:-https://dl-linux-images.flipp.dev/rootfs/}"','URL="${FLIPPER_UPDATE_URL:-$(cat /etc/flipper-rpi/update-url)}"');put(update,txt,0o755)
   put(root/'etc/flipper-rpi/update-url','file:///usr/share/flipper-rpi/updates/\n');put(root/'usr/share/flipper-rpi/updates/manifest.json','{"directories": []}\n')
   put(root/'etc/hostname','pi\n');put(root/'etc/hosts','127.0.0.1 localhost\n127.0.1.1 pi\n::1 localhost ip6-localhost\n')
   osrelease=root/'etc/os-release';text=osrelease.read_text();text=re.sub(r'^BUILD_ID=.*$',f'BUILD_ID={BUILD}',text,flags=re.M);text+='\nIMAGE_ID=flipperos-rpi4\nVARIANT_ID=flipperos-rpi4\n';put(osrelease,text)
   # Public builds do not copy the builder's network credentials. Private Wi-Fi is opt-in.
   con=root/'etc/NetworkManager/system-connections';con.mkdir(parents=True,exist_ok=True)
   for file in con.glob('*'):
    if file.is_file():file.unlink()
   if name!='Router':
    wifi=os.environ.get('FLIPPER_PRIVATE_WIFI_FILE')
    if wifi:
     src=pathlib.Path(wifi)
     if not src.is_file():raise SystemExit('Private Wi-Fi keyfile does not exist')
     shutil.copyfile(src,con/'private-wifi.nmconnection');(con/'private-wifi.nmconnection').chmod(0o600)
   else:
    for file in con.glob('*'):file.unlink()
    put(con/'pi-router-wan.nmconnection','[connection]\nid=Pi Router WAN\ntype=ethernet\ninterface-name=eth0\nautoconnect=true\n[ipv4]\nmethod=auto\n[ipv6]\nmethod=auto\n',0o600)
    put(con/'pi-router-ap.nmconnection','[connection]\nid=Pi Router LAN\ntype=wifi\ninterface-name=wlan0\nautoconnect=true\nautoconnect-priority=100\n[wifi]\nmode=ap\nband=bg\nchannel=6\nssid=FlipperPi\n[wifi-security]\nkey-mgmt=wpa-psk\npsk=flipperone\n[ipv4]\nmethod=shared\naddress1=192.168.50.1/24\n[ipv6]\nmethod=ignore\n',0o600)
   # Hardware services from the Rockchip image must not configure Pi buses or USB roles.
   for unit in ['usb-ncm-msc-mtp-gadget.service','usb-ncm-msc-gadget.service','usb-ncm-gadget.service','usb-msc-gadget.service','flipusb0-dhcp.service','ext-gpio.service','flipper-one-online.service','set-hostname-and-banner.service','router-lan-flipusb0.service','router-lan.service']:
    p=root/'etc/systemd/system'/unit
    if p.exists() or p.is_symlink():p.unlink()
    p.symlink_to('/dev/null')
   for unit in ['ssh.service','NetworkManager.service','flipctl.service','flipper-rpi-restore-order.service','flipper-bless-boot.service','systemd-boot-check-no-failures.service']:
    ch(root,'systemctl','enable',unit)
   if name!='Desktop':ch(root,'systemctl','set-default','multi-user.target')
   # Include btrfs even though the builder itself boots ext4.
   modules=root/'etc/initramfs-tools/modules';old=modules.read_text();put(modules,old if 'btrfs' in old.splitlines() else old+'\nbtrfs\n')
   vers=sorted([p.name for p in (root/'usr/lib/linux-image-').parent.glob('linux-image-*') if 'rpt-rpi-v8' in p.name])
   if not vers:raise SystemExit('Pi kernel package installed no device-tree directory')
   ver=vers[-1].removeprefix('linux-image-');(B/(name+'.kernel')).write_text(ver+'\n')
   ch(root,'/etc/kernel/install.d/54-flipper-rpi-kernel.install','add',ver,'/boot/stage','/boot/vmlinuz-'+ver)
   ch(root,'update-initramfs','-u','-k',ver)
   # The initrd post-update hook now stages the per-profile kernel/initrd. Ensure it exists.
   if not (root/'usr/lib/modules'/ver/'initrd').exists():
    src=root/'boot'/('initrd.img-'+ver)
    if not src.exists():raise SystemExit('Pi initramfs was not generated')
    shutil.copyfile(src,root/'usr/lib/modules'/ver/'initrd')
   for path,saved in disabled:path.unlink();saved.rename(path)
   disabled=[]
   # Wait for the board-enabled UI cross-build rather than shipping a UI that hides Pi kernels.
   binary=B/'artifacts/flipctl'
   while not binary.exists():print('Waiting for Pi-enabled full UI binary',flush=True);time.sleep(10)
   shutil.copyfile(binary,root/'usr/bin/flipctl');(root/'usr/bin/flipctl').chmod(0o755)
   # Stamp the new Pi stock so migration compares with the correct board baseline.
   ch(root,'sh','-c',f'. /usr/lib/flipper-btrfs.sh; stamp_stock_origin / @'+name+'_'+BUILD+'_stock')
   (root/'usr/sbin/policy-rc.d').unlink(missing_ok=True)
   ch(root,'apt-get','clean')
   (B/(name+'.configured')).touch()
  finally:
   for path,saved in disabled:
    if path.is_symlink():path.unlink()
    if saved.exists():saved.rename(path)
   for mount in reversed(mounts):subprocess.run(['umount',str(mount)])
  run('btrfs','property','set',str(stock),'ro','true')
  if not (M/('@'+name)).exists():run('btrfs','subvolume','snapshot',str(stock),str(M/('@'+name)))
 print('ALL PROFILES CONFIGURED',flush=True)
 # Boot entries point at each profile's own kernel, initrd and Broadcom DT directory.
 minimal=M/'@Minimal';tmp=[]
 try:
  for src,dst in [(M/'boot',minimal/'boot'),(F,minimal/'boot/firmware'),('/dev',minimal/'dev')]:run('mount','--bind',str(src),str(dst));run('mount','--make-rslave',str(dst));tmp.append(dst)
  run('mount','-t','proc','proc',str(minimal/'proc'));tmp.append(minimal/'proc')
  # Every listed root has the same Pi kernel release, but carries its own full boot set.
  for name in NAMES:
   dest='/'+('@'+name)
   (minimal/'run/port-profile').mkdir(parents=True,exist_ok=True)
   run('mount','--bind',str(M/('@'+name)),str(minimal/'run/port-profile'));tmp.append(minimal/'run/port-profile')
   ch(minimal,'sh','-c',f'. /usr/lib/flipper-bls.sh; FLIPPER_BLS_MIN_KERNEL=6.18; flipper_write_entry @'+name+' /run/port-profile')
   run('umount',str(tmp.pop()))
  ch(minimal,'set-boot-order','--autoboot','@Minimal','-d',p2)
 finally:
  for dst in reversed(tmp):subprocess.run(['umount',str(dst)])
 # Firmware/recovery is stored on FAT, independently of Btrfs.
 artifacts=B/'artifacts'
 while not (artifacts/'u-boot.bin').exists():print('Waiting for Pi U-Boot build',flush=True);time.sleep(5)
 shutil.copyfile(artifacts/'u-boot.bin',F/'u-boot.bin')
 put(F/'config.txt','arm_64bit=1\nenable_uart=1\nkernel=u-boot.bin\ngpu_mem=64\ndisable_overscan=1\n')
 (F/'flipper-bootcount.bin').write_bytes(bytes([0xbd,1,0,1]))
 rec=F/'recovery';rec.mkdir(exist_ok=True);ver=(B/'Minimal.kernel').read_text().strip()

 for dtb in (M/'@Minimal/usr/lib'/('linux-image-'+ver)/'broadcom').glob('*.dtb'):shutil.copyfile(dtb,F/dtb.name)
 shutil.copyfile(M/'@Minimal/usr/lib/modules'/ver/'vmlinuz',rec/'Image');shutil.copyfile(M/'@Minimal/usr/lib/modules'/ver/'initrd',rec/'initramfs')
 script=f'load mmc 0:1 ${{kernel_addr_r}} recovery/Image; load mmc 0:1 ${{ramdisk_addr_r}} recovery/initramfs; setenv rescue_size ${{filesize}}; setenv bootargs console=tty1 console=serial0,115200 root=UUID={rootuuid} rootfstype=btrfs rootflags=subvol=@Minimal rootwait rw net.ifnames=0 break=mount; booti ${{kernel_addr_r}} ${{ramdisk_addr_r}}:${{rescue_size}} ${{fdt_addr}}\n'
 put(B/'recovery-boot.cmd',script);run('mkimage','-A','arm64','-T','script','-C','none','-n','Flipper Pi recovery','-d',str(B/'recovery-boot.cmd'),str(rec/'boot.scr'))
 put(B/'image-board.json',json.dumps({'board':'rpi4-arm64','source_build':1328,'build_id':BUILD,'root_uuid':rootuuid,'firmware_uuid':fatuuid,'profiles':NAMES,'no_qemu':True},indent=2)+'\n')
 run('sync');print('PI IMAGE CONFIGURATION COMPLETE',flush=True)
finally:
 subprocess.run(['umount',str(F)]);subprocess.run(['umount',str(M)]);subprocess.run(['losetup','-d',loop])
