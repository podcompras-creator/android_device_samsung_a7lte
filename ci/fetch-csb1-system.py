#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Runner-only CSB1 SYSTEM acquisition from Samsung FUS, without mounting.

Requires >=9 GiB free disk and openssl, simg2img, debugfs. Never executes firmware.
Only the complete CRC-verified AP ZIP entry may produce a published SYSTEM tree.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MIN_FREE = 9 * 1024**3
NETWORK_LIMIT = 3 * 1024**3
MAX_AP_BYTES = 8 * 1024**3
MAX_SYSTEM_BYTES = 4 * 1024**3
MAX_BOOT_BYTES = 32 * 1024**2


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha256_file(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024**2), b''):
            result.update(chunk)
    return result.hexdigest()


class AuditedReader:
    """Hash every byte returned by the ZIP member and retain only a footer window."""
    def __init__(self, reader, expected_bytes):
        self.reader = reader
        self.expected_bytes = expected_bytes
        self.count = 0
        self.sha = hashlib.sha256()
        self.md5_prefix = hashlib.md5(usedforsecurity=False)
        self.tail = b''
        self.finished = False
        self.next_progress = 128 * 1024**2

    def read(self, size=-1):
        if size < 0:
            size = 1024**2
        data = self.reader.read(size)
        if not data:
            self.finished = True
            return b''
        self.count += len(data)
        if self.count > self.expected_bytes or self.count > MAX_AP_BYTES:
            raise ValueError('AP stream exceeded its declared size/budget')
        self.sha.update(data)
        combined = self.tail + data
        if len(combined) > 4096:
            self.md5_prefix.update(combined[:-4096])
            self.tail = combined[-4096:]
        else:
            self.tail = combined
        if self.count >= self.next_progress:
            print(f'AP streamed: {self.count // 1024**2} MiB uncompressed', flush=True)
            self.next_progress += 128 * 1024**2
        return data

    def finish(self):
        # Crucial: TAR stops before its footer; ZipExtFile validates CRC only at EOF.
        while self.read(1024**2):
            pass
        if self.count != self.expected_bytes:
            raise ValueError('AP ZIP entry was truncated')
        footer = re.search(rb'([0-9a-fA-F]{32})(?:[ \t]+[^\r\n\x00]*)?[\r\n]*\Z', self.tail)
        result = {'bytes': self.count, 'sha256': self.sha.hexdigest(),
                  'zip_entry_fully_consumed': True, 'zip_entry_crc_verified': True,
                  'tar_md5': {'state': 'not-present', 'signature_verified': False}}
        if footer:
            digest = self.md5_prefix.copy()
            digest.update(self.tail[:footer.start()])
            expected = footer.group(1).decode().lower()
            if digest.hexdigest() != expected:
                raise ValueError('Appended AP TAR MD5 does not match')
            result['tar_md5'] = {'state': 'matched', 'value': expected,
                                 'signature_verified': False}
        return result


def safe_name(value):
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError(f'Unsafe AP TAR member name: {value!r}')
    return p.name


def copy_member(source, destination, expected):
    digest = hashlib.sha256()
    count = 0
    with destination.open('xb') as target:
        while True:
            data = source.read(1024**2)
            if not data:
                break
            count += len(data)
            if count > expected:
                raise ValueError('TAR member exceeds declared size')
            digest.update(data)
            target.write(data)
    if count != expected:
        raise ValueError('Truncated TAR member')
    return {'path': destination.name, 'bytes': count, 'sha256': digest.hexdigest()}


