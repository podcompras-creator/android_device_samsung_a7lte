#!/usr/bin/env python3
"""Fetch a bounded, pinned Samsung A7 2016 ELF sample for reference ABI study.
These are community files predating CSB1, never extracted/installed as CSB1.
"""
import argparse, hashlib, importlib.util, json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REV='0f039d3c6c76b8fc9ece945f54a09056a09d9dcf'
REPO='MSM8939-Samsung/android_vendor_samsung_a7lte'
PATHS=['proprietary/lib/hw/camera.msm8916.so','proprietary/lib/hw/sensors.msm8916.so',
'proprietary/lib/hw/gps.default.so','proprietary/lib/libsec-ril.so','proprietary/lib/libsec-ril-dsds.so',
'proprietary/vendor/lib/libizat_core.so','proprietary/lib/libmmjpeg_interface.so',
'proprietary/vendor/lib/libqomx_jpegenc.so','proprietary/vendor/lib/libQSEEComAPI.so',
'proprietary/lib/libloc_api_v02.so','proprietary/lib/libloc_core.so','proprietary/lib/libloc_eng.so',
'proprietary/lib/libgps.utils.so','proprietary/vendor/lib/libtime_genoff.so','proprietary/lib/libril.so']
spec=importlib.util.spec_from_file_location('extract_stock',ROOT/'scripts/extract-stock.py')
extractor=importlib.util.module_from_spec(spec); spec.loader.exec_module(extractor)

def get(url,maximum):
    with urllib.request.urlopen(url,timeout=40) as r:
        data=r.read(maximum+1)
    if len(data)>maximum: raise ValueError('download exceeds bounded audit budget')
    return data

def audit(output,fetch=False):
    output.mkdir(parents=True,exist_ok=True)
    treefile=output/'tree.json'
    if fetch and not treefile.exists(): treefile.write_bytes(get(f'https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1',4*1024*1024))
    tree=json.loads(treefile.read_text()); files={x['path']:x for x in tree['tree'] if x['type']=='blob'}
    selected=[files[x] for x in PATHS]
    if sum(x['size'] for x in selected)>=100*1024*1024: raise ValueError('audit sample exceeds100MiB budget')
    rows=[]
    for entry in selected:
        p=output/entry['path']; p.parent.mkdir(parents=True,exist_ok=True)
        url=f'https://raw.githubusercontent.com/{REPO}/{REV}/{entry["path"]}'
        if fetch and not p.exists(): p.write_bytes(get(url,entry['size']))
        data=p.read_bytes()
        blob=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        if blob!=entry['sha'] or len(data)!=entry['size']: raise ValueError(f'Git blob mismatch {p}')
        rows.append({'path':entry['path'],'origin_url':url,'git_blob_sha1':blob,'sha256':hashlib.sha256(data).hexdigest(),
                     'bytes':len(data),'elf':extractor.elf_info(p)})
    report={'schema_version':1,'kind':'historical-a7-reference-ABI-only','repository':f'https://github.com/{REPO}',
            'revision':REV,'firmware_version':'unknown; 2016 community Marshmallow files; NOT CSB1',
            'csb1_verified':False,'installed_into_vendor':False,'sample_bytes':sum(x['bytes'] for x in rows),'files':rows}
    (output/'elf-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    write_findings(output, report)
    return report

def write_findings(output,report):
    files=report['files'];by_path={r['path']:r for r in files}
    camera_symbol='_ZN7android16CameraParameters26PIXEL_FORMAT_YUV420SP_NV21E'
    gps_symbols=['sec_gps_conf','loc_read_sec_gps_conf','loc_secgps_default_parameters']
    gps_text='\n'.join(p.read_text(errors='replace') for p in (ROOT/'sources/common/gps').rglob('*') if p.is_file())
    source=ROOT/'sources/common/libshims/camera_shim.c'
    sap=sorted(s for s in by_path['proprietary/lib/libsec-ril-dsds.so']['elf']['undefined_dynamic_symbols'] if s.startswith('RIL_SIM_SAP_'))
    symbol_rows=[]
    for symbol in gps_symbols+sap+[camera_symbol]:
        symbol_rows.append({'symbol':symbol,'sample_consumers':[r['path'] for r in files if symbol in r['elf']['undefined_dynamic_symbols']],
                            'sample_providers':[r['path'] for r in files if symbol in r['elf']['defined_dynamic_symbols']]})
    findings={'kind':'observed-historical-ABI-findings','reference_revision':REV,'csb1_verified':False,
              'sample_files':len(files),'sample_bytes':report['sample_bytes'],
              'camera_shim_import_present':camera_symbol in by_path['proprietary/lib/hw/camera.msm8916.so']['elf']['undefined_dynamic_symbols'],
              'camera_shim_source_contains_exact_symbol':camera_symbol in source.read_text(),
              'camera_shim_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'gps_identifiers_not_found_in_common_source_text':[x for x in gps_symbols if x not in gps_text],
              'symbol_observations':symbol_rows,
              'keymaster_keystore_elf_in_upstream_tree':[x['path'] for x in json.loads((output/'tree.json').read_text())['tree'] if x['path'].endswith('.so') and any(z in x['path'].lower() for z in ['keymaster','keystore'])],
              'actions':['Keep camera/sensors stock HALs renamed under vendor suffix; wrappers own main HAL module names.',
                         'Do not install historical rild/libril/libloc_eng/libloc_core/libgps.utils over current source modules.',
                         'Port and verify Samsung GPS extensions required by proprietary libloc_api_v02 or obtain exact CSB1 ABI evidence before enabling GPS stack.',
                         'Resolve RIL SAP field and protobuf symbols against actual built Pie libs; filenames alone do not prove ABI.',
                         'Run actual built-native dependency audit after native modules build; sample is incomplete and never a packaging readiness report.']}
    (output/'findings.json').write_text(json.dumps(findings,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,default=ROOT/'verification/historical-a7');p.add_argument('--fetch',action='store_true');a=p.parse_args()
    r=audit(a.output,a.fetch);print(json.dumps({'files':len(r['files']),'bytes':r['sample_bytes'],'csb1_verified':False}))
