#!/usr/bin/env python3
"""Capture four native compositor presentation cases; requires sway, grim and built probe."""
import json, os, pathlib, subprocess, tempfile, time
from PIL import Image
root=pathlib.Path(__file__).resolve().parents[1]
probe=root/'build/host-display-target/debug/examples/wl_sink_probe'
module=root/'port/board-files/usr/local/sbin/flipper-display'
results=[]
for output,mode in [('dsi','1280x800'),('hdmi','1920x1080')]:
 for tint in ['grayscale','orange']:
  with tempfile.TemporaryDirectory(prefix='flipper-visual-') as tmp:
   runtime=pathlib.Path(tmp);runtime.chmod(0o700)
   preset='waveshare-7-e' if output=='dsi' else 'hdmi'
   config=json.loads((root/f'port/board-files/usr/share/flipper-rpi/displays/{preset}.json').read_text())
   config.update(tint=tint,mode=mode)
   path=runtime/'display.json';path.write_text(json.dumps(config))
   env=dict(os.environ,XDG_RUNTIME_DIR=tmp,WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_HEADLESS_OUTPUTS='1',FLIPPER_DISPLAY_HEADLESS_TEST='1',FLIPCTL_BIN=str(probe))
   log=root/f'build/visual-{output}-{tint}.log'
   with log.open('w') as f:
    proc=subprocess.Popen(['python3',str(module),'--config',str(path),'session'],env=env,stdout=f,stderr=f)
    try:
     for _ in range(100):
      sockets=list(runtime.glob('sway-ipc.*.sock'))
      if sockets and 'surface up' in log.read_text():break
      if proc.poll() is not None:raise RuntimeError(log.read_text())
      time.sleep(.1)
     else:raise RuntimeError('No frame: '+log.read_text())
     env['SWAYSOCK']=str(sockets[0]);env['WAYLAND_DISPLAY']='wayland-1'
     # Discover the compositor's actual Wayland socket.
     env['WAYLAND_DISPLAY']=next(x.name for x in runtime.glob('wayland-*') if not x.name.endswith('.lock'))
     dest=root/f'build/visual-{output}-{tint}.png'
     subprocess.run(['grim','-o','HEADLESS-1',str(dest)],env=env,check=True)
     im=Image.open(dest).convert('RGB');expected=tuple(map(int,mode.split('x')));assert all(abs(a-b)<=1 for a,b in zip(im.size,expected)),im.size
     colors=im.getdata(); maximum=max(colors,key=lambda c:sum(c))
     assert maximum==((255,255,255) if tint=='grayscale' else (255,130,0)),maximum
     assert im.getpixel((0,0))==(0,0,0)
     results.append({'output':output,'tint':tint,'size':im.size,'white':maximum})
    finally:
     if proc.poll() is None:
      subprocess.run(['swaymsg','exit'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
      proc.wait(timeout=10)
print(json.dumps(results,indent=2))
