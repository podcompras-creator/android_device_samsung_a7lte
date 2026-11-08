#!/usr/bin/env python3
"""Generate a Pie vendor tree from a complete, explicit per-file review plan.

Never infers AOSP module conflicts, HAL ABI fixes or permission/SELinux rules.
Missing files may be skipped only with a recorded reason. Output is for diagnostic
builds; no stock hardware behavior or Pie symbol compatibility is implied.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

spec = importlib.util.spec_from_file_location('extract_stock', Path(__file__).with_name('extract-stock.py'))
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def generate(staging, plan_file, output):
    staging = staging.resolve(strict=True)
    manifest = json.loads((staging / 'inventory.json').read_text())
    plan = json.loads(plan_file.read_text())
    if (manifest.get('schema_version') != 2 or manifest.get('model') != extractor.MODEL
            or manifest.get('firmware') != extractor.VERSION or plan.get('firmware') != extractor.VERSION):
        raise ValueError('expected SM-A700FD CSB1 schema-v2 inventory and matching review plan')
    if plan.get('reviewed') is not True:
        raise ValueError('plan must be reviewed=true after per-file module/copy/skip decisions')
    rows = {r['source']: r for r in manifest['files']}
    decisions = plan['files']
    if len({r['source'] for r in decisions}) != len(decisions) or set(rows) != {r['source'] for r in decisions}:
        raise ValueError('review plan must cover every inventory source exactly once')
    output = output.absolute()
    if output.is_symlink():
        raise ValueError('output cannot be symlink')
    output = output.resolve()
    if output.is_relative_to(staging) or staging.is_relative_to(output):
        raise ValueError('staging/output trees must not overlap')
    if output.exists() and any(output.iterdir()):
        raise ValueError('output must be empty; preserve previous generated trees')
    contracts = json.loads(Path(__file__).with_name('native-contracts.json').read_text())
    source_owned = contracts['source_owned_stock_sources_to_skip']
    library_modules = {}
    for item in decisions:
        row = rows[item['source']]
        if item.get('action') == 'module' and row.get('elf') and row['elf'].get('soname'):
            library_modules.setdefault(row['elf']['soname'], []).append(item.get('module'))
    dependency_overrides = plan.get('dependency_modules', {})
    copies, modules, selected, skipped, names, destinations = [], [], [], [], set(), set()
    for decision in decisions:
        source = extractor.safe_rel(decision['source'])
        row = rows[source]
        action = decision.get('action')
        if action == 'skip':
            if not decision.get('reason', '').strip():
                raise ValueError(f'skipped {source} needs a reason (e.g. provided by platform)')
            skipped.append({'source': source, 'reason': decision['reason']})
            continue
        if source in source_owned:
            raise ValueError(f'{source}: must skip source-owned platform module: {source_owned[source]}')
        if action not in ('copy', 'module'):
            raise ValueError(f'{source}: action must be copy/module/skip, not {action!r}')
        if row['status'] != 'extracted':
            raise ValueError(f'{source}: missing in extraction; explicitly skip with reason or obtain it')
        destination = extractor.safe_rel(decision.get('destination', row['destination']))
        if destination in destinations:
            raise ValueError(f'duplicate destination {destination}')
        destinations.add(destination)
        source_file = extractor.inside(staging / 'proprietary' / source, staging)
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'hash changed since extraction: {source}')
        elf = extractor.elf_info(source_file)
        if elf and (not elf['expected_arm32'] or not elf['dynamic_audit_ok']):
            raise ValueError(f'ELF must pass ELF32 ARM/dynamic audit: {source}')
        if action == 'copy' and elf:
            raise ValueError(f'ELF {source} must be a prebuilt module (or explicitly skipped)')
        selected.append((source, source_file))
        if action == 'copy':
            copies.append(f'    $(LOCAL_PATH)/proprietary/{source}:system/{destination}')
            continue
        name = decision.get('module')
        if not name or not re.fullmatch(r'[A-Za-z0-9_.+@-]+', name):
            raise ValueError(f'{source}: specify a valid unique module name')
        if name in names:
            raise ValueError(f'duplicate module name {name}')
        names.add(name)
        dp = PurePosixPath(destination)
        suffix = '.so' if elf and destination.endswith('.so') else ('.apk' if destination.endswith('.apk') else '')
        if elf and suffix == '.so' and elf['elf_type'] != 3:
            raise ValueError(f'{source}: shared-library module requires ELF ET_DYN')
        cls = 'SHARED_LIBRARIES' if suffix == '.so' else ('APPS' if suffix == '.apk' else 'EXECUTABLES')
        if not elf and cls != 'APPS':
            raise ValueError(f'{source}: only ELF or APK modules supported; use copy for other files')
        stem = dp.name[:-len(suffix)] if suffix else dp.name
        stanza = ['include $(CLEAR_VARS)', f'LOCAL_MODULE := {name}', f'LOCAL_MODULE_CLASS := {cls}',
                  'LOCAL_MODULE_TAGS := optional', 'LOCAL_MODULE_OWNER := samsung',
                  f'LOCAL_SRC_FILES := proprietary/{source}', f'LOCAL_MODULE_STEM := {stem}',
                  f'LOCAL_MODULE_PATH := $(TARGET_OUT)/{dp.parent}']
        if suffix:
            stanza.append(f'LOCAL_MODULE_SUFFIX := {suffix}')
        if elf:
            deps = []
            for needed in elf['needed']:
                matches = library_modules.get(needed, [])
                if needed in dependency_overrides:
                    dep = dependency_overrides[needed]
                elif len(matches) == 1:
                    dep = matches[0]
                elif len(matches) > 1:
                    raise ValueError(f'{source}: ambiguous module for {needed}; set dependency_modules')
                elif needed.endswith('.so'):
                    dep = needed[:-3]
                else:
                    raise ValueError(f'{source}: set dependency_modules for unusual SONAME {needed}')
                if not isinstance(dep, str) or not re.fullmatch(r'[A-Za-z0-9_.+@-]+', dep):
                    raise ValueError(f'{source}: invalid dependency module mapping for {needed}')
                if dep != name: deps.append(dep)
            if deps: stanza.append('LOCAL_SHARED_LIBRARIES := ' + ' '.join(sorted(set(deps))))
            stanza += ['LOCAL_MULTILIB := 32', 'LOCAL_STRIP_MODULE := false']
        if cls == 'APPS':
            stanza.append('LOCAL_CERTIFICATE := PRESIGNED')
        stanza.append('include $(BUILD_PREBUILT)')
        modules.append('\n'.join(stanza))
    if not selected:
        raise ValueError('empty vendor selection')
    output.mkdir(parents=True, exist_ok=True)
    for source, src in selected:
        dst = output / 'proprietary' / source
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (output / 'Android.mk').write_text('# Generated for diagnostic Pie builds; review plan recorded.\nLOCAL_PATH := $(call my-dir)\n\n' + '\n\n'.join(modules) + '\n')
    mk = '# Generated from reviewed CSB1 inventory; NOT device-tested.\nLOCAL_PATH := vendor/samsung/a7lte\n'
    if copies:
        mk += '\nPRODUCT_COPY_FILES += \\\n' + ' \\\n'.join(copies) + '\n'
    if names:
        mk += '\nPRODUCT_PACKAGES += \\\n' + ' \\\n'.join('    ' + name for name in sorted(names)) + '\n'
    (output / 'a7lte-vendor.mk').write_text(mk)
    (output / 'BoardConfigVendor.mk').write_text('# Reserved for reviewed device-specific board flags.\n')
    shutil.copyfile(staging / 'inventory.json', output / 'stock-inventory.json')
    shutil.copyfile(plan_file, output / 'vendor-review.json')
    report = {'schema_version': 2, 'firmware': extractor.VERSION, 'model': extractor.MODEL,
              'csc_region_verified': manifest.get('csc_identity', {}).get('region_verified_from_metadata', False),
              'review_plan_sha256': hashlib.sha256(plan_file.read_bytes()).hexdigest(),
              'inventory_sha256': hashlib.sha256((staging / 'inventory.json').read_bytes()).hexdigest(),
              'native_contract_sha256': hashlib.sha256(Path(__file__).with_name('native-contracts.json').read_bytes()).hexdigest(),
              'generated_makefiles': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ('Android.mk','a7lte-vendor.mk','BoardConfigVendor.mk')},
              'reviewed_plan': True, 'selected_files': len(selected), 'skipped': skipped,
              'selected_files_hashes_verified': True, 'selected_elf32_arm_audit_passed': True,
              'ready_for_diagnostic_build': True, 'pie_symbol_compatibility_verified': False,
              'device_tested': False, 'release_ready': False,
              'note': 'Only format, paths and extraction hashes audited. Run full platform module/dependency/SELinux build and device tests.'}
    (output / 'vendor-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('staging', type=Path)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path, help='new vendor/samsung/a7lte directory')
    a = p.parse_args()
    try:
        report = generate(a.staging, a.plan, a.output)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        p.exit(2, f'error: {e}\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
