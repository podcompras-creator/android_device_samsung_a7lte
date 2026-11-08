#!/usr/bin/env python3
"""Compare historical A7 candidates with common-tree expectations; never fetch blobs."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('extract_stock', Path(__file__).with_name('extract-stock.py'))
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def audit(a7_list, common_list):
    a7 = extractor.read_list(a7_list)
    known = {s for s, d in a7} | {d for s, d in a7}
    rows, section = [], ''
    for line in common_list.read_text().splitlines():
        line = line.strip()
        if line.startswith('#'):
            section = line.lstrip('# ').strip()
            continue
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        module = line.startswith('-'); line = line.lstrip('-')
        entry, *hashes = line.split('|')
        parts = entry.split(':')
        source, destination = parts[0], parts[-1]
        rows.append({'source': source, 'destination': destination,
                     'module_entry': module, 'upstream_replacement_hash': hashes[0] if hashes else None,
                     'section': section, 'path_in_a7_candidate_list': source in known or destination in known})
    return {'kind': 'candidate-path-reconciliation',
            'note': 'Matching paths do NOT establish firmware/ABI equality. No common replacement blob was imported.',
            'a7_candidates': len(a7), 'common_expectations': len(rows),
            'matching_paths': sum(r['path_in_a7_candidate_list'] for r in rows),
            'common_paths_absent_from_a7_list': [r for r in rows if not r['path_in_a7_candidate_list']],
            'a7_paths_not_in_common_list': [{'source': s, 'destination': d} for s, d in a7
                                           if s not in {r['source'] for r in rows} and d not in {r['destination'] for r in rows}],
            'common_entries': rows,
            'integration_decisions': {
                'bin/rild': 'extract for evidence; skip stock rild installation, use Pie source-built HIDL RIL',
                'lib/hw/camera.msm8916.so': 'rename to lib/hw/camera.vendor.msm8916.so; common Pie wrapper owns camera.msm8916',
                'lib/hw/sensors.msm8916.so': 'rename to lib/hw/sensors.vendor.msm8916.so; common source-built wrapper owns sensors.msm8916',
                'lib/libsec-ril-dsds.so': 'retain /system/lib location expected by DSDS service',
                'lib/libsec-ril.so': 'retain /system/lib location expected by single-SIM service',
                'vendor/firmware/keymaste.*': 'historical stock basename mapped to vendor/firmware/keymaster/keymaster.*; verify from actual CSB1',
                'foreign_common_hashes': 'never imported automatically; replace only with audited Samsung CSB1 or source-built compatible alternatives'}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a7-list', type=Path, default=extractor.DEFAULT_LIST)
    p.add_argument('--common-list', type=Path, default=ROOT / 'sources/common/proprietary-files.txt')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    data = json.dumps(audit(a.a7_list, a.common_list), indent=2) + '\n'
    if a.output:
        a.output.write_text(data)
    else:
        print(data, end='')


if __name__ == '__main__':
    main()
