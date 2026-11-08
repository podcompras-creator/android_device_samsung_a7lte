#!/usr/bin/env python3
"""Inventory CSB1 stock files without executing proprietary binaries.

Input is the root of a safely unpacked/mounted stock SYSTEM filesystem, not an
Android tree, tar file or a firmware URL. Output is a staging tree, never a ROM.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys

MODEL = 'SM-A700FD'
VERSION = 'A700FDXXS1CSB1'
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = ROOT / 'android/device/samsung/a7lte/proprietary-files.txt'


def safe_rel(value):
    p = PurePosixPath(value)
    if (not value or not p.parts or p.is_absolute() or '..' in p.parts or '.' in p.parts or str(p) != value
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/+@-' for c in value)):
        raise ValueError(f'unsafe relative path: {value!r}')
    return value


def inside(path, root):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f'path escapes SYSTEM root: {path}')
    return resolved


def properties(root):
    prop = inside(root / 'build.prop', root)
    values = {}
    for line in prop.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if key in values and values[key] != value:
            raise ValueError(f'conflicting property: {key}')
        values[key] = value
    if values.get('ro.product.model') != MODEL:
        raise ValueError(f'ro.product.model must be {MODEL}')
    if values.get('ro.product.manufacturer', '').lower() != 'samsung':
        raise ValueError('ro.product.manufacturer must be samsung')
    build_keys = ('ro.build.PDA', 'ro.build.version.incremental')
    builds = [values[k] for k in build_keys if k in values]
    if not builds or VERSION not in builds:
        raise ValueError(f'an explicit PDA/incremental property must equal {VERSION}')
    if any(v != VERSION for v in builds):
        raise ValueError('PDA/incremental version properties disagree')
    device = values.get('ro.product.device', '')
    if device and not re.fullmatch(r'a7lte[a-z0-9_]*', device):
        raise ValueError('ro.product.device does not identify a7lte')
    return values, hashlib.sha256(prop.read_bytes()).hexdigest()


def read_list(path):
    rows, seen = [], set()
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        # Extract-utils hash/module syntax is intentionally rejected: this list
        # describes source:destination paths, not foreign blob replacement hashes.
        parts = line.split(':')
        if len(parts) > 2:
            raise ValueError(f'{path}:{number}: invalid mapping')
        source = safe_rel(parts[0]); destination = safe_rel(parts[-1])
        if source in seen:
            raise ValueError(f'{path}:{number}: duplicate source {source}')
        seen.add(source)
        rows.append((source, destination))
    if not rows:
        raise ValueError('empty proprietary file list')
    destinations = [x[1] for x in rows]
    if len(set(destinations)) != len(destinations):
        raise ValueError('duplicate installation destination')
    return rows


def elf_info(path):
    with path.open('rb') as f:
        head = f.read(64)
    if not head.startswith(b'\x7fELF'):
        return None
    if len(head) < 20 or head[4] not in (1, 2) or head[5] not in (1, 2):
        raise ValueError(f'invalid ELF header: {path}')
    endian = '<' if head[5] == 1 else '>'
    machine = struct.unpack_from(endian + 'H', head, 18)[0]
    elf_type = struct.unpack_from(endian + 'H', head, 16)[0]
    info = {'elf_type': elf_type, 'bits': 32 if head[4] == 1 else 64, 'machine': machine,
            'expected_arm32': head[4] == 1 and head[5] == 1 and machine == 40,
            'needed': [], 'soname': None, 'undefined_dynamic_symbols': [], 'weak_undefined_dynamic_symbols': [], 'defined_dynamic_symbols': []}
    result = subprocess.run(['readelf', '-dW', str(path)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    info['dynamic_audit_ok'] = result.returncode == 0
    if result.returncode:
        info['readelf_error'] = result.stderr.strip()
    else:
        info['needed'] = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', result.stdout)
        names = re.findall(r'\(SONAME\).*?\[([^]]+)\]', result.stdout)
        info['soname'] = names[0] if names else None
    symbols = subprocess.run(['readelf', '--dyn-syms', '--wide', str(path)], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if symbols.returncode:
        info['dynamic_audit_ok'] = False
        info['readelf_symbols_error'] = symbols.stderr.strip()
    else:
        for line in symbols.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 8 and parts[0].rstrip(':').isdigit():
                symbol = parts[7]
                if parts[6] == 'UND':
                    info['undefined_dynamic_symbols'].append(symbol)
                    if parts[4] == 'WEAK': info['weak_undefined_dynamic_symbols'].append(symbol)
                elif parts[4] in ('GLOBAL', 'WEAK') and parts[5] in ('DEFAULT', 'PROTECTED'):
                    info['defined_dynamic_symbols'].append(symbol)
        info['undefined_dynamic_symbols'] = sorted(set(info['undefined_dynamic_symbols']))
        info['defined_dynamic_symbols'] = sorted(set(info['defined_dynamic_symbols']))
    return info


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def extract(system, output, file_list):
    if shutil.which('readelf') is None:
        raise ValueError('readelf from binutils is required for the ELF audit')
    system = system.resolve(strict=True)
    if not system.is_dir():
        raise ValueError('SYSTEM input must be a directory')
    output = output.absolute()
    if output.is_symlink():
        raise ValueError('output cannot be a symlink')
    output = output.resolve()
    if output.is_relative_to(system) or system.is_relative_to(output):
        raise ValueError('input and output trees must not overlap')
    if output.exists() and any(output.iterdir()):
        raise ValueError('output must be empty; use a fresh directory to preserve prior evidence')
    props, prop_hash = properties(system)
    requested = read_list(file_list)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source, destination in requested:
        entry = {'source': source, 'destination': destination}
        path = system / source
        if not path.exists() and not path.is_symlink():
            entry['status'] = 'missing'
            rows.append(entry)
            continue
        # Reject links leaving the supplied filesystem; preserve the fact that
        # confined links were materialized, rather than silently dereferencing.
        resolved = inside(path, system)
        if not resolved.is_file():
            raise ValueError(f'not a regular file: {source}')
        if path.is_symlink():
            entry['symlink_target'] = os.readlink(path)
        dst = output / 'proprietary' / source
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resolved, dst)
        mode = 0o755 if source.startswith(('bin/', 'vendor/bin/')) else 0o644
        dst.chmod(mode)
        entry.update(status='extracted', bytes=dst.stat().st_size,
                     sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
        entry['elf'] = elf_info(dst)
        rows.append(entry)
    csc_values = {}
    if props.get('ro.csc.sales_code'):
        csc_values['ro.csc.sales_code'] = props['ro.csc.sales_code']
    sales_file = system / 'csc/sales_code.dat'
    if sales_file.exists():
        csc_values['csc/sales_code.dat'] = inside(sales_file, system).read_text().strip()
    csc = {'requested_region': 'ZTO', 'metadata': csc_values,
           'region_verified_from_metadata': bool(csc_values) and all(v == 'ZTO' for v in csc_values.values())}
    available = {}
    for row in rows:
        if row['status'] == 'extracted' and row['elf']:
            name = row['elf']['soname'] or PurePosixPath(row['destination']).name
            available.setdefault(name, []).append(row['destination'])
    abi_errors = []
    dependencies = []
    for row in rows:
        elf = row.get('elf')
        if not elf:
            continue
        if not elf['expected_arm32'] or not elf['dynamic_audit_ok']:
            abi_errors.append(row['source'])
        for name in elf['needed']:
            stock_providers = []
            if PurePosixPath(name).name == name:
                for directory in ('lib', 'vendor/lib', 'lib/hw', 'vendor/lib/hw'):
                    provider = system / directory / name
                    if provider.exists():
                        inside(provider, system)
                        stock_providers.append(directory + '/' + name)
            resolution = ('candidate-present' if name in available else
                          'stock-present-not-selected' if stock_providers else 'platform-or-missing')
            dependencies.append({'consumer': row['destination'], 'needed': name,
                                 'providers_in_extraction': available.get(name, []),
                                 'providers_in_stock_system': stock_providers, 'resolution': resolution})
    manifest = {'schema_version': 2, 'kind': 'stock-candidate-inventory',
                'model': MODEL, 'firmware': VERSION,
                'verified_build_identity_only': True, 'pie_abi_compatible': False,
                'source_build_prop_sha256': prop_hash,
                'source_properties': props, 'csc_identity': csc,
                'list_sha256': hashlib.sha256(file_list.read_bytes()).hexdigest(),
                'files': rows,
                'summary': {'requested': len(rows),
                            'extracted': sum(r['status'] == 'extracted' for r in rows),
                            'missing': sum(r['status'] == 'missing' for r in rows),
                            'abi_or_elf_audit_errors': len(abi_errors)},
                'abi_or_elf_audit_errors': abi_errors}
    write_json(output / 'inventory.json', manifest)
    write_json(output / 'elf-dependencies.json', {'note': 'Presence is not symbol/namespace/Pie compatibility. Resolve against final built system.', 'dependencies': dependencies})
    plan = {'schema_version': 1, 'firmware': VERSION, 'reviewed': False,
            'note': 'Choose copy/module/skip for every file; review duplicate AOSP/common modules, init/service placement, source firmware ABI and symbols.',
            'files': [{'source': r['source'], 'destination': r['destination'],
                       'action': 'REVIEW', 'suggested_action': 'module' if r.get('elf') else 'copy',
                       'suggested_module': PurePosixPath(r['destination']).name.removesuffix('.so') if r.get('elf') else None}
                      for r in rows]}
    write_json(output / 'vendor-review.candidate.json', plan)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('system', type=Path, help='root containing stock build.prop, bin/, lib/, vendor/')
    p.add_argument('--output', type=Path, default=Path('stock-extracted'))
    p.add_argument('--list', type=Path, default=DEFAULT_LIST)
    args = p.parse_args()
    try:
        report = extract(args.system, args.output, args.list)
    except (ValueError, OSError) as e:
        p.exit(2, f'error: {e}\n')
    print(json.dumps(report['summary'], sort_keys=True))
    return 1 if report['summary']['missing'] or report['summary']['abi_or_elf_audit_errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
