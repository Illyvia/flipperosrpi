#!/usr/bin/env python3
"""Configure DSI or HDMI in an owned Pi image, without executing ARM code on the host."""
import argparse, json, os, pathlib, shutil, subprocess, sys, runpy

if os.environ.get('FLIPPER_PRIVATE_MOUNT_NS') != '1':
    os.execvp('unshare', ['unshare', '--mount', '--propagation', 'private', 'env',
                         'FLIPPER_PRIVATE_MOUNT_NS=1', sys.executable, *sys.argv])
p = argparse.ArgumentParser()
p.add_argument('--image', type=pathlib.Path, required=True)
p.add_argument('--project', type=pathlib.Path, required=True)
p.add_argument('--dtmerge', type=pathlib.Path, required=True, help='native build-host dtmerge')
p.add_argument('--report', type=pathlib.Path, required=True)
p.add_argument('--ui', type=pathlib.Path, help='updated full ARM64 launcher')
p.add_argument('--wifi', type=pathlib.Path, help='private working NetworkManager keyfile')
p.add_argument('--preset', choices=['hdmi', 'waveshare-7-e'], default='waveshare-7-e')
p.add_argument('--display-config', type=pathlib.Path)
p.add_argument('--tint', choices=['grayscale', 'orange'])
p.add_argument('--metadata', type=pathlib.Path)
a = p.parse_args()
if a.image.is_symlink(): raise SystemExit('Image path must not be a symlink')
image = a.image.resolve(); project = a.project.resolve()
if os.geteuid() != 0 or not image.is_file() or image.is_symlink():
    raise SystemExit('Root and a regular image file are required')
if image.stat().st_size != 8589934592:
    raise SystemExit('Expected the 8 GiB Flipper Pi candidate')

def run(*args, **kw): return subprocess.run([str(x) for x in args], check=True, **kw)
def out(*args, **kw): return subprocess.check_output([str(x) for x in args], text=True, **kw).strip()
if out('losetup', '-j', image): raise SystemExit('Image is already attached')
meta = json.loads((a.metadata or project/'build/full-os/image-board.json').read_text())
display = runpy.run_path(str(project/'port/board-files/usr/local/sbin/flipper-display'))
config_path = a.display_config or project/'port/board-files/usr/share/flipper-rpi/displays'/(a.preset+'.json')
config = display['read_config'](config_path)
if a.tint: config['tint'] = a.tint
build = project/'build/full-os'
ui = a.ui or build/'flipctl'
dtmerge_arm = project/'build/full-os/dtmerge'
fdtoverlay = project/'build/dsi-tools/fdtoverlay-host'
for artifact in [ui, dtmerge_arm, fdtoverlay, project/'build/full-os/u-boot.bin']:
    if not artifact.is_file(): raise SystemExit('Missing build artifact: '+str(artifact))
