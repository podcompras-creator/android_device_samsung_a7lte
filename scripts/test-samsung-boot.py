#!/usr/bin/env python3
"""Execute Samsung's pinned make recipe with a marker-only NONFLASHABLE ramdisk.

This tests packaging and roundtrip integrity. It does not build Android, execute
kernel code, supply Android init, sign a flash image, or verify stock geometry.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import shlex
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def newc(name,content,ino,mode):
    name=name.encode()+b'\0'
    fields=(ino,mode,0,0,1,0,len(content),0,0,0,0,len(name),0)
    value=b'070701'+b''.join(('%08x'%x).encode() for x in fields)+name
    value+=bytes((-len(value))%4)
    value+=content
    value+=bytes((-len(content))%4)
    return value


def run(argv,log,**kwargs):
    result=subprocess.run(argv,text=True,capture_output=True,**kwargs)
    log.write('$ '+shlex.join(str(x) for x in argv)+'\n'+result.stdout+result.stderr)
    log.flush()
    if result.returncode:
        raise RuntimeError(f'command failed ({result.returncode}): {argv[0]}')
    return result


def make_harness(output,ramdisk,dt_image):
    tools=ROOT/'host/boot-tools'
    boot=output/'a7lte-BOOT-PACKAGING-NONFLASHABLE.img'
    recovery=output/'a7lte-RECOVERY-PACKAGING-NONFLASHABLE.img'
    # This arbitrary test-only upper bound is NOT a Samsung partition size.
    # The real image-build script still requires a stock PIT layout report.
    args=['--kernel',str(ROOT/'artifacts/zImage'),'--ramdisk',str(ramdisk),
          '--dt',str(dt_image),'--base','0x80000000',
          '--kernel_offset','0x00008000','--ramdisk_offset','0x02000000',
          '--tags_offset','0x01e00000','--pagesize','2048',
          '--board','NONFLASHABLE','--cmdline','a7lte.packaging_audit=NONFLASHABLE']
    lines=[f'MKBOOTIMG := {tools}/mkbootimg',
           f'INSTALLED_BOOTIMAGE_TARGET := {boot}',
           f'INSTALLED_RECOVERYIMAGE_TARGET := {recovery}',
           f'RECOVERYIMAGE_ID_FILE := {output}/recovery.header-id.txt',
           f'INTERNAL_BOOTIMAGE_FILES := {ROOT}/artifacts/zImage {dt_image} {ramdisk}',
           f'recovery_ramdisk := {ramdisk}', f'recovery_kernel := {ROOT}/artifacts/zImage',
           'INTERNAL_BOOTIMAGE_ARGS := '+shlex.join(args),
           'INTERNAL_RECOVERYIMAGE_ARGS := '+shlex.join(args),
           'INTERNAL_MKBOOTIMG_VERSION_ARGS := --header_version 0 --os_version 9.0.0 --os_patch_level 2019-02-01',
           'BOARD_KERNEL_SEPARATED_DT := true', 'BOARD_KERNEL_PREBUILT_DT := true',
           'BOARD_BOOTIMAGE_PARTITION_SIZE := 33554432',
           'BOARD_RECOVERYIMAGE_PARTITION_SIZE := 33554432',
           '# Synthetic 32 MiB ceiling above; not obtained from a PIT.',
           'hide :=', 'pretty = @echo $(1)',
           'assert-max-image-size = test "$$(wc -c < $(1))" -le "$(2)"',
           f'include {ROOT}/tooling/boot-sources/samsung-mkbootimg.mk',
           '.PHONY: audit', 'audit: $(INSTALLED_BOOTIMAGE_TARGET) $(INSTALLED_RECOVERYIMAGE_TARGET)']
    (output/'SamsungBootAudit.mk').write_text('\n'.join(lines)+'\n')
    return boot,recovery


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/boot-audit',help='new directory; refuses to overwrite an existing audit')
    p.add_argument('--dt-image',type=Path,default=ROOT/'artifacts/dt.img',help='preserved v2 or explicitly generated v3 native candidate')
    p.add_argument('--dtc',type=Path,default=ROOT/'out/kernel/scripts/dtc/dtc',help='existing dtc executable or installed official dtc; kernel is not rebuilt')
    a=p.parse_args()
    output=a.output.resolve()
    a.dt_image=a.dt_image.resolve()
    magic,dt_version,dt_count=struct.unpack('<4sII',a.dt_image.read_bytes()[:12])
    if magic!=b'QCDT' or dt_version not in (2,3): p.error('DT input must be QCDT v2/v3')
    if output.exists(): p.error('output already exists; preserve it and select a new --output')
    if not a.dtc.is_file(): p.error('dtc absent; specify --dtc /path/to/dtc (device-tree-compiler), without rebuilding the preserved kernel')
    output.mkdir(parents=True)
    logs=ROOT/'logs/phase3-boot'; logs.mkdir(parents=True,exist_ok=True)
    originals={name:sha(ROOT/'artifacts'/name) for name in ('zImage','dt.img')}
    with (logs/'packaging-run.log').open('w') as log:
        run([ROOT/'tooling/build-boot-tools.sh'],log)
        run([ROOT/'host/boot-tools/dtbToolLineage','-'+str(dt_version),'-s','2048','-p',str(a.dtc.resolve().parent)+'/',
             '-o',output/'dt.REPACKED-NONFLASHABLE.img',str(ROOT/'artifacts/dtbs')+'/'],log)
        if not (output/'dt.REPACKED-NONFLASHABLE.img').is_file():
            raise RuntimeError('dtbTool reported success without producing a DT image')
        if sha(output/'dt.REPACKED-NONFLASHABLE.img') != sha(a.dt_image):
            raise RuntimeError('repacked QCDT differs from selected DT input')
        # Externally compile/execute the real dtbTool, then retain original DT in
        # the boot test so byte identity and existing provenance remain intact.
        marker=b'NONFLASHABLE packaging fixture. No Android init, no services, no stock ramdisk.\n'
        cpio=newc('README.NONFLASHABLE',marker,1,0o100644)+newc('TRAILER!!!',b'',0,0)
        cpio+=bytes((-len(cpio))%512)
        ramdisk=output/'ramdisk.MARKER-ONLY-NONFLASHABLE.cpio.gz'
        with ramdisk.open('wb') as f:
            with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as z: z.write(cpio)
        assert gzip.decompress(ramdisk.read_bytes())==cpio
        assert b'/init\0' not in cpio and b'init\0' not in cpio
        (output/'README.NONFLASHABLE.txt').write_text('Packaging audit only. Synthetic marker-only ramdisk contains no /init.\nDo not flash. No stock compatibility, partition map or device behavior validated.\n')
        boot,recovery=make_harness(output,ramdisk,a.dt_image)
        run(['make','--no-print-directory','-f',output/'SamsungBootAudit.mk','audit'],log)
        inspector=module('boot_inspect',ROOT/'scripts/inspect-samsung-boot.py')
        validator=module('stock_layout',ROOT/'scripts/verify-stock-layout.py')
        reports={}
        for name,image in (('boot',boot),('recovery',recovery)):
            report,payloads=inspector.inspect(image,kernel=ROOT/'artifacts/zImage',ramdisk=ramdisk,dt=a.dt_image)
            # Exercise the updated legacy layout parser on a real mkbootimg
            # result with a nonzero OS-version word. No synthetic PIT supplied.
            geometry=validator.parse_boot(image,32*1024*1024)
            assert geometry['os_version']=='9.0.0' and geometry['os_patch_level']=='2019-02'
            assert report['qcdt']['entries']==15 and report['qcdt']['unique_dtbs']==5
            assert report['page_size']==2048
            reports[name]=report
            (logs/(name+'-roundtrip.json')).write_text(json.dumps(report,indent=2)+'\n')
        expected_id='0x'+reports['recovery']['header_sha1']+'0'*24
        assert (output/'recovery.header-id.txt').read_text().strip()==expected_id
        checks=[]
        with tempfile.TemporaryDirectory(prefix='a7lte-boot-negative-') as temp:
            mutated=Path(temp)/'mutation.img'
            raw=bytearray(boot.read_bytes())
            raw[2048]^=1; mutated.write_bytes(raw)
            try: inspector.inspect(mutated)
            except ValueError as e: checks.append({'check':'kernel corruption rejected','detail':str(e)})
            else: raise AssertionError('corrupt payload was accepted')
            mutated.write_bytes(boot.read_bytes()[:-1])
            try: inspector.inspect(mutated)
            except ValueError as e: checks.append({'check':'truncated trailer rejected','detail':str(e)})
            else: raise AssertionError('corrupt trailer was accepted')
            raw=bytearray(boot.read_bytes()); struct.pack_into('<I',raw,40,1); mutated.write_bytes(raw)
            try: validator.parse_boot(mutated,32*1024*1024)
            except ValueError as e: checks.append({'check':'modern header-v1 not mistaken for legacy DT','detail':str(e)})
            else: raise AssertionError('modern v1 was accepted as legacy')
        assert originals=={name:sha(ROOT/'artifacts'/name) for name in originals}
        results={'result':'PASS','scope':'native boot-tool compilation and Samsung recipe packaging/roundtrip with synthetic marker-only ramdisk',
                 'nonflashable':True,'kernel_recompiled':False,'original_artifact_hashes_unchanged':originals,
                 'stock_layout_verified':False,'stock_ramdisk_used':False,'device_tested':False,
                 'selected_dt':{'path':str(a.dt_image),'version':dt_version,'sha256':sha(a.dt_image)},
                 'dt_repack_equals_selected_input':sha(output/'dt.REPACKED-NONFLASHABLE.img')==sha(a.dt_image),
                 'dt_repack_sha256':sha(output/'dt.REPACKED-NONFLASHABLE.img'),
                 'dt_repack_equals_original':sha(output/'dt.REPACKED-NONFLASHABLE.img')==originals['dt.img'],
                 'new_checks':checks,'outputs':{name:{'path':r['image'],'bytes':r['image_bytes'],'sha256':r['image_sha256']} for name,r in reports.items()}}
        (logs/'boot-audit-result.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