def consume_ap(zip_archive, info, stage):
    if not 0 < info.file_size <= MAX_AP_BYTES or info.flag_bits & 1:
        raise ValueError('Invalid/encrypted AP ZIP entry')
    selected = {}
    members = []
    with zip_archive.open(info) as raw:
        audited = AuditedReader(raw, info.file_size)
        with tarfile.open(fileobj=audited, mode='r|') as archive:
            for member in archive:
                name = safe_name(member.name)
                members.append({'name': member.name, 'bytes': member.size})
                if len(members) > 10000 or not 0 <= member.size <= MAX_AP_BYTES:
                    raise ValueError('AP TAR member count/size budget exceeded')
                if name not in ('system.img.ext4', 'system.img', 'boot.img', 'recovery.img'):
                    continue
                if not member.isfile() or member.issparse():
                    raise ValueError('Selected payload is not a regular TAR file')
                key = 'system' if name.startswith('system.img') else name
                if key in selected:
                    raise ValueError('Duplicate selected AP payload')
                limit = MAX_SYSTEM_BYTES if key == 'system' else MAX_BOOT_BYTES
                if member.size > limit:
                    raise ValueError('Selected AP payload exceeds size limit')
                if shutil.disk_usage(stage).free < member.size + 64 * 1024**2:
                    raise ValueError('Insufficient disk while receiving AP payload')
                print(f'Receiving AP payload {name}: {member.size} bytes', flush=True)
                selected[key] = copy_member(archive.extractfile(member), stage / name, member.size)
        ap_audit = audited.finish()  # raises on corrupt ZIP CRC or TAR MD5
    if set(selected) != {'system', 'boot.img', 'recovery.img'}:
        raise ValueError('AP lacks exactly one SYSTEM, boot and recovery payload')
    ap_audit.update(zip_member=info.filename, expected_crc32=f'{info.CRC:08x}', members=members)
    return selected, ap_audit


def run_logged(argv, logfile):
    with logfile.open('wb') as log:
        subprocess.run(argv, check=True, stdout=log, stderr=subprocess.STDOUT)


def catalog_system(system, output):
    """Record real stock paths without following Android symlinks into the host."""
    entries = []
    for base, dirs, files in os.walk(system, followlinks=False):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(base) / name
            mode = path.lstat().st_mode
            entry = {'path': path.relative_to(system).as_posix()}
            if stat.S_ISLNK(mode):
                entry.update(kind='symlink', target=os.readlink(path))
            elif stat.S_ISREG(mode):
                entry.update(kind='file', bytes=path.stat().st_size)
            elif stat.S_ISDIR(mode):
                entry.update(kind='directory')
            else:
                entry.update(kind='special', mode=oct(mode))
            entries.append(entry)
            if len(entries) > 200000:
                raise ValueError('SYSTEM catalog exceeds entry budget')
    output.write_text(json.dumps({'scope': 'Actual extracted SYSTEM paths; symlinks are not followed',
                                  'entries': entries}, indent=2, sort_keys=True) + '\n')
    return {'path': output.name, 'entries': len(entries), 'sha256': sha256_file(output)}


