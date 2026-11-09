#!/usr/bin/env python3
"""Check the compiled Pi configuration against the startup command it contains."""
import pathlib, sys
config = pathlib.Path(sys.argv[1]).read_text()
settings = dict(line.split('=', 1) for line in config.splitlines()
                if line.startswith('CONFIG_') and '=' in line)
required = ['CONFIG_FS_BTRFS', 'CONFIG_BOOTMETH_BLS', 'CONFIG_FAT_WRITE']
if 'bootflow scan -' in settings.get('CONFIG_BOOTCOMMAND', ''):
    required += ['CONFIG_BOOTSTD_FULL', 'CONFIG_CMD_BOOTFLOW_FULL']
missing = [name for name in required if settings.get(name) != 'y']
if missing:
    raise SystemExit('FAIL: startup command requires '+', '.join(missing))
if len(sys.argv) > 2:
    binary = pathlib.Path(sys.argv[2]).read_bytes()
    if b'fdtoverlay_addr_r=0x0a000000' not in binary:
        raise SystemExit('FAIL: compiled Pi environment lacks overlay load address')
print('PASS: compiled U-Boot supports its configured startup command and filesystems')
