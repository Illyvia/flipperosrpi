#!/usr/bin/env python3
"""Fetch signed Raspberry Pi firmware inputs without changing the build host's APT sources."""
import hashlib, json, os, pathlib, shutil, subprocess, sys
if os.geteuid()!=0 or os.uname().machine!='aarch64':raise SystemExit('Native ARM64 root required')
base=pathlib.Path(sys.argv[1]).resolve()
base.mkdir(parents=True,exist_ok=True)
def run(*args,**kw):return subprocess.run([str(a) for a in args],check=True,**kw)
key=base/'raspberrypi.asc'
run('curl','-fsSL','--retry','3','https://archive.raspberrypi.com/debian/raspberrypi.gpg.key','-o',key)
info=subprocess.check_output(['gpg','--show-keys','--with-colons',str(key)],text=True)
if 'fpr:::::::::CF8A1AF502A2AA2D763BAE7E82B129927FA3303E:' not in info:raise SystemExit('Unexpected Raspberry Pi signing key')
keyring=base/'usr/share/keyrings/raspberrypi-archive-keyring.pgp';keyring.parent.mkdir(parents=True,exist_ok=True)
run('gpg','--batch','--yes','--dearmor','-o',keyring,key)
sources=base/'etc/apt/sources.list.d/raspi.sources';sources.parent.mkdir(parents=True,exist_ok=True)
sources.write_text('Types: deb\nURIs: https://archive.raspberrypi.com/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp\n')
host_sources=base/'apt.sources';host_sources.write_text(sources.read_text().replace('/usr/share/keyrings/raspberrypi-archive-keyring.pgp',str(keyring)))
state=base/'apt';(state/'lists/partial').mkdir(parents=True,exist_ok=True);(state/'archives/partial').mkdir(parents=True,exist_ok=True);(state/'status').touch()
opts=['-o','Dir::Etc::sourcelist='+str(host_sources),'-o','Dir::Etc::sourceparts=-','-o','Dir::State::lists='+str(state/'lists'),'-o','Dir::State::status='+str(state/'status'),'-o','Dir::Cache::archives='+str(state/'archives'),'-o','APT::Architecture=arm64','-o','APT::Sandbox::User=root']
run('apt-get',*opts,'update')
meta=subprocess.check_output(['apt-cache',*opts,'show','linux-image-rpi-v8'],text=True)
real=next(line.split(': ',1)[1].split()[0] for line in meta.splitlines() if line.startswith('Depends: linux-image-'))
run('apt-get',*opts,'download','raspi-firmware',real,cwd=base)
packages=[]
for deb in base.glob('*.deb'):
 packages.append({'file':deb.name,'sha256':hashlib.sha256(deb.read_bytes()).hexdigest()})
 run('dpkg-deb','-x',deb,base)
firmware=base/'boot/firmware';firmware.mkdir(parents=True,exist_ok=True)
for f in (base/'usr/lib/raspi-firmware').iterdir():
 if f.is_file():shutil.copyfile(f,firmware/f.name)
dt=next((base/'usr/lib').glob('linux-image-*/broadcom'))
for f in dt.glob('*.dtb'):shutil.copyfile(f,firmware/f.name)
shutil.copytree(dt.parent/'overlays',firmware/'overlays',dirs_exist_ok=True)
(base/'board-packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print('Signed board inputs ready:',real)
