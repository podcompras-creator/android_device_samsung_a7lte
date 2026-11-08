#!/usr/bin/env python3
"""Apply only this port's owned changes; never reset a destination checkout."""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument('--tree',required=True,type=Path); p.add_argument('--check-only',action='store_true'); a=p.parse_args(); tree=a.tree.resolve()

def git(where,*args):
    return subprocess.run(['git','-C',str(where),*args],text=True,capture_output=True)

def no_symlinks(path):
    for item in [path,*path.parents]:
        if item==tree.parent: break
        if item.is_symlink(): p.error(f'managed path contains symlink: {item}')
    if path.is_dir() and any(x.is_symlink() for x in path.rglob('*')): p.error(f'managed tree contains symlink: {path}')

def safe_rel(name):
    r=PurePosixPath(name)
    if r.is_absolute() or '..' in r.parts or str(r)!=name: p.error('unsafe managed receipt path')
    return name

def hashes(path):
    return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.rglob('*')) if p.is_file() and '.git' not in p.parts and p.name not in {'partition-sizes.mk','layout-report.json'}}

lock=json.loads((ROOT/'sources.lock.json').read_text())
checks=[('common','device/samsung/msm8916-common','common-lineage16.patch'),('kernel','kernel/samsung/msm8916','kernel-host-dtc.patch'),('sepolicy-legacy','device/qcom/sepolicy-legacy','qcom-sepolicy-a7lte.patch')]
patches=[]
for source,dest,patch in checks:
    target=tree/dest
    # Repository .git metadata may be a git worktree file; only owned content is copied.
    for ancestor in [target,*target.parents]:
        if ancestor==tree.parent: break
        if ancestor.is_symlink(): p.error(f'repository path contains symlink: {ancestor}')
    expected=next(x['revision'] for x in lock if x['path']=='sources/'+source)
    result=git(target,'rev-parse','HEAD')
    if result.returncode or result.stdout.strip()!=expected: p.error(f'{dest}: expected pinned checkout {expected}')
    patch=ROOT/'patches'/patch
    if not patch.is_file(): p.error(f'missing patch {patch}')
    if git(target,'apply','--check',str(patch)).returncode==0: patches.append((target,patch))
    elif git(target,'apply','--reverse','--check',str(patch)).returncode: p.error(f'{dest}: patch conflicts with local changes')
variant=Path('arch/arm/configs/msm8939_sec_a7_eur_defconfig')
variant_src=ROOT/'patches'/variant.name
variant_dest=tree/'kernel/samsung/msm8916'/variant
no_symlinks(variant_dest)
if variant_dest.exists() and variant_dest.read_bytes()!=variant_src.read_bytes(): p.error('existing A7 variant differs; refusing to overwrite')
device=tree/'device/samsung/a7lte'; source_device=ROOT/'android/device/samsung/a7lte'; receipt=tree/'.a7lte-overlay.json'
no_symlinks(device); no_symlinks(receipt)
old=json.loads(receipt.read_text()) if receipt.is_file() else {}
for rel in old.get('device_files',{}): safe_rel(rel)
if device.exists() and any(device.iterdir()):
    current=hashes(device)
    if current!=hashes(source_device) and current!=old.get('device_files'): p.error('existing device tree has unmanaged edits; refusing overwrite')
if not a.check_only:
    for target,patch in patches:
        result=git(target,'apply',str(patch))
        if result.returncode: raise SystemExit(result.stderr)
    variant_dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(variant_src,variant_dest)
    for rel in old.get('device_files',{}):
        if rel not in hashes(source_device): (device/rel).unlink(missing_ok=True)
    shutil.copytree(source_device,device,dirs_exist_ok=True)
    receipt.write_text(json.dumps({'device_files':hashes(source_device),'kernel_variant_sha256':hashlib.sha256(variant_src.read_bytes()).hexdigest()},indent=2)+'\n')
print('PASS: overlay '+('preflight' if a.check_only else 'applied')+'; kernel and common pinned, local edits protected')
