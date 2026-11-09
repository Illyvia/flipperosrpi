#!/usr/bin/env python3
"""Audit staged public files and produce a source-only ZIP without ignored artifacts."""
import hashlib,pathlib,re,subprocess,zipfile
root=pathlib.Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','-C',str(root),'diff','--cached','--name-only','-z']).decode().split('\0')
files=[n for n in files if n]
if not files:raise SystemExit('Stage the intended source files first')
for name in files:
 p=root/name
 if name.startswith(('build/','upstream/','.git/')) or p.suffix in ['.img','.zst','.nmconnection','.pem','.key']:
  raise SystemExit('Private/generated file staged: '+name)
 if p.stat().st_size>2*1024**2:raise SystemExit('Unexpected large source file: '+name)
 data=p.read_bytes()
 if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----|192\.168\.1\.252|C:\\Users\\Owner',data):
  raise SystemExit('Private material in '+name)
 # Require packaged bytes to equal the reviewed staged version.
 staged=subprocess.check_output(['git','-C',str(root),'show',':'+name])
 if staged!=data.replace(b'\r\n', b'\n'):raise SystemExit('Restage modified file: '+name)
out=root/'build/flipperos-rpi-source.zip';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for name in files:z.writestr('flipperos-rpi/'+name,subprocess.check_output(['git','-C',str(root),'show',':'+name]))
sha=hashlib.sha256(out.read_bytes()).hexdigest()
out.with_suffix('.zip.sha256').write_text(sha+'  '+out.name+'\n')
print(len(files),'source files;',out.stat().st_size,'bytes;',sha)
