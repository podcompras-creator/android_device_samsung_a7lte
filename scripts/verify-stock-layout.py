#!/usr/bin/env python3
"""Validate Samsung PIT geometry and legacy Android boot headers, offline.

No flashing, partition writing or firmware authenticity claim is performed.
PIT layout follows Benjamin-Dobell/Heimdall libpit; header follows the
legacy Android boot image header used by Samsung/Qualcomm in this generation.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

MODEL = 'SM-A700FD'
FIRMWARE = 'A700FDXXS1CSB1'
PIT_MAGIC = 0x12349876
REQUIRED = ('boot', 'recovery', 'system', 'userdata', 'cache', 'persist')
EXPECTED = dict(base=0x80000000, kernel_offset=0x8000,
                ramdisk_offset=0x02000000, tags_offset=0x01e00000, page_size=2048)


class LayoutError(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def record(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha256(path)}


def text_field(data, label):
    raw, sep, padding = data.partition(b'\0')
    if not sep:
        raise LayoutError(label + ': unterminated fixed-width string')
    try:
        s = raw.decode('ascii')
    except UnicodeDecodeError as e:
        raise LayoutError(label + ': non-ASCII text') from e
    if any(ord(c) < 32 or ord(c) > 126 for c in s):
        raise LayoutError(label + ': control character')
    return s


def parse_pit(data, sector_size, *, allow_signature_tail=False, allow_userdata_fill=False):
    if sector_size != 512:
        raise LayoutError('Only explicitly confirmed 512-byte MMC sectors are supported')
    if len(data) < 28:
        raise LayoutError('Truncated PIT header')
    magic, count = struct.unpack_from('<II', data)
    if magic != PIT_MAGIC:
        raise LayoutError('Not a Samsung PIT (magic mismatch)')
    if not 1 <= count <= 1024:
        raise LayoutError('Invalid PIT entry count')
    end = 28 + 132 * count
    if len(data) < end:
        raise LayoutError('Truncated PIT entry table')
    # Heimdall pads PIT to a 4096-byte boundary; do not interpret trailing data
    # as extra entries. Non-zero padding is suspicious and rejected.
    if any(data[end:]) and not (allow_signature_tail and len(data[end:]) == 256):
        raise LayoutError('Unexpected non-zero bytes after PIT entry table; official signed PIT needs explicit verified FUS provenance')
    entries = []
    seen = set()
    for i in range(count):
        offset = 28 + 132 * i
        binary_type, device_type, identifier, attributes, update_attributes, first, blocks, file_offset, file_size = struct.unpack_from('<9I', data, offset)
        name = text_field(data[offset + 36:offset + 68], 'partition name')
        flash = text_field(data[offset + 68:offset + 100], 'flash filename')
        fota = text_field(data[offset + 100:offset + 132], 'FOTA filename')
        if not name or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise LayoutError('Empty or unsafe PIT partition name')
        key = (binary_type, device_type, name.casefold())
        if key in seen:
            raise LayoutError('Duplicate PIT partition name: ' + name)
        seen.add(key)
        entry = dict(name=name, binary_type=binary_type, device_type=device_type,
                     identifier=identifier, attributes=attributes,
                     update_attributes=update_attributes, raw_block_size_or_offset=first,
                     block_count=blocks, file_offset=file_offset, file_size=file_size,
                     flash_filename=flash, fota_filename=fota)
        # For AP/MMC, first is a starting sector, NOT a block size in bytes.
        if binary_type == 0 and device_type == 2:
            entry.update(offset_bytes=first * sector_size, size_bytes=blocks * sector_size)
        entries.append(entry)
    selected = {}
    for name in REQUIRED:
        matches = [e for e in entries if e['name'].casefold() == name and e['binary_type'] == 0 and e['device_type'] == 2]
        if len(matches) != 1 or (matches[0]['block_count'] == 0 and not (allow_userdata_fill and name == 'userdata')):
            raise LayoutError('Missing/empty unique AP/MMC partition: ' + name)
        selected[name] = matches[0]
    intervals = sorted((e['offset_bytes'], e['offset_bytes'] + e['size_bytes'], n) for n, e in selected.items() if e['size_bytes'])
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise LayoutError('Overlapping required partitions: ' + previous[2] + '/' + current[2])
    if selected['userdata']['size_bytes'] == 0 and selected['userdata']['offset_bytes'] < max(e[1] for e in intervals):
        raise LayoutError('Fill-to-end USERDATA begins before a fixed required partition ends')
    return entries, {name: (e['size_bytes'] or None) for name, e in selected.items()}


def align(value, page):
    return (value + page - 1) // page * page


def parse_boot(path, partition_size):
    path = Path(path)
    with path.open('rb') as f:
        header = f.read(1632)
    if len(header) < 608 or header[:8] != b'ANDROID!':
        raise LayoutError(str(path) + ': missing/truncated legacy Android boot header')
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr, tags_addr, page_size, dt_size, os_version_raw = struct.unpack_from('<10I', header, 8)
    if page_size not in (2048, 4096, 8192, 16384):
        raise LayoutError(str(path) + ': unsupported boot page size')
    if not kernel_size or not ramdisk_size:
        raise LayoutError(str(path) + ': empty kernel or ramdisk')
    # Modern v1/v2 use offset 40 as header_version, not Samsung's dt_size.
    if dt_size in (1, 2):
        raise LayoutError(str(path) + ': not a supported legacy Samsung/v0 boot header')
    # Offset 44 is OS version/patchlevel even with Samsung's legacy --dt.
    # A nonzero value is normal for Pie; it is not a reserved-word failure.
    packed_version = os_version_raw >> 11
    version = ((packed_version >> 14) & 127, (packed_version >> 7) & 127, packed_version & 127)
    patch = os_version_raw & 2047
    month = patch & 15
    if month > 12:
        raise LayoutError(str(path) + ': invalid OS patchlevel month')
    patchlevel = ('%04d-%02d' % (2000 + (patch >> 4), month)) if month else None
    name = text_field(header[48:64], 'boot board name')
    kernel_offset = page_size
    ramdisk_offset = kernel_offset + align(kernel_size, page_size)
    second_offset = ramdisk_offset + align(ramdisk_size, page_size)
    dt_offset = second_offset + align(second_size, page_size)
    required_bytes = dt_offset + align(dt_size, page_size)
    file_bytes = path.stat().st_size
    if required_bytes > file_bytes:
        raise LayoutError(str(path) + ': truncated boot payload')
    if file_bytes > partition_size:
        raise LayoutError(str(path) + ': image exceeds PIT partition size')
    if dt_size:
        with path.open('rb') as f:
            f.seek(dt_offset)
            if f.read(4) != b'QCDT':
                raise LayoutError(str(path) + ': separated DT payload is not QCDT')
    observed = dict(base=kernel_addr - EXPECTED['kernel_offset'],
                    kernel_offset=EXPECTED['kernel_offset'],
                    ramdisk_offset=ramdisk_addr - EXPECTED['base'],
                    tags_offset=tags_addr - EXPECTED['base'], page_size=page_size)
    differences = {key: {'expected': value, 'observed': observed[key]} for key, value in EXPECTED.items() if observed[key] != value}
    if differences:
        raise LayoutError(str(path) + ': header differs from A7 common BoardConfig: ' + json.dumps(differences))
    return dict(format=('legacy-samsung-dt' if dt_size else 'android-v0'), kernel_size=kernel_size,
                kernel_address=kernel_addr, ramdisk_size=ramdisk_size,
                ramdisk_address=ramdisk_addr, second_size=second_size,
                second_address=second_addr, tags_address=tags_addr,
                page_size=page_size, dt_size=dt_size, board_name=name,
                os_version_raw=os_version_raw, os_version='.'.join(map(str, version)),
                os_patch_level=patchlevel,
                payload_end=required_bytes, file_bytes=file_bytes,
                trailing_bytes=file_bytes - required_bytes, geometry=observed)


def identity(path):
    props = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        if k in props and props[k] != v:
            raise LayoutError('Conflicting build.prop property: ' + k)
        props[k] = v
    if props.get('ro.product.model') != MODEL:
        raise LayoutError('Stock build.prop must identify ' + MODEL)
    versions = {props.get(k) for k in ('ro.build.PDA', 'ro.build.version.incremental')}
    if FIRMWARE not in versions:
        raise LayoutError('Stock build.prop must identify exact firmware ' + FIRMWARE)
    return {k: props[k] for k in ('ro.product.model', 'ro.product.device', 'ro.build.PDA', 'ro.build.version.incremental', 'ro.build.fingerprint') if k in props}


def fus_identity(report_path, paths):
    report = json.loads(Path(report_path).read_text())
    fields = report['metadata']['fields']
    results = report['metadata']['results']
    version = fields.get('BINARY_SW_VERSION', '').split('/')
    if (results.get('Status') != 'S00' or report['initialization']['results'].get('Status') != 'S00'
            or fields.get('BINARY_MODEL_NAME') != MODEL or fields.get('BINARY_LOCAL_CODE') != 'ZTO'
            or len(version) != 4 or version[0] != FIRMWARE or version[1] != 'A700FDZTO1CSB1'
            or report.get('requested_version') != fields.get('BINARY_SW_VERSION')):
        raise LayoutError('FUS report does not identify successful exact SM-A700FD/CSB1/ZTO request')
    components = report['components']
    for kind, path in paths.items():
        rows = [r for r in components if r.get('path') == Path(path).name]
        if len(rows) != 1 or rows[0]['sha256'] != sha256(path) or rows[0]['bytes'] != Path(path).stat().st_size:
            raise LayoutError('FUS component hash/size does not match supplied ' + kind)
        archive = rows[0].get('archive', '')
        expected = fields.get('DEVICE_CSC_FILE') if kind == 'pit' else fields.get('DEVICE_PDA_CODE1_FILE')
        if archive != expected:
            raise LayoutError('FUS component archive does not match exact AP/CSC metadata: ' + kind)
    return dict(model=MODEL, firmware=FIRMWARE, csc='ZTO', requested_version=fields['BINARY_SW_VERSION'],
                metadata_status=results['Status'], component_hashes_matched=True,
                full_archive_crc_verified=False, samsung_signature_verified=False,
                scope=report.get('scope'))


def verify(pit, boot, recovery, build_prop, sector_size, makefile, *, fus_components=None, allow_partial=False):
    paths = dict(pit=pit, boot=boot, recovery=recovery)
    props = identity(build_prop) if build_prop else None
    fus = fus_identity(fus_components, paths) if fus_components else None
    if not props and not fus:
        raise LayoutError('Stock build.prop or exact FUS component provenance required')
    pit_data = Path(pit).read_bytes()
    entries, sizes = parse_pit(pit_data, sector_size, allow_signature_tail=bool(fus), allow_userdata_fill=allow_partial)
    headers = {name: parse_boot(path, sizes[name]) for name, path in (('boot', boot), ('recovery', recovery))}
    missing = [name for name, size in sizes.items() if size is None]
    make = '# Generated from supplied SM-A700FD/CSB1 stock PIT; do not hand-edit.\n'
    if missing:
        make += '# PARTIAL: USERDATA is fill-to-end (PIT count 0); physical capacity unresolved.\n'
    for name in REQUIRED:
        value = str(sizes[name]) if sizes[name] is not None else ''
        make += 'BOARD_' + ('USERDATA' if name == 'userdata' else name.upper()) + 'IMAGE_PARTITION_SIZE :=' + (' ' + value if value else '') + '\n'
    if build_prop:
        paths['build_prop'] = build_prop
    if fus_components:
        paths['fus_components'] = fus_components
    pit_end = 28 + 132 * len(entries)
    pit_tail = pit_data[pit_end:]
    report = dict(layout_format=1, model=MODEL, firmware=FIRMWARE,
                  layout_verified=not missing, ready_for_boot_recovery=True,
                  fixed_partition_sizes_verified=True,
                  unresolved={name: 'PIT count 0 means fill-to-end; actual partition capacity must be measured on target or verified GPT, not inferred from SGPT placeholder' for name in missing},
                  verification_scope='offline supplied component hashes/provenance, PIT fields and A7 header geometry; not Samsung signature verification or device boot test',
                  sector_size=sector_size, sector_size_source='operator assertion; confirm blockdev --getss /dev/block/mmcblk0 on the target',
                  partition_sizes=sizes, partitions=entries, boot_headers=headers,
                  pit_trailer=dict(bytes=len(pit_tail), sha256=hashlib.sha256(pit_tail).hexdigest(), opaque_nonzero=any(pit_tail), samsung_signature_verified=False),
                  stock_properties=props, fus_identity=fus,
                  provenance={k: record(v) for k, v in paths.items()},
                  makefile={'path': str(Path(makefile).resolve()), 'sha256': hashlib.sha256(make.encode()).hexdigest()})
    return make, report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pit', required=True, type=Path)
    p.add_argument('--boot', required=True, type=Path)
    p.add_argument('--recovery', required=True, type=Path)
    evidence = p.add_mutually_exclusive_group(required=True)
    evidence.add_argument('--stock-build-prop', type=Path)
    evidence.add_argument('--fus-components', type=Path, help='exact official FUS component report with matching AP/CSC metadata and file hashes')
    p.add_argument('--allow-partial-layout', action='store_true', help='record unresolved USERDATA fill-to-end instead of inventing a size')
    p.add_argument('--sector-size', required=True, type=int, choices=[512], help='confirm MMC logical sector size on target before supplying 512')
    p.add_argument('--makefile', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(argv)
    try:
        inputs = {x.resolve() for x in (a.pit, a.boot, a.recovery, a.stock_build_prop, a.fus_components) if x is not None}
        if a.output.resolve() in inputs or a.makefile.resolve() in inputs or a.output.resolve() == a.makefile.resolve():
            raise LayoutError('Output paths must differ from each other and all inputs')
        make, report = verify(a.pit, a.boot, a.recovery, a.stock_build_prop, a.sector_size, a.makefile, fus_components=a.fus_components, allow_partial=a.allow_partial_layout)
        a.makefile.parent.mkdir(parents=True, exist_ok=True)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.makefile.write_text(make)
        a.output.write_text(json.dumps(report, indent=2) + '\n')
    except (OSError, ValueError, KeyError) as e:
        p.exit(2, 'layout verification failed: ' + str(e) + '\n')
    print(('PASS' if report['layout_verified'] else 'PARTIAL') + ': fixed stock partitions and boot headers verified offline; USERDATA resolved=' + str(report['layout_verified']) + '; not a flash/boot test')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
