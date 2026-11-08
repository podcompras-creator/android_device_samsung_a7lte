#!/usr/bin/env python3
"""Check diagnostic image inputs; require actual built native audit before ZIP."""
import argparse,hashlib,importlib.util,json
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''): h.update(data)
    return h.hexdigest()

def require(condition,message):
    # Keep validation active even if PYTHONOPTIMIZE is set by the build host.
    if not condition: raise AssertionError(message)

def check(tree,layout,require_native=False,native_report=None,product_out=None):
    r=json.loads(layout.read_text()); mk=tree/'device/samsung/a7lte/partition-sizes.mk'
    require(r['layout_format']==1 and r['layout_verified'] and r['model']=='SM-A700FD' and r['firmware']=='A700FDXXS1CSB1','layout not verified SM-A700FD CSB1')
    require(mk.is_file() and digest(mk)==r['makefile']['sha256'],'partition-sizes.mk missing/stale')
    vendor=tree/'vendor/samsung/a7lte'
    v=json.loads((vendor/'vendor-audit.json').read_text())
    require(v.get('model')=='SM-A700FD' and v.get('firmware')=='A700FDXXS1CSB1' and v.get('ready_for_diagnostic_build'),'vendor is not audited CSB1')
    inventory=json.loads((vendor/'stock-inventory.json').read_text())
    plan=json.loads((vendor/'vendor-review.json').read_text())
    require(plan['reviewed'] is True and inventory['firmware']==v['firmware'] and plan['firmware']==v['firmware'],'vendor plan/identity mismatch')
    if v.get('schema_version',1)>=2:
        require(digest(vendor/'vendor-review.json')==v['review_plan_sha256'],'vendor review changed after generation')
        require(digest(vendor/'stock-inventory.json')==v['inventory_sha256'],'stock inventory changed after generation')
        require(digest(ROOT/'scripts/native-contracts.json')==v['native_contract_sha256'],'source module contracts changed; regenerate vendor')
        expected={'Android.mk','a7lte-vendor.mk','BoardConfigVendor.mk'}
        require(set(v['generated_makefiles'])==expected,'generated makefile inventory incomplete')
        for name,sha in v['generated_makefiles'].items():
            path=vendor/name
            require(path.resolve().is_relative_to(vendor.resolve()) and digest(path)==sha,'generated vendor makefile changed: '+name)
    rows={x['source']:x for x in inventory['files']}
    require(len(plan['files'])==len(rows) and {x['source'] for x in plan['files']}==set(rows),'review plan changed')
    count=0
    for item in plan['files']:
        if item['action']=='skip':
            require(item.get('reason','').strip(),'unexplained skipped file')
            continue
        require(item['action'] in {'copy','module'},'unreviewed action')
        rel=PurePosixPath(item['source'])
        require(not rel.is_absolute() and '..' not in rel.parts,'unsafe vendor source path')
        path=vendor/'proprietary'/rel
        require(path.resolve().is_relative_to(vendor.resolve()),'vendor path escapes tree')
        require(digest(path)==rows[item['source']]['sha256'],'vendor file missing/changed: '+str(rel))
        count+=1
    require(count==v['selected_files']>0,'vendor selection changed')
    if require_native:
        require(v.get('schema_version',1)>=2,'ZIP requires vendor schema2 makefile/plan integrity; regenerate vendor')
        product_out=product_out or tree/'out/target/product/a7lte'
        native_report=native_report or product_out/'native-dependencies.json'
        spec=importlib.util.spec_from_file_location('native_audit',ROOT/'scripts/audit-native-dependencies.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.validate_report(product_out,native_report)
    return count

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tree',required=True,type=Path);p.add_argument('--layout',required=True,type=Path)
    p.add_argument('--require-native',action='store_true',help='mandatory for bacon/ZIP packaging')
    p.add_argument('--native-report',type=Path);p.add_argument('--product-out',type=Path);a=p.parse_args()
    try:count=check(a.tree.resolve(),a.layout,a.require_native,a.native_report,a.product_out)
    except (OSError,ValueError,KeyError,AssertionError) as e:p.exit(2,f'Input validation failed: {e}\n')
    print(f'PASS: layout and {count} selected stock hashes match; native packaging gate={a.require_native}; device behavior remains unverified')
if __name__=='__main__':main()
