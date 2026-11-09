#!/usr/bin/env python3
"""Keep the Pi's console arguments when upstream generates new BLS entries."""
import argparse, pathlib, re
p = argparse.ArgumentParser()
p.add_argument('root', type=pathlib.Path)
p.add_argument('--entries', type=pathlib.Path)
a = p.parse_args()
lib = a.root/'usr/lib/flipper-bls.sh'
text = lib.read_text()
text = re.sub(r'    if has_config FIQ_DEBUGGER_CONSOLE; then\n.*?\n    fi\n(?=})',
              '    # Pi console arguments are already defined in /etc/kernel/cmdline.\n',
              text, count=1, flags=re.S)
lib.write_text(text)
cmdline = a.root/'etc/kernel/cmdline'
if cmdline.exists():
    options = [t for t in cmdline.read_text().split() if not t.startswith('cma=')]
    options.append('cma=256M')
    cmdline.write_text(' '.join(options)+'\n')
if a.entries:
    remove = {'console=ttyS0,1500000n8', 'console=ttyS4,1500000n8',
              'console=ttyFIQ0,1500000n8', 'fbcon=map:1'}
    for f in a.entries.glob('*.conf'):
        lines = f.read_text().splitlines()
        lines = [('options    '+' '.join(t for t in line.split()[1:] if t not in remove and not t.startswith('cma='))+' cma=256M')
                 if line.split() and line.split()[0] == 'options' else line for line in lines]
        f.write_text('\n'.join(lines)+'\n')
print('Pi BLS console arguments preserved:', a.root)
