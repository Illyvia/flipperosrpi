#!/usr/bin/env python3
"""Verify CI images and package release assets below GitHub's per-file size limit."""
import argparse,hashlib,json,pathlib,subprocess,zipfile
CHUNK_BYTES=1_900_000_000

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(8*1024**2),b''):h.update(data)
    return h.hexdigest()

def package(inputs,output):
    output.mkdir(parents=True,exist_ok=True)
    checksums=[];images=[]
    for variant in ['hdmi','waveshare-7-e']:
        directory=inputs/variant
        image=next(directory.glob('*.img.zst'))
        expected=image.with_suffix(image.suffix+'.sha256').read_text().split()[0]
        if digest(image)!=expected:raise ValueError('Image checksum mismatch: '+variant)
        subprocess.run(['zstd','-t',str(image)],check=True)
        parts=[]
        with image.open('rb') as src:
            number=1
            while True:
                data=src.read(min(CHUNK_BYTES,8*1024**2))
                if not data:break
                part=output/(image.name+f'.part{number:02d}')
                with part.open('wb') as target:
                    target.write(data);remaining=CHUNK_BYTES-len(data)
                    while remaining:
                        data=src.read(min(remaining,8*1024**2))
                        if not data:break
                        target.write(data);remaining-=len(data)
                checksums.append((digest(part),part.name));parts.append(part.name);number+=1
        checksums.append((expected,image.name))
        (output/(image.name+'.sha256')).write_text(expected+'  '+image.name+'\n')
        images.append({'variant':variant,'file':image.name,'sha256':expected,'parts':parts})
    (output/'SHA256SUMS').write_text(''.join(sha+'  '+name+'\n' for sha,name in checksums))
    (output/'images.json').write_text(json.dumps(images,indent=2)+'\n')
    with zipfile.ZipFile(output/'validation-reports.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for variant in ['hdmi','waveshare-7-e']:
            for report in (inputs/variant).glob('*.json'):
                archive.write(report,variant+'/'+report.name)
    # Stream parts into a new file; never load the full image into memory.
    (output/'join-image.ps1').write_text('''param([ValidateSet('hdmi','waveshare-7-e')][string]$Display = 'waveshare-7-e')
$ErrorActionPreference = 'Stop'
$images = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'images.json') -Raw | ConvertFrom-Json
$image = $images | Where-Object variant -eq $Display
$destination = Join-Path $PSScriptRoot $image.file
if (Test-Path -LiteralPath $destination) { throw 'Output already exists; move it before running again.' }
$target = [IO.File]::Open($destination, [IO.FileMode]::CreateNew)
try {
    foreach ($part in $image.parts) {
        $source = [IO.File]::OpenRead((Join-Path $PSScriptRoot $part))
        try { $source.CopyTo($target) } finally { $source.Dispose() }
    }
} finally { $target.Dispose() }
if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $image.sha256) {
    throw 'Checksum mismatch. Do not flash this file.'
}
Write-Host "Verified: $destination"
''')
    (output/'join-image.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
case ${1:-waveshare-7-e} in hdmi|waveshare-7-e) display=${1:-waveshare-7-e} ;; *) echo 'Choose hdmi or waveshare-7-e' >&2; exit 1 ;; esac
name="flipperos-rpi4-1328001-$display-orange.img.zst"
[[ ! -e $name ]] || { echo 'Output already exists; move it before running again.' >&2; exit 1; }
set -C
parts=( "$name".part[0-9][0-9] )
[[ -f ${parts[0]} ]] || { echo 'Image parts are missing' >&2; exit 1; }
cat -- "${parts[@]}" > "$name"
sha256sum -c "$name.sha256"
''')
    return images

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args()
    package(a.inputs,a.output)
