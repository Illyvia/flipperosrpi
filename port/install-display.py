#!/usr/bin/env python3
"""Install the display interface into an explicitly supplied Pi profile root."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

p = argparse.ArgumentParser()
p.add_argument('root', type=Path)
p.add_argument('--profile', required=True)
p.add_argument('--config', type=Path)
p.add_argument('--dtmerge', default='/usr/local/bin/flipper-dtmerge')
p.add_argument('--no-kernel', action='store_true')
a = p.parse_args()
board = Path(__file__).resolve().parent/'board-files'
module = runpy.run_path(str(board/'usr/local/sbin/flipper-display'))
c = module['read_config'](a.config or board/'etc/flipper-rpi/display.json')
files = ['usr/local/sbin/flipper-display', 'etc/systemd/system/flipctl-display.service',
         'etc/systemd/system/flipper-rpi-restore-order.service',
         'etc/kernel/install.d/54-flipper-rpi-kernel.install']
files += [str(f.relative_to(board)) for f in (board/'usr/share/flipper-rpi/displays').glob('*.json')]
if 'IMAGE_ID=flipperos-rpi4' not in (a.root/'etc/os-release').read_text():
    raise SystemExit('Target is not a Flipper OS Pi profile')
for rel in files:
    src = board/rel; dest = a.root/rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink(): dest.unlink()
    shutil.copyfile(src, dest)
    dest.chmod(0o755 if src.read_bytes().startswith(b'#!') else 0o644)
config = a.root/'etc/flipper-rpi/display.json'
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(json.dumps(c, indent=2)+'\n')
config.chmod(0o644)
unitdir = a.root/'etc/systemd/system'
legacy = unitdir/'flipctl-dsi.service'
legacy.unlink(missing_ok=True)
legacy.symlink_to('flipctl-display.service')
wants = unitdir/'multi-user.target.wants'; wants.mkdir(exist_ok=True)
gui = a.profile in ['Minimal', 'Router'] or any((wants/u).is_symlink()
      for u in ['flipctl-dsi.service', 'flipctl-display.service'])
for unit in ['flipctl-dsi.service', 'flipctl-display.service', 'flipctl.service']:
    (wants/unit).unlink(missing_ok=True)
session = 'flipctl-display.service' if gui else 'flipctl.service'
(wants/session).symlink_to('/etc/systemd/system/'+session)
for legacy in ['etc/flipper-rpi/dsi-panel.conf', 'etc/flipper-rpi/sway-dsi.conf',
               'usr/local/libexec/flipper-dsi-client']:
    (a.root/legacy).unlink(missing_ok=True)
if not a.no_kernel:
    for dt in (a.root/'usr/lib').glob('linux-image-*'):
        for dest, data in module['kernel_plan'](a.root, dt.name.removeprefix('linux-image-'), c, a.dtmerge):
            module['atomic_write'](dest, data)
print('Display installed:', a.profile, c['output'], c['tint'])
