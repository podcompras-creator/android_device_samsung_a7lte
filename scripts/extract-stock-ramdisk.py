#!/usr/bin/env python3
"""Extract audit text from a boot ramdisk without creating links/devices or init.

This is evidence for comparing fstab/init, not an Android ramdisk generator.
"""
import argparse,gzip,hashlib,importlib.util,io,json,stat
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('boot_inspection',ROOT/'scripts/inspect-samsung-boot.py')
boot=importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)


def parse_newc(data):
    offset=0; names=set(); entries=[]
    while True:
        if len(entries)>20000 or offset+110>len(data): raise ValueError('CPIO entry limit or truncated header')
        raw=data[offset:offset+110]; magic=raw[:6]
        if magic not in (b'070701',b'070702'): raise ValueError('unsupported ramdisk CPIO format')
        f=[int(raw[6+i*8:14+i*8],16) for i in range(13)]
        ino,mode,uid,gid,nlink,mtime,size,devmaj,devmin,rdevmaj,rdevmin,namesize,checksum=f
        if not 0<namesize<=4096 or offset+110+namesize>len(data): raise ValueError('unsafe or truncated CPIO filename')
        rawname=data[offset+110:offset+110+namesize]
        if not rawname.endswith(b'\0') or b'\0' in rawname[:-1]: raise ValueError('bad CPIO name terminator')
        name=rawname[:-1].decode('utf-8')
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name: raise ValueError('unsafe CPIO path')
        name=str(path)
        start=(offset+110+namesize+3)//4*4
        end=start+size
        if end>len(data): raise ValueError('truncated CPIO file')
        value=data[start:end]
        if magic==b'070702' and sum(value)&0xffffffff!=checksum: raise ValueError('CPIO CRC mismatch')
        offset=(end+3)//4*4
        if name=='TRAILER!!!':
            if size: raise ValueError('bad CPIO trailer size')
            break
        if name in names: raise ValueError('duplicate CPIO name: '+name)
        names.add(name)
        entries.append((dict(path=name,mode=oct(mode),uid=uid,gid=gid,bytes=size,sha256=hashlib.sha256(value).hexdigest(),
                             type=('file' if stat.S_ISREG(mode) else 'directory' if stat.S_ISDIR(mode) else 'symlink' if stat.S_ISLNK(mode) else 'special')),
                        value))
    return entries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--allow-signature-tail',action='store_true')
    a=p.parse_args()
    try:
        if a.output.exists(): raise ValueError('output exists; use a new directory')
        report,payloads=boot.inspect(a.image,allow_signature_tail=a.allow_signature_tail)
        with gzip.GzipFile(fileobj=io.BytesIO(payloads['ramdisk'])) as gz: data=gz.read(64*1024*1024+1)
        if len(data)>64*1024*1024: raise ValueError('ramdisk exceeds 64MiB inspection limit')
        entries=parse_newc(data)
        a.output.mkdir(parents=True)
        selected=[];inventory=[]
        for entry,value in entries:
            inventory.append(entry)
            name=entry['path'];base=PurePosixPath(name).name
            useful=(base=='default.prop' or base in ('file_contexts','property_contexts','seapp_contexts') or
                    ((base.startswith('init') or base.startswith('fstab') or base.startswith('ueventd')) and (base.endswith('.rc') or base.endswith('.sh') or base.startswith('fstab'))))
            if entry['type']=='file' and useful:
                dest=a.output/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value);selected.append(name)
        result=dict(result='PASS',source_image=str(a.image.resolve()),source_image_sha256=report['image_sha256'],
                    ramdisk_sha256=report['payloads']['ramdisk']['sha256'],cpio_entries=len(entries),
                    selected_text_files=selected,created_links_or_devices=False,android_init_copied=False,
                    scope='offline text evidence only; no stock ramdisk installed in Lineage product',inventory=inventory)
        (a.output/'ramdisk-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='inventory'},indent=2))
    except (OSError,ValueError,EOFError) as e: p.exit(2,'stock ramdisk inspection failed: '+str(e)+'\n')

if __name__=='__main__': main()
