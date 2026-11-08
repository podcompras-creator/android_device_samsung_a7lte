#!/usr/bin/env python3
"""Safely stage selected stock firmware payloads from ZIP/TAR/TAR.MD5.

Does not mount filesystems, run firmware code, extract arbitrary archives, or
certify Samsung signatures. Supply SYSTEM image to rootless filesystem tools on
a suitably provisioned builder, then use extract-stock.py on its SYSTEM tree.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile

IMAGE = re.compile(r'(?:system|boot|recovery|cache)\.img(?:\.ext4)?(?:\.lz4)?$', re.I)
METADATA = re.compile(r'(?:[^/]+\.pit|sales_code\.dat|SW_Configuration\.xml|customer\.xml|others\.xml)$', re.I)


def safe_name(name):
    if not name or '\\' in name or '\x00' in name or ':' in name:
        raise ValueError(f'unsafe archive path: {name!r}')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f'unsafe archive path: {name!r}')
    clean = '/'.join(part for part in p.parts if part != '.')
    if not clean:
        if name.rstrip('/') == '.':
            return ''
        raise ValueError(f'empty archive path: {name!r}')
    return clean


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def tar_md5(path):
    """Check Samsung's appended MD5 when present. This is not a signature."""
    size = path.stat().st_size
    with path.open('rb') as f:
        start = max(0, size - 4096)
        f.seek(start)
        tail = f.read()
    m = re.search(rb'([0-9a-fA-F]{32})(?:[ \t]+[^\r\n\x00]*)?[\r\n]*\Z', tail)
    if not m:
        return {'state': 'not-present', 'signature_verified': False}
    boundary = start + m.start()
    h = hashlib.md5(usedforsecurity=False)
    with path.open('rb') as f:
        remaining = boundary
        while remaining:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError('truncated TAR before MD5 footer')
            h.update(chunk); remaining -= len(chunk)
    expected = m.group(1).decode().lower()
    if h.hexdigest() != expected:
        raise ValueError(f'appended TAR MD5 mismatch: {path.name}')
    return {'state': 'matched', 'value': expected, 'tar_bytes': boundary, 'signature_verified': False}


