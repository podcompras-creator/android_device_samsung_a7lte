#!/usr/bin/env python3
"""Inspect a legacy Samsung/QCDT Android image; no flashing or execution."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

TRAILER = b'SEANDROIDENFORCE'


def aligned(value, page):
    return (value + page - 1) // page * page


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(image, *, kernel=None, ramdisk=None, dt=None, allow_signature_tail=False):
    image = Path(image)
    if image.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('audit inspector limit: image larger than 128 MiB')
    data = image.read_bytes()
    if len(data) < 1632 or data[:8] != b'ANDROID!':
        raise ValueError('missing complete Android v0 / Samsung legacy header')
    values = struct.unpack_from('<10I', data, 8)
    ks, ka, rs, ra, ss, sa, ta, page, ds, os_raw = values
    if page not in (2048, 4096, 8192, 16384) or not ks or not rs:
        raise ValueError('invalid page size or empty required payload')
    if ds in (1, 2):
        raise ValueError('modern header version is not Samsung legacy --dt')
    offsets = dict(kernel=page)
    offsets['ramdisk'] = offsets['kernel'] + aligned(ks, page)
    offsets['second'] = offsets['ramdisk'] + aligned(rs, page)
    offsets['dt'] = offsets['second'] + aligned(ss, page)
    end = offsets['dt'] + aligned(ds, page)
    if end > len(data):
        raise ValueError('truncated image payload')
    sizes = dict(kernel=ks, ramdisk=rs, second=ss, dt=ds)
    payloads = {name: data[offsets[name]:offsets[name]+size] for name, size in sizes.items()}
    sha1 = hashlib.sha1()
    for name in ('kernel', 'ramdisk', 'second', 'dt'):
        sha1.update(payloads[name])
        sha1.update(struct.pack('<I', sizes[name]))
    if data[576:608] != sha1.digest().ljust(32, b'\0'):
        raise ValueError('header SHA1 identifier does not match payloads/sizes')
    tail = data[end:]
    opaque_signature = tail[len(TRAILER):] if tail.startswith(TRAILER) else b''
    if tail != TRAILER and not (allow_signature_tail and tail.startswith(TRAILER) and len(opaque_signature) == 256):
        raise ValueError('missing/extraneous Samsung trailer bytes after aligned payload')
    qcdt = None
    if ds:
        if ds < 12:
            raise ValueError('truncated QCDT header')
        magic, version, count = struct.unpack_from('<4sII', payloads['dt'])
        if magic != b'QCDT' or version not in (2, 3) or not 0 < count <= 1024:
            raise ValueError('this audit expects a nonempty QCDT v2/v3 image')
        entry_size = 24 if version == 2 else 40
        if 12 + entry_size * count + 4 > ds:
            raise ValueError('truncated QCDT table')
        table = []
        for i in range(count):
            fields = struct.unpack_from('<' + ('6I' if version == 2 else '10I'), payloads['dt'], 12+entry_size*i)
            soc, platform, subtype, revision = fields[:4]
            pmic = list(fields[4:8]) if version == 3 else None
            off, size = fields[-2:]
            if off % page or size % page or off+size > ds or off < 12+entry_size*count+4:
                raise ValueError('QCDT entry bounds/alignment invalid')
            if payloads['dt'][off:off+4] != bytes.fromhex('d00dfeed'):
                raise ValueError('QCDT entry missing flattened DT magic')
            fdt_size = struct.unpack_from('>I', payloads['dt'], off+4)[0]
            if fdt_size > size or fdt_size < 40:
                raise ValueError('FDT size exceeds QCDT entry')
            table.append(dict(soc=soc, platform=platform, subtype=subtype, revision=revision, pmic=pmic, offset=off, size=size))
        qcdt = dict(version=version, entries=count, unique_dtbs=len({x['offset'] for x in table}), table=table)
    matches = {}
    for name, reference in dict(kernel=kernel, ramdisk=ramdisk, dt=dt).items():
        if reference is not None:
            if payloads[name] != Path(reference).read_bytes():
                raise ValueError(name + ' differs from preserved/reference input')
            matches[name] = True
    packed_version = os_raw >> 11
    patch = os_raw & 2047
    month = patch & 15
    if month > 12:
        raise ValueError('invalid patchlevel month')
    version = '.'.join(str((packed_version >> shift) & 127) for shift in (14, 7, 0))
    report = dict(result='PASS', image=str(image.resolve()), image_sha256=digest(data), image_bytes=len(data),
                  format=('Samsung legacy DT/v0' if ds else 'Android v0'), header_sha1=sha1.hexdigest(),
                  page_size=page, kernel_address=ka, ramdisk_address=ra, second_address=sa, tags_address=ta,
                  os_version=version, os_patch_level=(f'{2000+(patch >> 4):04d}-{month:02d}' if month else None),
                  board=data[48:64].split(b'\0',1)[0].decode('ascii'),
                  cmdline=(data[64:576]+data[608:1632]).split(b'\0',1)[0].decode('ascii'),
                  payloads={n:dict(offset=offsets[n], bytes=sizes[n], sha256=digest(v)) for n,v in payloads.items()},
                  trailer=dict(offset=end, bytes=len(tail), value=TRAILER.decode(), opaque_signature_bytes=len(opaque_signature), opaque_signature_sha256=digest(opaque_signature), samsung_signature_verified=False),
                  qcdt=qcdt, reference_matches=matches,
                  stock_compatibility_verified=False, device_boot_tested=False)
    return report, payloads


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('--kernel',type=Path)
    p.add_argument('--ramdisk',type=Path)
    p.add_argument('--dt',type=Path)
    p.add_argument('--allow-signature-tail',action='store_true',help='record exactly 256 opaque bytes after Samsung marker; does not authenticate the signature')
    p.add_argument('--extract',type=Path,help='new directory for fixed-name roundtrip payloads')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        report,payloads=inspect(a.image,kernel=a.kernel,ramdisk=a.ramdisk,dt=a.dt,allow_signature_tail=a.allow_signature_tail)
        if a.extract:
            a.extract.mkdir(parents=True,exist_ok=False)
            for name,value in payloads.items():
                (a.extract/(name+'.roundtrip.bin')).write_bytes(value)
        text=json.dumps(report,indent=2)+'\n'
        if a.output:
            if a.output.resolve() in {x.resolve() for x in (a.image,a.kernel,a.ramdisk,a.dt) if x is not None}:
                raise ValueError('output cannot overwrite input image')
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(text)
        print(text,end='')
    except (OSError,ValueError,struct.error) as e:
        p.exit(2,'boot inspection failed: '+str(e)+'\n')


if __name__=='__main__':
    main()
