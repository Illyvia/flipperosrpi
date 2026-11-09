#!/usr/bin/env python3
"""Remove generated identities and verify public-image network configuration in an owned loop image."""
import json,os,pathlib,re,subprocess,sys,tempfile
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root required')
if os.environ.get('FLIPPER_PRIVATE_MOUNT_NS')!='1':os.execvp('unshare',['unshare','--mount','--propagation','private','env','FLIPPER_PRIVATE_MOUNT_NS=1',sys.executable,*sys.argv])
image=pathlib.Path(sys.argv[1]).resolve();meta=json.loads(pathlib.Path(sys.argv[2]).read_text())
if not image.is_file() or image.stat().st_size!=8589934592:raise SystemExit('Expected regular 8 GiB image')
def out(*args):return subprocess.check_output([str(a) for a in args],text=True).strip()
def run(*args):return subprocess.run([str(a) for a in args],check=True)
if out('losetup','-j',image):raise SystemExit('Image already attached')
loop=out('losetup','--find','--show','--partscan',image);readonly=[];removed=[]
with tempfile.TemporaryDirectory(prefix='flipper-public-') as tmp:
 top=pathlib.Path(tmp);mounted=False
 try:
  if pathlib.Path(out('losetup','-n','-O','BACK-FILE',loop)).resolve()!=image:raise SystemExit('Wrong loop backing file')
  if out('blkid','-s','UUID','-o','value',loop+'p2')!=meta['root_uuid']:raise SystemExit('Wrong image identity')
  run('mount','-t','btrfs','-o','subvolid=5',loop+'p2',top);mounted=True
  roots=[*top.glob('@*'),*(top/'@stock-snapshots').glob('@*')]
  roots=[r for r in roots if (r/'etc/os-release').is_file() and 'IMAGE_ID=flipperos-rpi4' in (r/'etc/os-release').read_text()]
  if len(roots)!=10:raise SystemExit('Expected five active profiles and five stocks')
  for root in roots:
   if out('btrfs','property','get',root,'ro')=='ro=true':run('btrfs','property','set',root,'ro','false');readonly.append(root)
   for f in (root/'etc/ssh').glob('ssh_host_*'):
    if f.is_file() or f.is_symlink():removed.append(str(f.relative_to(top)));f.unlink()
   machine=root/'etc/machine-id'
   if machine.is_symlink():machine.unlink()
   machine.write_text('')
   # The runner's build-time DNS address is not usable on a flashed Pi.
   resolv=root/'etc/resolv.conf'
   resolv.unlink(missing_ok=True)
   resolv.symlink_to('/run/NetworkManager/resolv.conf')
   dbus=root/'var/lib/dbus/machine-id'
   if dbus.is_file() and not dbus.is_symlink():dbus.write_text('')
   connections=root/'etc/NetworkManager/system-connections'
   for f in connections.glob('*'):
    if not f.is_file():continue
    text=f.read_text()
    if 'Router' not in root.name:raise SystemExit('Unexpected network keyfile in '+root.name)
    secrets=re.findall(r'(?m)^(?:psk|password|private-key-password)=(.*)$',text)
    if any(value!='flipperone' for value in secrets):raise SystemExit('Unexpected router credentials')
   # Build-time package installation must not leave an identity in root's home.
   for sshdir in [root/'root/.ssh']:
    for f in sshdir.glob('*'):
     if f.is_file() or f.is_symlink():removed.append(str(f.relative_to(top)));f.unlink()
  for sshdir in [*(top/'@home').glob('*/.ssh'),top/'@home/.flipper-system']:
   for f in sshdir.glob('*'):
    if f.is_file() or f.is_symlink():removed.append(str(f.relative_to(top)));f.unlink()
  for root in roots:
   if list((root/'etc/ssh').glob('ssh_host_*')):raise SystemExit('Host identity remains')
  os.sync()
  image.with_name('public-image-check.json').write_text(json.dumps({'profile_roots_checked':len(roots),'private_wifi_present':False,'host_keys_removed':True,'machine_ids_reset':True,'dns_managed_by_networkmanager':True,'removed_identity_files':removed},indent=2)+'\n')
  print('PUBLIC IMAGE IDENTITY CHECK PASSED')
 finally:
  for root in readonly:subprocess.run(['btrfs','property','set',str(root),'ro','true'],check=True)
  if mounted:run('umount',top)
  run('losetup','-d',loop)
