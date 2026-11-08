#!/usr/bin/env python3
"""Prepare genuine-CSB1 vendor candidates for the explicitly forced CI build.

Identity and per-file hashes are checked. Source-owned modules and common
firmware symlinks are not replaced. --allow-missing-candidates records every
unresolved candidate while allowing diagnostic compilation; it does not certify
ABI, a usable ZIP, signatures, CSC or hardware operation.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

extractor = load('extract-stock')
generator = load('generate-vendor')
ADDITIONAL_SOURCE_MODULES = {
    'lib/libtinyalsa.so': 'external/tinyalsa source module libtinyalsa owns this platform library',
    'lib/libaudioroute.so': 'system/media/audio_route source module libaudioroute owns this platform library',
    'lib/libreference-ril.so': 'hardware/ril/reference-ril source module libreference-ril owns this platform library',
    'lib/libsecril-client.so': 'hardware/samsung@871d3f4777603ff6c33a021fc38c9b2265c54f83/ril/libsecril-client source module is included for BOARD_VENDOR=samsung',
}
FIRMWARE_SYMLINK_DESTINATIONS = {
    f'vendor/firmware/keymaster/keymaster.{ext}':
    f'device/samsung/msm8916-common/Android.mk generates this link to /firmware/image/keymaste.{ext}; retain existing firmware partition'
    for ext in ('b00','b01','b02','b03','mdt')
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''): h.update(data)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def inspect_source(system, source, destination):
    entry = {'source':source, 'destination':destination}
    path = system/source
    links = []
    current = system
    for part in PurePosixPath(source).parts:
        current = current/part
        if current.is_symlink():
            links.append({'path':str(current.relative_to(system)), 'target':os.readlink(current)})
            try: link_resolved=current.resolve(strict=False)
            except (OSError, RuntimeError) as error:
                return dict(entry, status='unresolved_symlink', source_links=links, reason=str(error))
            if not link_resolved.is_relative_to(system):
                return dict(entry, status='unresolved_external_symlink', source_links=links, reason='source link leaves verified SYSTEM; not followed')
    if links: entry['source_links'] = links
    try: resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        return dict(entry, status='unresolved_symlink', reason=str(error))
    if not resolved.is_relative_to(system):
        return dict(entry, status='unresolved_external_symlink', reason='source link leaves verified SYSTEM; not followed')
    if not resolved.exists(): return dict(entry, status='missing', reason='not present in verified CSB1 SYSTEM')
    if not resolved.is_file(): return dict(entry, status='non_regular_source', reason='candidate is not a regular file')
    return dict(entry, status='available', resolved_source=str(resolved))


def materialize(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    try: os.link(source, destination)
    except OSError: shutil.copyfile(source, destination)


def prepare(system, tree, staging, allow_missing=False, file_list=None):
    system = system.resolve(strict=True)
    # Read and validate identity before touching the output or following candidate
    # links. Stock files are never executed. Optional CSC links are probed below.
    properties, prop_hash = extractor.properties(system)
    staging = staging.absolute()
    if staging.is_symlink(): raise ValueError('staging must not be a symlink')
    staging = staging.resolve()
    tree = tree.absolute().resolve()
    if staging.is_relative_to(system) or system.is_relative_to(staging): raise ValueError('SYSTEM/staging must not overlap')
    if staging.exists() and any(staging.iterdir()): raise ValueError('staging must be empty; prior evidence is preserved')
    vendor = tree/'vendor/samsung/a7lte'
    if not vendor.resolve().is_relative_to(tree): raise ValueError('vendor output escapes requested tree')
    if vendor.is_symlink() or (vendor.exists() and any(vendor.iterdir())): raise ValueError('vendor output must be empty; prior vendor is preserved')
    if vendor.resolve().is_relative_to(system) or system.is_relative_to(vendor.resolve()): raise ValueError('vendor output must not overlap SYSTEM')
    if vendor.resolve().is_relative_to(staging) or staging.is_relative_to(vendor.resolve()): raise ValueError('vendor/staging must not overlap')
    rows = extractor.read_list(file_list or extractor.DEFAULT_LIST)
    contracts_file = ROOT/'scripts/native-contracts.json'
    contracts = json.loads(contracts_file.read_text())
    source_owned = dict(contracts['source_owned_stock_sources_to_skip'])
    source_owned.update(ADDITIONAL_SOURCE_MODULES)
    probes = [inspect_source(system,s,d) for s,d in rows]
    staging.mkdir(parents=True,exist_ok=True)
    write_json(staging/'source-probe.json', probes)
    provenance_file = system.parent/'fetch-result.json'
    provenance = {'path':str(provenance_file), 'present':provenance_file.is_file(), 'verification_level':'build-properties-only', 'firmware_signature_verified':False}
    if provenance_file.is_file():
        # Keep source evidence intact; never reinterpret a failed transfer as
        # valid merely because a leftover SYSTEM directory exists.
        raw = json.loads(provenance_file.read_text())
        if raw.get('success') is not True: raise ValueError('firmware fetch-result reports failure; refusing partial SYSTEM')
        ap=raw.get('ap_archive',{});identity=raw.get('system_identity',{})
        if ap.get('zip_entry_crc_verified') is not True or ap.get('zip_entry_fully_consumed') is not True:
            raise ValueError('fetch-result does not prove the complete AP ZIP entry CRC')
        if identity.get('model')!=extractor.MODEL or identity.get('build_prop_sha256')!=prop_hash:
            raise ValueError('SYSTEM build.prop changed since the verified acquisition')
        provenance.update(sha256=digest(provenance_file), evidence=raw, verification_level='successful-full-AP-acquisition-report')
        shutil.copyfile(provenance_file,staging/'firmware-fetch-result.json')
    available = [r for r in probes if r['status']=='available']
    if not available: raise ValueError('no confined stock candidates are available; cannot create vendor from nothing')
    # The view contains only verified regular candidate bytes and build.prop.
    # Hardlinks/copies avoid following Android absolute symlinks into the host.
    # Unknown external CSC/firmware links are reported, never dereferenced.
    view = staging/'safe-system-view'; view.mkdir()
    materialize(extractor.inside(system/'build.prop',system),view/'build.prop')
    for row in available: materialize(Path(row['resolved_source']),view/row['source'])
    csc_probe = inspect_source(system,'csc/sales_code.dat','csc/sales_code.dat')
    if csc_probe['status']=='available': materialize(Path(csc_probe['resolved_source']),view/'csc/sales_code.dat')
    safe_list = staging/'available-candidates.txt'
    safe_list.write_text(''.join(f"{r['source']}:{r['destination']}\n" for r in available))
    extraction = staging/'extraction'
    try: inventory = extractor.extract(view,extraction,safe_list)
    finally: shutil.rmtree(view)
    extracted = {r['source']:r for r in inventory['files']}
    merged = []
    for probe in probes:
        row = extracted.get(probe['source'],{k:v for k,v in probe.items() if k!='resolved_source'})
        if probe.get('source_links'): row['original_system_links'] = probe['source_links']
        merged.append(row)
    inventory['files'] = merged
    inventory['list_sha256'] = digest(file_list or extractor.DEFAULT_LIST)
    inventory['ci_available_list_sha256'] = digest(safe_list)
    inventory['source_view_limited_to_safe_candidates'] = True
    inventory['source_build_prop_sha256'] = prop_hash
    inventory['summary'].update(requested=len(rows),extracted=len(extracted),
                                missing=sum(r['status']=='missing' for r in merged),
                                unresolved_external_symlinks=sum(r['status']=='unresolved_external_symlink' for r in merged),
                                unresolved_sources=sum(r['status']!='extracted' for r in merged))
    write_json(extraction/'inventory.json',inventory)
    plan = {'schema_version':1,'firmware':extractor.VERSION,'reviewed':True,
            'review_method':'deterministic source-aware CI rules; source mappings reviewed, runtime ABI not reviewed',
            'rule_code_sha256':digest(Path(__file__)), 'native_contract_sha256':digest(contracts_file),
            'allow_missing_candidates':allow_missing, 'files':[]}
    unresolved = []; essential = set(contracts['essential_files']); essential_missing = []
    for row in merged:
        source,destination = row['source'],row['destination']
        item = {'source':source,'destination':destination}
        reason = source_owned.get(source) or FIRMWARE_SYMLINK_DESTINATIONS.get(destination)
        if reason:
            item.update(action='skip',reason=reason,source_provided=True,unresolved=False)
        elif row['status']!='extracted':
            item.update(action='skip',reason=row.get('reason','not present in verified CSB1 SYSTEM'),
                        source_provided=False,unresolved=True,unresolved_status=row['status'])
        elif row.get('elf') and (not row['elf']['expected_arm32'] or not row['elf']['dynamic_audit_ok']):
            item.update(action='skip',reason='actual CSB1 candidate failed ARM32/dynamic ELF audit',
                        source_provided=False,unresolved=True,unresolved_status='incompatible_elf')
        elif row.get('elf'):
            name = PurePosixPath(destination).name
            item.update(action='module',module=name[:-3] if name.endswith('.so') else name,unresolved=False)
        else: item.update(action='copy',unresolved=False)
        if item.get('unresolved'):
            unresolved.append(item)
            if 'system/'+destination in essential: essential_missing.append(item)
        plan['files'].append(item)
    plan_file = staging/'vendor-review.json'; write_json(plan_file,plan)
    audit = {'schema_version':1,'operation':'actual-CSB1-CI-vendor-generation','model':extractor.MODEL,'firmware':extractor.VERSION,
             'success':False,'forced_diagnostic':allow_missing,'candidate_count':len(rows),
             'actual_extracted_files':len(extracted),'source_provided_skips':[r for r in plan['files'] if r.get('source_provided')],
             'unresolved_candidates':unresolved,'unresolved_count':len(unresolved),
             'essential_stock_missing':essential_missing,'essential_stock_missing_count':len(essential_missing),
             'source_build_prop_sha256':prop_hash,'source_provenance':provenance,'csc_probe':csc_probe,
             'pie_symbol_compatibility_verified':False,'device_tested':False,'release_ready':False,
             'note':'Only genuine bytes from the supplied exact-CSB1 SYSTEM are installed. Missing candidates are never supplied from 2016 or another device.'}
    write_json(staging/'generation-audit.json',audit)
    if unresolved and not allow_missing: raise ValueError(f'{len(unresolved)} stock candidates unresolved ({len(essential_missing)} essential); see generation-audit.json; no vendor installed')
    report = generator.generate(extraction,plan_file,vendor)
    report.update(forced_diagnostic=allow_missing,unresolved_candidates=unresolved,
                  essential_stock_missing=essential_missing,ready_for_functional_rom=False,
                  source_provenance=provenance,review_method=plan['review_method'])
    write_json(vendor/'vendor-audit.json',report)
    audit.update(success=True,vendor_path=str(vendor),selected_files=report['selected_files'],
                 vendor_audit_sha256=digest(vendor/'vendor-audit.json'))
    write_json(staging/'generation-audit.json',audit)
    write_json(vendor/'ci-generation-audit.json',audit)
    return audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system',required=True,type=Path);p.add_argument('--tree',required=True,type=Path);p.add_argument('--staging',required=True,type=Path)
    p.add_argument('--allow-missing-candidates',action='store_true',help='explicitly record unresolved candidates and continue diagnostic build without substitution')
    a=p.parse_args()
    try: result=prepare(a.system,a.tree,a.staging,a.allow_missing_candidates)
    except (OSError,ValueError,KeyError,RuntimeError,json.JSONDecodeError) as error:p.exit(2,f'CSB1 vendor preparation failed: {error}\n')
    print(json.dumps({k:result[k] for k in ('success','candidate_count','selected_files','unresolved_count','essential_stock_missing_count','forced_diagnostic')}))

if __name__=='__main__':main()
