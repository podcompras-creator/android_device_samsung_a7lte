#!/usr/bin/env python3
"""Audit actual built ARM32 ELFs before a7lte ZIP packaging; never execute them.

Checks essential path contracts, ELF DT_NEEDED closure and strong dynamic symbol
providers, including explicitly configured linker-injected shims. This is a
conservative static gate, not an emulator of Android linker namespaces/dlopen.
"""
import argparse, hashlib, importlib.util, json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
CONTRACTS=ROOT/'scripts/native-contracts.json'
spec=importlib.util.spec_from_file_location('extract_stock',ROOT/'scripts/extract-stock.py')
extractor=importlib.util.module_from_spec(spec);spec.loader.exec_module(extractor)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def canonical(symbol):
    return symbol.replace('@@','@')

def symbol_matches(required, exports):
    if '@' in required: return canonical(required) in {canonical(s) for s in exports}
    return required in exports or any(s.startswith(required+'@@') for s in exports)

def audit(product_out, contracts_file=CONTRACTS):
    product_out=product_out.resolve(strict=True)
    contract=json.loads(contracts_file.read_text()); records={}; invalid=[]
    for base in ('system/lib','system/vendor/lib','vendor/lib','system/bin','system/vendor/bin','vendor/bin'):
        directory=product_out/base
        if not directory.exists():continue
        for path in sorted(directory.rglob('*')):
            if not path.is_file():continue
            resolved=path.resolve()
            if not resolved.is_relative_to(product_out):raise ValueError(f'ELF input escapes product output: {path}')
            with path.open('rb') as f: magic=f.read(4)
            if magic!=b'\x7fELF':continue
            rel=str(path.relative_to(product_out)); info=extractor.elf_info(path)
            records[rel]={'path':rel,'sha256':digest(path),'elf':info}
            if not info['expected_arm32'] or not info['dynamic_audit_ok']:invalid.append(rel)
    missing_essential=[p for p in contract['essential_files'] if p not in records]
    missing_groups=[g for g in contract.get('essential_alternative_groups',[]) if not any(p in records for p in g)]
    providers={}
    for path,row in records.items():
        elf=row['elf']
        if not elf['expected_arm32']:continue
        name=elf['soname'] or Path(path).name
        providers.setdefault(name,[]).append(path)
    needed_missing=[];ambiguous=[];unresolved=[];injected_missing=[]
    graphs={};
    for path,row in records.items():
        names=row['elf']['needed']+contract.get('injected_shims',{}).get(path,[])
        deps=[]
        for name in names:
            candidates=providers.get(name,[])
            # If two namespaces provide the same SONAME, do not guess which ELF
            # Android will load. Hash-equal symlink duplicates are harmless here.
            distinct={records[p]['sha256'] for p in candidates}
            if not candidates:
                issue={'consumer':path,'needed':name}
                (injected_missing if name in contract.get('injected_shims',{}).get(path,[]) else needed_missing).append(issue)
            elif len(distinct)>1:
                ambiguous.append({'consumer':path,'needed':name,'providers':candidates})
            else:deps.append(candidates[0])
        graphs[path]=deps
    for path,row in records.items():
        closure=set();todo=[path]
        while todo:
            p=todo.pop()
            if p in closure:continue
            closure.add(p);todo.extend(graphs.get(p,[]))
        exports=set()
        for provider in closure:
            exports.update(records[provider]['elf']['defined_dynamic_symbols'])
        weak=set(row['elf'].get('weak_undefined_dynamic_symbols',[]))
        for symbol in row['elf']['undefined_dynamic_symbols']:
            if symbol not in weak and not symbol_matches(symbol,exports):
                unresolved.append({'consumer':path,'symbol':symbol})
    ready=bool(records) and not any([missing_essential,missing_groups,invalid,needed_missing,ambiguous,unresolved,injected_missing])
    return {'schema_version':1,'kind':'built-native-dependency-audit','model':contract['model'],'firmware':contract['firmware'],
            'product_out':str(product_out),'contract_sha256':digest(contracts_file),
            'essential_paths_checked':contract['essential_files'], 'missing_essential_files':missing_essential,
            'essential_alternative_groups':contract.get('essential_alternative_groups',[]),'missing_essential_groups':missing_groups,
            'invalid_elfs':invalid,'missing_needed':needed_missing,'ambiguous_providers':ambiguous,
            'missing_injected_shims':injected_missing,'unresolved_strong_symbols':unresolved,
            'elf_count':len(records),'files':[{'path':p,'sha256':r['sha256']} for p,r in records.items()],
            'ready_for_image_packaging':ready,'linker_namespaces_verified':False,'dlopen_behavior_verified':False,
            'device_tested':False,'release_ready':False,'limitations':contract.get('limitations','')}

def validate_report(product_out, report_path, contracts_file=CONTRACTS):
    product_out=product_out.resolve(strict=True);r=json.loads(report_path.read_text())
    if r.get('schema_version')!=1 or r.get('kind')!='built-native-dependency-audit' or r.get('model')!='SM-A700FD' or r.get('firmware')!='A700FDXXS1CSB1':raise ValueError('native dependency report identity/schema invalid')
    if not r.get('ready_for_image_packaging'):raise ValueError('native dependencies unresolved; ZIP packaging blocked')
    if r.get('contract_sha256')!=digest(contracts_file):raise ValueError('native contract changed; rerun audit')
    files=r.get('files',[])
    if not files or len(files)!=r.get('elf_count'):raise ValueError('native audit inventory is empty/inconsistent')
    seen=set()
    for item in files:
        rel=extractor.safe_rel(item['path'])
        if rel in seen:raise ValueError('duplicate native report path')
        seen.add(rel);path=extractor.inside(product_out/rel,product_out)
        if digest(path)!=item['sha256']:raise ValueError(f'native report stale: {rel}')
    for p in json.loads(contracts_file.read_text())['essential_files']:
        if p not in seen:raise ValueError(f'native report omitted essential path: {p}')
    for group in json.loads(contracts_file.read_text()).get('essential_alternative_groups',[]):
        if not any(p in seen for p in group):raise ValueError('native report omitted essential alternative group')
    # Detect added/changed ELF providers as well as changes to previously audited
    # files: a new SONAME duplicate can invalidate a formerly clean closure.
    fresh=audit(product_out,contracts_file)
    if not fresh['ready_for_image_packaging'] or fresh['files']!=files:raise ValueError('native output changed; rerun audit')
    return len(files)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--product-out',required=True,type=Path);p.add_argument('--output',type=Path);p.add_argument('--validate',type=Path);a=p.parse_args()
    try:
        if a.validate:
            count=validate_report(a.product_out,a.validate);print(f'PASS: {count} built ELF hashes and dependency closures still match');return 0
        r=audit(a.product_out);out=a.output or a.product_out/'native-dependencies.json';out.write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r[k] for k in ('elf_count','ready_for_image_packaging')}));return 0 if r['ready_for_image_packaging'] else 1
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:p.exit(2,f'Native audit failed: {e}\n')

if __name__=='__main__':sys.exit(main())
