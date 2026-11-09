#!/usr/bin/env python3
"""Probe the image's graphics userspace on the physical Pi's current kernel; no image boot."""
import os,sys,pathlib,subprocess,re,json
if os.environ.get('FLIPPER_PRIVATE_MOUNT_NS')!='1':os.execvp('unshare',['unshare','--mount','--propagation','private','env','FLIPPER_PRIVATE_MOUNT_NS=1',sys.executable,*sys.argv])
B=pathlib.Path(os.environ.get('FLIPPER_BUILD_ROOT', '/var/tmp/flipperos-rpi-full')).resolve();IMG=B/'flipperos-rpi4.img';R=B/'graphics-check';R.mkdir(exist_ok=True)
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root required')
if subprocess.check_output(['losetup','-j',str(IMG)],text=True).strip():raise SystemExit('Image is attached')
def run(*a,**kw):return subprocess.run(a,check=True,**kw)
loop=subprocess.check_output(['losetup','--read-only','--find','--show','--partscan',str(IMG)],text=True).strip()
try:
 run('udevadm','settle');run('mount','-t','btrfs','-o','ro,rescue=nologreplay,subvol=@Minimal',loop+'p2',str(R))
 for src,dst in [('/dev',R/'dev'),('/sys',R/'sys')]:run('mount','--bind',src,str(dst))
 run('mount','-t','proc','proc',str(R/'proc'));run('mount','-t','tmpfs','tmpfs',str(R/'run'));(R/'run/egl-check').mkdir(mode=0o700)
 env={**os.environ,'EGL_PLATFORM':'surfaceless','XDG_RUNTIME_DIR':'/run/egl-check','MESA_SHADER_CACHE_DISABLE':'true'}
 probe=subprocess.run(['chroot',str(R),'/usr/bin/eglinfo','-B'],capture_output=True,text=True,env=env,timeout=60)
 text=probe.stdout+probe.stderr;(B/'graphics-native.log').write_text(text)
 ok=bool(re.search(r'EGL driver name:\s*v3d\b|OpenGL[^\n]*renderer[^\n]*V3D',text,re.I))
 lines=[x for x in text.splitlines() if re.search(r'vendor|renderer|driver name|version string',x,re.I)]
 print('\n'.join(lines[:35]))
 report={'physical_architecture':os.uname().machine,'builder_kernel':os.uname().release,'image_kernel_booted':False,'hardware_v3d_initialized':ok,'eglinfo_exit':probe.returncode,'qemu_used':False}
 (B/'graphics-native.json').write_text(json.dumps(report,indent=2)+'\n')
 if not ok:raise SystemExit('V3D GPU initialization was not confirmed; inspect graphics-native.log')
 print('PASS: image userspace initialized native Pi V3D graphics',flush=True)
finally:
 subprocess.run(['umount','-R',str(R)]);subprocess.run(['losetup','-d',loop])