def materialize_system(payload, stage, report, raw_limit=MAX_SYSTEM_BYTES):
    raw = stage / 'system.raw.img'
    with payload.open('rb') as source:
        header = source.read(28)
    if len(header) >= 28 and struct.unpack_from('<I', header)[0] == 0xed26ff3a:
        magic, major, minor, file_header, chunk_header, block_size, blocks, chunks, checksum = struct.unpack('<I4H4I', header)
        raw_size = block_size * blocks
        if major != 1 or file_header < 28 or chunk_header < 12 or not 0 < raw_size <= raw_limit:
            raise ValueError('Unsupported/oversized Android sparse header')
        if shutil.disk_usage(stage).free < raw_size + 128 * 1024**2:
            raise ValueError('Insufficient disk to convert complete sparse SYSTEM')
        run_logged(['simg2img', str(payload), str(raw)], stage.parent / 'simg2img.log')
        if raw.stat().st_size != raw_size:
            raise ValueError('Converted SYSTEM length differs from sparse header')
        report['sparse'] = {'logical_bytes': raw_size, 'block_size': block_size,
                            'total_blocks': blocks, 'total_chunks': chunks}
    else:
        if not 0 < payload.stat().st_size <= raw_limit:
            raise ValueError('Invalid raw SYSTEM size')
        # Move only a file created by this invocation; no second full-size copy.
        payload.rename(raw)
    with raw.open('rb') as source:
        source.seek(1024 + 56)
        if source.read(2) != b'\x53\xef':
            raise ValueError('SYSTEM is not a complete ext filesystem image')
    report['raw_system'] = {'bytes': raw.stat().st_size, 'sha256': sha256_file(raw)}
    extracted = stage / 'system'
    extracted.mkdir()
    text = str(extracted)
    if any(ord(c) < 32 for c in text):
        raise ValueError('Unsafe output directory')
    quoted = '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    # No -w, mount, sudo or execution of firmware binaries.
    run_logged(['debugfs', '-R', 'rdump / ' + quoted, str(raw)], stage.parent / 'debugfs-rdump.log')
    extractor = module('csb1_blob_properties', 'scripts/extract-stock.py')
    overrides = []
    properties, digest = extractor.properties(extracted.resolve(), duplicate_report=overrides)
    report['non_identity_property_overrides'] = overrides
    report['system_identity'] = {'model': properties['ro.product.model'],
                                  'manufacturer': properties['ro.product.manufacturer'],
                                  'pda': properties.get('ro.build.PDA'),
                                  'incremental': properties.get('ro.build.version.incremental'),
                                  'build_prop_sha256': digest}
    return extracted, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.is_symlink() or (output.exists() and any(output.iterdir())):
        parser.error('--output must be a new or empty non-symlink directory')
    output.mkdir(parents=True, exist_ok=True)
    report = {'success': False, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'model': 'SM-A700FD', 'region': 'ZTO', 'network_limit_bytes': NETWORK_LIMIT,
              'whole_encrypted_zip_crc_verified': False,
              'scope': 'Complete AP ZIP entry CRC + complete SYSTEM conversion; not whole firmware signature validation'}
    stage = None
    client = stream = None
    try:
        free = shutil.disk_usage(output).free
        report['initial_free_bytes'] = free
        if free < MIN_FREE:
            raise ValueError(f'Need >=9 GiB free before network; available {free} bytes')
        for tool in ('openssl', 'simg2img', 'debugfs'):
            if not shutil.which(tool):
                raise ValueError('Required runner tool missing: ' + tool)
        metadata_dir = output / 'fus-metadata'
        metadata_dir.mkdir()
        helper = module('runner_fus_ranges', 'scripts/fetch-fus-stock-components.py')
        client = helper.fus.FUS((ROOT / 'tooling/fus-auth/auth_param.dat').read_bytes(), metadata_dir)
        metadata = client.query(False)
        report['metadata'] = metadata
        fields = metadata.get('fields', {})
        report['requested_version'] = helper.fus.VERSION
        if metadata.get('results', {}).get('Status') not in ('S00', '200') or fields.get('BINARY_SW_VERSION') != helper.fus.VERSION or fields.get('BINARY_MODEL_NAME') != 'SM-A700FD' or fields.get('BINARY_LOCAL_CODE') != 'ZTO':
            raise ValueError('Samsung FUS did not confirm exact CSB1 model/region/version')
        init = client.post('NF_SmartDownloadBinaryInitForMass.do', helper.init_body(fields, client.nonce), False)
        report['initialization'] = init
        if init.get('results', {}).get('Status') not in ('S00', '200'):
            raise ValueError('Samsung FUS did not authorize firmware download')
        stream = helper.RangedZIP(client, fields, NETWORK_LIMIT, chunk_size=8 * 1024**2)
        report['range_chunk_bytes'] = stream.chunk_size
        stage = output / '.work-system'
        stage.mkdir()
        with zipfile.ZipFile(stream) as archive:
            expected_ap = fields.get('DEVICE_PDA_CODE1_FILE', '')
            infos = [entry for entry in archive.infolist() if entry.filename == expected_ap]
            if len(infos) != 1 or not expected_ap.startswith('AP_A700FDXXS1CSB1_'):
                raise ValueError('Official ZIP AP identity does not match FUS metadata')
            selected, report['ap_archive'] = consume_ap(archive, infos[0], stage)
        report['selected_payloads'] = selected
        system_payload = stage / selected['system']['path']
        extracted, raw = materialize_system(system_payload, stage, report)
        report['system_file_catalog'] = catalog_system(extracted, output / 'system-file-catalog.json')
        # The conventional system path appears ONLY after AP integrity and identity pass.
        extracted.rename(output / 'system')
        for name in ('boot.img', 'recovery.img'):
            (stage / name).rename(output / name)
        report['system_directory'] = 'system'
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        # Remove only known intermediates created inside this invocation's stage.
        try:
            for path in (system_payload, raw):
                if path.exists():
                    path.unlink()
            stage.rmdir()
        except OSError as cleanup_error:
            # SYSTEM is already validated; a cleanup failure is not a false fetch failure.
            report['cleanup_note'] = str(cleanup_error)
        report['success'] = True
        print('Complete CSB1 SYSTEM ready: ' + str(output / 'system'), flush=True)
        return 0
    except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        report['error'] = str(error)
        print('CSB1 acquisition failed: ' + str(error), file=sys.stderr, flush=True)
        return 1
    finally:
        if client is not None:
            report['http_events'] = client.events
        if stream is not None:
            report['network_bytes'] = stream.used
            report['range_transfers'] = stream.events
        (output / 'fetch-result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