class Stager:
    def __init__(self, output, max_file_bytes, max_total_bytes, max_members, max_depth):
        self.output = output
        self.max_file = max_file_bytes
        self.max_total = max_total_bytes
        self.max_members = max_members
        self.max_depth = max_depth
        self.members = 0
        self.declared_bytes = 0
        self.streamed_bytes = 0
        self.selected = []
        self.archives = []
        self.basenames = set()

    def account(self, name, size):
        safe_name(name)
        if size < 0 or size > self.max_file:
            raise ValueError(f'member exceeds --max-file-bytes: {name}')
        self.members += 1
        self.declared_bytes += size
        if self.members > self.max_members:
            raise ValueError('archive exceeds --max-members')
        if self.declared_bytes > self.max_total:
            raise ValueError('archive exceeds --max-total-bytes (nested containers count too)')

    def copy_stream(self, reader, target, expected):
        if expected > shutil.disk_usage(target.parent).free:
            raise ValueError(f'insufficient disk to stage {target.name} ({expected} bytes)')
        total = 0
        with target.open('xb') as out:
            while True:
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                self.streamed_bytes += len(chunk)
                if total > expected or total > self.max_file or self.streamed_bytes > self.max_total:
                    raise ValueError('actual extracted bytes exceed declared size or budget')
                out.write(chunk)
        if total != expected:
            raise ValueError('actual extracted bytes differ from declared size')
        target.chmod(0o644)

    def consume(self, reader, name, size, chain, depth):
        clean = safe_name(name)
        base = PurePosixPath(clean).name
        lower = base.lower()
        nested = lower.endswith(('.tar', '.tar.md5', '.zip'))
        if nested:
            if depth >= self.max_depth:
                raise ValueError('nested archives exceed --max-depth')
            with tempfile.TemporaryDirectory(prefix='firmware-container-', dir=self.output) as tmp:
                path = Path(tmp) / base
                self.copy_stream(reader, path, size)
                self.visit(path, chain + [clean], depth + 1)
        elif IMAGE.fullmatch(base) or METADATA.fullmatch(base):
            if base.lower() in self.basenames:
                raise ValueError(f'duplicate selected payload basename: {base}; choose source archives separately')
            self.basenames.add(base.lower())
            target = self.output / 'payloads' / base
            self.copy_stream(reader, target, size)
            self.selected.append({'archive_chain': chain, 'member': clean,
                                  'output': str(target.relative_to(self.output)),
                                  'bytes': size, 'sha256': sha256_file(target)})

    def visit(self, path, chain, depth):
        record = {'chain': chain, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        if zipfile.is_zipfile(path):
            record['format'] = 'zip'
            self.archives.append(record)
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                for info in members:
                    name = safe_name(info.filename)
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                        raise ValueError(f'ZIP links/special/encrypted entries unsupported: {name}')
                    self.account(info.filename, info.file_size)
                for info in members:
                    if not info.is_dir():
                        with archive.open(info) as reader:
                            self.consume(reader, info.filename, info.file_size, chain, depth)
        else:
            record['format'] = 'tar'
            record['appended_md5'] = tar_md5(path)
            self.archives.append(record)
            with tarfile.open(path, 'r:*') as archive:
                # Validate every header, even entries whose bytes are not selected.
                members = []
                for info in archive:
                    name = safe_name(info.name)
                    if not (info.isfile() or info.isdir()):
                        raise ValueError(f'TAR links/special entries unsupported: {name}')
                    if info.sparse is not None:
                        raise ValueError(f'GNU sparse TAR members unsupported: {name}')
                    self.account(info.name, info.size)
                    members.append(info)
                for info in members:
                    if info.isfile():
                        with archive.extractfile(info) as reader:
                            self.consume(reader, info.name, info.size, chain, depth)


def stage(source, output, max_file_bytes=16 * 1024**3, max_total_bytes=32 * 1024**3,
          max_members=10000, max_depth=2):
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.is_symlink():
        raise ValueError('output must not be a symlink')
    output = output.resolve()
    if source.is_relative_to(output):
        raise ValueError('output may not contain the input archive')
    if output.exists() and any(output.iterdir()):
        raise ValueError('output must be empty; existing progress is preserved')
    if any(v <= 0 for v in (max_file_bytes, max_total_bytes, max_members, max_depth)):
        raise ValueError('limits must be positive')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'payloads').mkdir()
    stager = Stager(output, max_file_bytes, max_total_bytes, max_members, max_depth)
    try:
        stager.visit(source, [source.name], 0)
        if not stager.selected:
            raise ValueError('no supported SYSTEM/boot/recovery/cache/PIT/CSC payload found')
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as error:
        (output / 'unpack-error.json').write_text(json.dumps({'error': str(error), 'partial_output': True}, indent=2) + '\n')
        raise
    report = {'schema_version': 1, 'operation': 'selected-firmware-payload-staging',
              'firmware_identity_verified': False, 'signature_verified': False,
              'archives': stager.archives, 'payloads': stager.selected,
              'members_checked': stager.members, 'declared_bytes_checked': stager.declared_bytes,
              'streamed_bytes': stager.streamed_bytes,
              'next': 'Read docs/unpack-stock.md. Filesystem unpack and CSB1/model/CSC verification are separate steps.'}
    (output / 'firmware-payloads.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--max-file-bytes', type=int, default=16 * 1024**3)
    p.add_argument('--max-total-bytes', type=int, default=32 * 1024**3)
    p.add_argument('--max-members', type=int, default=10000)
    p.add_argument('--max-depth', type=int, default=2)
    a = p.parse_args()
    try:
        report = stage(a.archive, a.output, a.max_file_bytes, a.max_total_bytes, a.max_members, a.max_depth)
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as error:
        p.exit(2, f'error: {error}\n')
    print(json.dumps({'payloads': len(report['payloads']), 'members_checked': report['members_checked'],
                      'signature_verified': False}, sort_keys=True))


if __name__ == '__main__':
    main()
