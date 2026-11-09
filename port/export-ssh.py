#!/usr/bin/env python3
"""Stream a closed native Pi disk image over SSH without storing another copy on the Pi."""
import argparse,hashlib,os,pathlib,shlex,sys,paramiko
p=argparse.ArgumentParser();p.add_argument('--remote-image',required=True);p.add_argument('--host',required=True);p.add_argument('--user',required=True);p.add_argument('--known-hosts',required=True);p.add_argument('--output',required=True);p.add_argument('--password-env',default='FLIPPER_PI_PASSWORD');a=p.parse_args()
dest=pathlib.Path(a.output).resolve();temp=dest.with_suffix(dest.suffix+'.part')
if dest.exists() or temp.exists():raise SystemExit('Choose a new output path')
dest.parent.mkdir(parents=True,exist_ok=True)
pw=os.environ[a.password_env];client=paramiko.SSHClient();client.load_host_keys(a.known_hosts);client.set_missing_host_key_policy(paramiko.RejectPolicy());client.connect(a.host,username=a.user,password=pw,look_for_keys=False,allow_agent=False,timeout=15)
image=shlex.quote(a.remote_image)
remote='set -eu; test -f '+image+'; [ -z "$(/usr/sbin/losetup -j '+image+')" ]; exec zstd -T2 -3 -c -- '+image
i,o,e=client.exec_command("sudo -S -p '' sh -c "+shlex.quote(remote),timeout=900);i.write(pw+'\n');i.flush();i.channel.shutdown_write();sha=hashlib.sha256();count=0;mark=0
try:
 with temp.open('xb') as target:
  while True:
   data=o.read(1024*1024)
   if not data:break
   target.write(data);sha.update(data);count+=len(data)
   if count-mark>=128*1024**2:print(str(count//1024**2)+' MiB exported',flush=True);mark=count
 err=e.read().decode();code=o.channel.recv_exit_status()
 if code or not count:raise SystemExit('Export failed: '+err)
 temp.replace(dest);dest.with_suffix(dest.suffix+'.sha256').write_text(sha.hexdigest()+'  '+dest.name+'\n');print(sha.hexdigest(),dest,flush=True)
finally:client.close()
