#!/usr/bin/env python3
"""Statically validate artifacts already present in a supplied a7lte PRODUCT_OUT.

No image or ZIP is created, repaired, signed, copied, flashed, or executed. A PASS
checks packaging only; it does not establish build provenance or hardware support.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'a7lte_samsung_boot_inspector', ROOT/'scripts/inspect-samsung-boot.py')
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)

# Verified against official CSB1 boot/recovery/PIT, not historical A7 guesses.
# Evidence: logs/phase3-boot/official-{boot,recovery}-inspection.json and
# logs/phase3-boot/official-layout-partial.json. USERDATA is not inferred here.
GEOMETRY = {
    'page_size': 2048,
    'kernel_address': 0x80008000,
    'ramdisk_address': 0x82000000,
    'second_address': 0x80F00000,
    'tags_address': 0x81E00000,
}
PARTITION_LIMITS = {'boot': 13631488, 'recovery': 15728640}
METADATA_ENTRY = 'META-INF/com/android/metadata'
UPDATER_ENTRIES = ('META-INF/com/google/android/update-binary',
                   'META-INF/com/google/android/updater-script')
SCOPE = ('Static packaging, hashes and ZIP CRC only; no firmware signature, '
         'build provenance, filesystem semantics, HAL compatibility, flashing '
         'or device boot/hardware validation')


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def validate_boot(path, *, kind='boot'):
    """Inspect an existing Samsung image using the shared legacy-format parser."""
    image = Path(path)
    result = {'result': 'FAIL', 'scope': SCOPE, 'errors': []}
    try:
        report, _ = BOOT.inspect(image)
        result['inspection'] = report
        for name, expected in GEOMETRY.items():
            if report[name] != expected:
                result['errors'].append(
                    f'{name}: {report[name]:#x}, expected verified A7 {expected:#x}')
        if not report['qcdt'] or report['qcdt']['version'] != 3:
            result['errors'].append('native A7 packaging requires nonempty Samsung QCDT v3')
        if report['os_version'] != '9.0.0':
            result['errors'].append('boot header OS version must be Android 9.0.0')
        if image.stat().st_size > PARTITION_LIMITS[kind]:
            result['errors'].append(f'{kind} image exceeds verified CSB1 partition capacity')
        if 'NONFLASHABLE' in (report['board']+' '+report['cmdline']).upper():
            result['errors'].append('packaging fixture marker is not a built product image')
        for name, payload in report['payloads'].items():
            if payload['offset'] % report['page_size']:
                result['errors'].append(f'{name} file offset is not page aligned')
        ranges = []
        for payload, address in (('kernel', 'kernel_address'),
                                 ('ramdisk', 'ramdisk_address'),
                                 ('second', 'second_address')):
            size = report['payloads'][payload]['bytes']
            start = report[address]
            if size:
                if start+size > 1 << 32:
                    result['errors'].append(f'{payload} load range exceeds 32-bit address space')
                ranges.append((start, start+size, payload))
        ranges.sort()
        for first, second in zip(ranges, ranges[1:]):
            if first[1] > second[0]:
                result['errors'].append(f'{first[2]} and {second[2]} load ranges overlap')
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        result['errors'].append(str(error))
    result['result'] = 'PASS' if not result['errors'] else 'FAIL'
    return result


def metadata_values(raw):
    """Reject ambiguous duplicate metadata keys rather than silently overwriting."""
    values = {}
    for line in raw.decode('utf-8').splitlines():
        if not line.strip():
            continue
        if '=' not in line:
            raise ValueError('malformed Android OTA metadata line')
        key, value = line.split('=', 1)
        if key in values:
            raise ValueError('duplicate Android OTA metadata key: '+key)
        values[key] = value
    return values


def regular_zip_entry(info):
    mode = info.external_attr >> 16
    return not info.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)


def validate_ota_zip(path):
    """Stream every entry for CRC, then inspect the expected non-A/B OTA layout."""
    result = {'result': 'FAIL', 'scope': SCOPE, 'errors': [],
              'crc_verified': False, 'non_ab_ota': False,
              'ota_signature_verified': False,
              'firmware_signature_verified': False, 'device_tested': False}
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            duplicates = sorted(n for n, count in Counter(names).items() if count > 1)
            if duplicates:
                raise ValueError('duplicate ZIP entry names: '+', '.join(duplicates[:10]))
            for name in names:
                relative = PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in name:
                    raise ValueError('unsafe/noncanonical OTA entry path: '+name)
            # ZipFile.testzip streams each file in bounded chunks and checks CRC.
            bad = archive.testzip()
            if bad is not None:
                raise ValueError('ZIP CRC mismatch: '+bad)
            result.update(crc_verified=True, crc_method='ZipFile.testzip (bounded streaming)',
                          entries=len(entries),
                          total_uncompressed_bytes=sum(x.file_size for x in entries))
            for required in (METADATA_ENTRY, *UPDATER_ENTRIES, 'boot.img'):
                if required not in names:
                    result['errors'].append('missing OTA entry: '+required)
                else:
                    entry = archive.getinfo(required)
                    if not regular_zip_entry(entry) or not entry.file_size:
                        result['errors'].append('OTA entry must be a nonempty regular file: '+required)
            if METADATA_ENTRY in names:
                if archive.getinfo(METADATA_ENTRY).file_size > 1024*1024:
                    raise ValueError('OTA metadata exceeds 1 MiB inspection limit')
                metadata = metadata_values(archive.read(METADATA_ENTRY))
                result['metadata'] = metadata
                if metadata.get('pre-device') != 'a7lte':
                    result['errors'].append('OTA metadata pre-device must equal a7lte')
                if metadata.get('ota-type') != 'BLOCK':
                    result['errors'].append('expected non-A/B ota-type=BLOCK')
            if 'payload.bin' in names or 'payload_properties.txt' in names:
                result['errors'].append('A/B update payload is not the native non-A/B layout')
            system_payloads = [n for n in ('system.new.dat.br', 'system.new.dat', 'system.img')
                               if n in names and archive.getinfo(n).file_size
                               and regular_zip_entry(archive.getinfo(n))]
            if len(system_payloads) != 1:
                result['errors'].append('expected exactly one nonempty system.new.dat[.br] or system.img payload')
            elif system_payloads[0] != 'system.img':
                if ('system.transfer.list' not in names
                        or not regular_zip_entry(archive.getinfo('system.transfer.list'))
                        or not archive.getinfo('system.transfer.list').file_size):
                    result['errors'].append('block system payload requires nonempty system.transfer.list')
            result['system_payloads'] = system_payloads
            if 'boot.img' in names and regular_zip_entry(archive.getinfo('boot.img')):
                entry = archive.getinfo('boot.img')
                if not 0 < entry.file_size <= PARTITION_LIMITS['boot']:
                    result['errors'].append('embedded boot size is empty or exceeds CSB1 boot capacity')
                else:
                    # Only a temporary inspection copy; never an installable artifact output.
                    with tempfile.TemporaryDirectory(prefix='a7lte-ota-inspection-') as temp:
                        image = Path(temp)/'embedded-boot.img'
                        with archive.open(entry) as source, image.open('wb') as output:
                            shutil.copyfileobj(source, output, length=1024*1024)
                        result['embedded_boot_sha256'] = sha256(image)
                        boot = validate_boot(image)
                        if 'inspection' in boot:
                            boot['inspection']['image'] = 'ZIP entry: boot.img'
                        result['embedded_boot'] = boot
                        if boot['result'] != 'PASS':
                            result['errors'].append('embedded boot image failed static Samsung validation')
            result['non_ab_ota'] = (result.get('metadata', {}).get('ota-type') == 'BLOCK'
                                   and 'payload.bin' not in names)
    except (OSError, ValueError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile, UnicodeError, EOFError, zlib.error,
            struct.error) as error:
        result['errors'].append(str(error))
    result['result'] = 'PASS' if not result['errors'] else 'FAIL'
    return result


def validate_product_out(path):
    directory = Path(path).absolute()
    report = {'schema_version': 1, 'scope': SCOPE,
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'product': 'a7lte', 'product_out': str(directory),
              'artifacts': [], 'errors': [], 'device_tested': False,
              'flash_ready': False, 'rom_zip_static_validated': False}
    if not directory.is_dir():
        report.update(result='NO_ARTIFACTS', completeness='none')
        report['errors'].append('supplied PRODUCT_OUT is absent or not a directory')
        return report
    candidates = [directory/n for n in ('boot.img', 'recovery.img')
                  if (directory/n).exists() or (directory/n).is_symlink()]
    candidates += sorted(directory.glob('*.zip'))
    for artifact in candidates:
        kind = 'ota_zip' if artifact.suffix == '.zip' else artifact.stem
        row = {'name': artifact.name, 'path': str(artifact), 'kind': kind,
               'result': 'FAIL', 'errors': []}
        try:
            if artifact.is_symlink() or not artifact.is_file():
                raise ValueError('artifact must be a regular output file, not a symlink')
            before = artifact.stat()
            row.update(bytes=before.st_size, sha256=sha256(artifact))
            validation = (validate_ota_zip(artifact) if kind == 'ota_zip'
                          else validate_boot(artifact, kind=kind))
            row['validation'] = validation
            row['result'] = validation['result']
            row['errors'] += validation['errors']
            after = artifact.stat()
            if ((before.st_size, before.st_mtime_ns, before.st_ino)
                    != (after.st_size, after.st_mtime_ns, after.st_ino)):
                raise ValueError('artifact changed during static validation')
        except (OSError, ValueError) as error:
            row['errors'].append(str(error))
            row['result'] = 'FAIL'
        report['artifacts'].append(row)
    boot = next((r for r in report['artifacts'] if r['kind'] == 'boot'), None)
    for row in report['artifacts']:
        embedded_hash = row.get('validation', {}).get('embedded_boot_sha256')
        if embedded_hash and boot and boot.get('sha256') != embedded_hash:
            row['errors'].append('OTA boot.img differs from PRODUCT_OUT/boot.img')
            row['result'] = 'FAIL'
    report['rom_zip_static_validated'] = any(
        r['kind'] == 'ota_zip' and r['result'] == 'PASS' for r in report['artifacts'])
    if not report['artifacts']:
        report.update(result='NO_ARTIFACTS', completeness='none')
        report['errors'].append('no existing boot.img, recovery.img or top-level OTA ZIP in PRODUCT_OUT')
    elif any(r['result'] != 'PASS' for r in report['artifacts']):
        report.update(result='FAIL', completeness='invalid_artifact')
    elif report['rom_zip_static_validated']:
        report.update(result='PASS', completeness='rom_zip_present')
    else:
        report.update(result='PARTIAL', completeness='images_only')
        report['errors'].append('no statically validated ROM OTA ZIP; image validation cannot establish ROM build success')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-out', type=Path, required=True,
                        help='existing PRODUCT_OUT directory; only its top-level outputs are inspected')
    parser.add_argument('--output', type=Path, required=True, help='JSON report destination')
    args = parser.parse_args()
    if args.output.suffix.lower() != '.json':
        parser.error('--output must be a JSON report, never an image or ZIP')
    if args.output.is_symlink():
        parser.error('JSON report destination cannot be a symlink')
    directory = args.product_out.absolute()
    output = args.output.absolute()
    # Avoid creating reports inside a ZIP-shaped directory or replacing an input.
    inputs = [directory/'boot.img', directory/'recovery.img', *directory.glob('*.zip')]
    if any(output.resolve() == value.resolve() for value in inputs):
        parser.error('report destination cannot overwrite an input artifact')
    report = validate_product_out(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(report['result']+': '+str(len(report['artifacts']))+' actual artifacts; '
          'ROM ZIP static validation='+str(report['rom_zip_static_validated']))
    return 0 if report['result'] == 'PASS' else (1 if report['result'] == 'FAIL' else 2)


if __name__ == '__main__':
    raise SystemExit(main())
