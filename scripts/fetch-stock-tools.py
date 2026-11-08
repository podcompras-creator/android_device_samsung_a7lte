#!/usr/bin/env python3
"""Fetch pinned official Debian amd64 image tools without sudo or system changes."""
import argparse, hashlib, json, os, platform, subprocess, sys, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',action='store_true',help='verify/extract cached packages only')
    a=p.parse_args()
    if platform.machine() not in ('x86_64','amd64'):
        p.error('Pinned Debian amd64 executables require an x86_64 Linux host')
    lock=json.loads((ROOT/'host-tools.lock.json').read_text())
    cache=ROOT/'host-packages/stock-tools'; dest=ROOT/'host/stock-tools'
    cache.mkdir(parents=True,exist_ok=True); dest.mkdir(parents=True,exist_ok=True)
    total=0
    for package in lock['packages']:
        archive=cache/package['file']; total+=package['bytes']
        if total>100*1024**2: raise ValueError('Package lock exceeds 100 MiB budget')
        if not archive.exists():
            if a.offline: raise FileNotFoundError(archive)
            with urllib.request.urlopen(package['url'],timeout=45) as response:
                data=response.read(package['bytes']+1)
            if len(data)!=package['bytes'] or hashlib.sha256(data).hexdigest()!=package['sha256']:
                raise ValueError('Downloaded package does not match lock: '+package['file'])
            archive.write_bytes(data)
        if archive.stat().st_size!=package['bytes'] or hashlib.sha256(archive.read_bytes()).hexdigest()!=package['sha256']:
            raise ValueError('Cached package does not match lock: '+package['file'])
        subprocess.run(['dpkg-deb','-x',str(archive),str(dest)],check=True)
    bindir=dest/'bin';bindir.mkdir(exist_ok=True)
    for name,relative in {'simg2img':'usr/bin/simg2img','img2simg':'usr/bin/img2simg','lz4':'usr/bin/lz4','debugfs':'usr/sbin/debugfs','mke2fs':'usr/sbin/mke2fs','mkfs.ext4':'usr/sbin/mkfs.ext4'}.items():
        wrapper=bindir/name
        wrapper.write_text('#!/bin/sh\nset -eu\nSTOCK_TOOLS_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\nexport LD_LIBRARY_PATH="$STOCK_TOOLS_ROOT/usr/lib/x86_64-linux-gnu/android:$STOCK_TOOLS_ROOT/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\nexport MKE2FS_CONFIG="$STOCK_TOOLS_ROOT/etc/mke2fs.conf"\nexec "$STOCK_TOOLS_ROOT/'+relative+'" "$@"\n')
        wrapper.chmod(0o755)
    for name,args in [('lz4',['--version']),('debugfs',['-V']),('mke2fs',['-V'])]:
        subprocess.run([str(bindir/name),*args],check=True)
    print('Ready. Add to PATH: '+str(bindir))
    print('Uses host runtime libraries listed in host-tools.lock.json; no system package was installed.')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);raise SystemExit(1)
