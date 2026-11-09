#!/usr/bin/env python3
"""Install display support on an existing physical Flipper OS Pi, with file backups."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

if os.geteuid() != 0 or os.uname().machine != 'aarch64':
    raise SystemExit('Run with sudo on the physical ARM64 Pi; no emulation')
if os.environ.get('FLIPPER_PRIVATE_MOUNT_NS') != '1':
    os.execvp('unshare', ['unshare', '--mount', '--propagation', 'private', 'env',
                         'FLIPPER_PRIVATE_MOUNT_NS=1', sys.executable, *sys.argv])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--ui', type=Path, required=True)
p.add_argument('--dtmerge', type=Path, required=True)
p.add_argument('--preset', choices=['waveshare-7-e', 'hdmi'], required=True)
p.add_argument('--tint', choices=['grayscale', 'orange'], default='grayscale')
a = p.parse_args()
if 'IMAGE_ID=flipperos-rpi4' not in Path('/etc/os-release').read_text():
    raise SystemExit('This installer requires the full Flipper OS Pi port')
if b'FLIPPER_WL_TINT' not in a.ui.read_bytes():
    raise SystemExit('Build the current full Pi launcher before installation')
if a.ui.read_bytes()[:4] != b'\x7fELF' or a.ui.read_bytes()[18:20] != b'\xb7\x00':
    raise SystemExit('The launcher must be an ARM64 ELF executable')

project = Path(__file__).resolve().parents[1]
board = project/'port/board-files'
display = runpy.run_path(str(board/'usr/local/sbin/flipper-display'))
c = display['read_config'](board/'usr/share/flipper-rpi/displays'/(a.preset+'.json'))
c['tint'] = a.tint
backup = Path('/home/user/flipper-port-backups')/('display-'+time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, mode=0o700)
device = subprocess.check_output(['findmnt', '-no', 'SOURCE', '/'], text=True).strip().split('[')[0]
if not re.fullmatch(r'/dev/mmcblk[0-9]+p[0-9]+|/dev/sd[a-z]+[0-9]+|/dev/nvme[0-9]+n[0-9]+p[0-9]+', device):
    raise SystemExit('Unexpected Pi root device')
for src in [Path('/boot/firmware/config.txt'), Path('/boot/flipper-rpi/display.json')]:
    if src.exists(): shutil.copyfile(src, backup/src.name)

def run(*args, **kw): return subprocess.run([str(x) for x in args], check=True, **kw)
with tempfile.TemporaryDirectory(prefix='flipper-install.', dir='/run') as temp:
    top = Path(temp)/'top'; top.mkdir()
    config = Path(temp)/'display.json'; config.write_text(json.dumps(c)+'\n')
    run('mount', '-t', 'btrfs', '-o', 'subvolid=5', device, top)
    readonly = []
    try:
        roots = [*top.glob('@*'), *(top/'@stock-snapshots').glob('@*')]
        roots = [r for r in roots if (r/'etc/os-release').is_file()
                 and 'IMAGE_ID=flipperos-rpi4' in (r/'etc/os-release').read_text()]
        affected = ['usr/bin/flipctl', 'usr/local/bin/flipper-dtmerge',
                    'usr/local/sbin/flipper-display', 'etc/flipper-rpi',
                    'usr/local/libexec/flipper-dsi-client',
                    'etc/kernel/install.d/54-flipper-rpi-kernel.install',
                    'etc/systemd/system/flipctl-dsi.service',
                    'etc/systemd/system/flipctl-display.service',
                    'etc/systemd/system/multi-user.target.wants/flipctl-dsi.service',
                    'etc/systemd/system/multi-user.target.wants/flipctl-display.service',
                    'etc/systemd/system/multi-user.target.wants/flipctl.service']
        with tarfile.open(backup/'profile-files.tar.gz', 'w:gz', dereference=False) as tar:
            for root in roots:
                for rel in affected:
                    src = root/rel
                    if src.exists() or src.is_symlink(): tar.add(src, arcname=str(src.relative_to(top)))
        # Confirm the new executable runs in the actual ARM64 userspace before replacing it.
        a.ui.chmod(0o755)
        run(a.ui, '--png', Path(temp)/'native-render.png', '--screen', 'main')
        subprocess.run(['systemctl', 'stop', 'flipctl-dsi.service', 'flipctl-display.service', 'flipctl.service'], check=False)
        for root in roots:
            prop = subprocess.check_output(['btrfs','property','get',str(root),'ro'], text=True).strip()
            if prop == 'ro=true':
                run('btrfs', 'property', 'set', root, 'ro', 'false'); readonly.append(root)
            profile = root.name.lstrip('@').split('_')[0]
            run(sys.executable, project/'port/install-display.py', root, '--profile', profile,
                '--config', config, '--no-kernel')
            for src, rel in [(a.ui, 'usr/bin/flipctl'), (a.dtmerge, 'usr/local/bin/flipper-dtmerge')]:
                dest = root/rel; dest.parent.mkdir(parents=True, exist_ok=True)
                nextfile = dest.with_name(dest.name+'.next')
                shutil.copyfile(src, nextfile); nextfile.chmod(0o755); nextfile.replace(dest)
    finally:
        for root in readonly: run('btrfs', 'property', 'set', root, 'ro', 'true')
        run('umount', top)
display = runpy.run_path('/usr/local/sbin/flipper-display')
display['apply_to_device'](c, Path('/boot/flipper-rpi/display.json'))
run('systemctl', 'daemon-reload')
run('systemd-analyze', 'verify', 'flipctl-display.service')
current = subprocess.check_output(['findmnt', '-no', 'FSROOT', '/'], text=True).strip().lstrip('/@')
if current in ['Minimal', 'Router']:
    run('systemctl', 'start', 'flipctl-display.service')
else:
    run('systemctl', 'start', 'flipctl.service')
print('Installed display support. Backups:', backup)
print('Reboot is required if changing between DSI and HDMI hardware modes.')