if b'FLIPPER_WL_TINT' not in ui.read_bytes(): raise SystemExit('Rebuild the full Pi UI with the current display patch first')
mount = image.parent/'dsi-mnt'; fat = image.parent/'dsi-fat'
mount.mkdir(exist_ok=True); fat.mkdir(exist_ok=True)
loop = out('losetup', '--find', '--show', '--partscan', image)
mounted = []; changed_stocks = []; report = []
try:
    if pathlib.Path(out('losetup','-n','-O','BACK-FILE',loop)).resolve() != image:
        raise SystemExit('Loop backing-file mismatch')
    if out('blkid','-s','UUID','-o','value',loop+'p2') != meta['root_uuid']:
        raise SystemExit('Wrong image filesystem identity')
    run('mount','-t','btrfs','-o','subvolid=5,compress=zstd:3,noatime',loop+'p2',mount); mounted.append(mount)
    run('mount',loop+'p1',fat); mounted.append(fat)
    prepared_config = image.parent/'selected-display.json'
    prepared_config.write_text(json.dumps(config, indent=2)+'\n')
    for name in meta['profiles']:
        stock = mount/'@stock-snapshots'/('@'+name+'_1328001_stock')
        for root in [stock, mount/('@'+name)]:
            if 'IMAGE_ID=flipperos-rpi4' not in (root/'etc/os-release').read_text():
                raise SystemExit('Unexpected profile identity: '+str(root))
            readonly = root == stock
            if readonly:
                run('btrfs','property','set',root,'ro','false'); changed_stocks.append(root)
            run(sys.executable, project/'port/patch-bls-library.py', root)
            run(sys.executable, project/'port/install-display.py', root, '--profile', name,
                '--config', prepared_config, '--dtmerge', a.dtmerge)
            for src,rel in [(ui,'usr/bin/flipctl'), (dtmerge_arm,'usr/local/bin/flipper-dtmerge')]:
                dest=root/rel; dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dest);dest.chmod(0o755)
            if a.wifi and name != 'Router':
                net=root/'etc/NetworkManager/system-connections'
                for old in net.glob('*.nmconnection'):old.unlink()
                net.mkdir(parents=True,exist_ok=True)
                connection=net/'flipper-wifi.nmconnection'
                shutil.copyfile(a.wifi,connection);connection.chmod(0o600)
                os.chown(connection,0,0)
            ver='6.18.60+rpt-rpi-v8'
            dt=root/'usr/lib'/('linux-image-'+ver)/'broadcom'
            base=dt/'bcm2711-rpi-4-b.dtb'
            if name != 'No-Graphics':
                validation=image.parent/('display-validated-'+name+'.dtb')
                run(fdtoverlay,'-i',base,'-o',validation,dt/'vc4-kms-v3d.dtbo')
                tree=out('dtc','-I','dtb','-O','dts',validation,stderr=subprocess.DEVNULL)
                if config['output']=='dsi' and config['panel']['overlay']=='vc4-kms-dsi-waveshare-panel':
                    if 'waveshare' not in tree or 'goodix' not in tree:
                        raise SystemExit('Expected panel/touch nodes missing')
            run('systemd-analyze','--root='+str(root),'verify','flipctl.service','flipctl-display.service')
            kconfig=(root/'usr/lib/modules'/ver/'config').read_text()
            for flag in (['CONFIG_TOUCHSCREEN_GOODIX=m','CONFIG_DRM_PANEL_WAVESHARE_TOUCHSCREEN=m','CONFIG_REGULATOR_WAVESHARE_TOUCHSCREEN=m'] if config['output']=='dsi' and config['panel']['overlay']=='vc4-kms-dsi-waveshare-panel' else ['CONFIG_DRM_VC4=m']):
                if flag not in kconfig:raise SystemExit('Missing panel kernel support: '+flag)
            if readonly:
                run('btrfs','property','set',root,'ro','true');changed_stocks.remove(root)
        report.append({'profile':name,'stock_and_active_updated':True,'local_flipper_session':name in ['Minimal','Router'],'panel_dt_validated':name!='No-Graphics'})
    cfg=fat/'config.txt';text=cfg.read_text()
    shutil.copyfile(project/'build/full-os/u-boot.bin',fat/'u-boot.bin')
    run(sys.executable, project/'port/patch-bls-library.py', mount/'@Minimal',
        '--entries', mount/'boot/loader/entries')
    cfg.write_text(display['firmware_text'](text,config))
    display['atomic_write'](mount/'boot/flipper-rpi/display.json',(json.dumps(config,indent=2)+'\n').encode())
    run('sync')
    a.report.write_text(json.dumps({'variant':'configurable-display','display':config,'profiles':report,'qemu_used':False,
        'offline_filesystem_edit':True,'arm_binaries_executed_on_build_host':False,
        'physical_display_tested':False,'physical_touch_tested':False},indent=2)+'\n')
    print('DISPLAY IMAGE CONFIGURATION PASSED',flush=True)
finally:
    for root in changed_stocks: subprocess.run(['btrfs','property','set',str(root),'ro','true'])
    for path in reversed(mounted): subprocess.run(['umount',str(path)])
    subprocess.run(['losetup','-d',loop])
