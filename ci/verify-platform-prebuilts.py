#!/usr/bin/env python3
"""Materialize real Git LFS archive inputs and verify them before Android build.

Uses the repository's normal Git LFS endpoint and exact HEAD pointer SHA/size.
No replacement APKs, source resets, signatures or firmware components are created.
Non-selected Chromium architectures are reported, not downloaded for ARM32.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile
import zlib

MARKER = b'version https://git-lfs.github.com/spec/v1\n'
ARCHIVES = {'.apk', '.jar', '.aar', '.zip'}
PRUNE = {'.git', '.repo', 'out', '__pycache__'}
INPUT_ERRORS = (OSError, ValueError, RuntimeError, NotImplementedError,
                zipfile.BadZipFile, zlib.error, UnicodeError, struct.error,
                subprocess.SubprocessError)


def pointer(raw):
    if not raw.startswith(MARKER):
        return None
    match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\n'
                         rb'oid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?', raw)
    if not match or int(match.group(2)) <= 0:
        raise ValueError('malformed Git LFS pointer')
    return {'sha256': match.group(1).decode(), 'bytes': int(match.group(2))}


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def run(argv, cwd):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_TRACE='0',
               GIT_CURL_VERBOSE='0', GIT_TRANSFER_TRACE='0')
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                            text=False, timeout=900)
    if result.returncode:
        # Preserve a diagnostic without disclosing temporary download queries.
        message = result.stderr.decode('utf-8', errors='replace')[-2500:]
        message = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?<redacted>', message)
        message = re.sub(r'(?i)(authorization:\s*(?:basic|bearer)\s+)\S+',
                         r'\1<redacted>', message)
        raise ValueError('Git LFS command failed: '+message)
    return result.stdout


def archive_check(path, webview=False):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError('duplicate archive entries: '+str(path))
        if path.suffix.lower() in {'.apk', '.jar', '.aar'} and any(
                x.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                for x in archive.infolist()):
            raise ValueError('unsupported Android/Java ZIP compression: '+str(path))
        bad = archive.testzip()
        if bad:
            raise ValueError('archive CRC mismatch: '+bad)
        report = {'zip_crc_verified': True, 'entries': len(names)}
        if webview:
            required = ('AndroidManifest.xml', 'classes.dex', 'resources.arsc',
                        'lib/armeabi-v7a/libwebviewchromium.so')
            for name in required:
                if name not in names or archive.getinfo(name).file_size == 0:
                    raise ValueError('ARM32 WebView lacks nonempty entry: '+name)
            with archive.open(required[-1]) as source:
                header = source.read(52)
            if (len(header) != 52 or header[:6] != b'\x7fELF\x01\x01'
                    or struct.unpack_from('<HH', header, 16) != (3, 40)):
                raise ValueError('WebView JNI library must be little-endian ELF32 ARM ET_DYN')
            report.update(arm32_jni_verified=True, required_entries=list(required))
        return report


def confined(tree, path):
    if not path.resolve(strict=True).is_relative_to(tree):
        raise ValueError('prebuilt input leaves platform checkout: '+str(path))
    return path


def materialize(tree, path, hydrate):
    confined(tree, path)
    repo = Path(run(['git', 'rev-parse', '--show-toplevel'], path.parent).decode().strip()).resolve()
    if not repo.is_relative_to(tree):
        raise ValueError('prebuilt repository leaves requested platform tree')
    relative = path.relative_to(repo).as_posix()
    tracked = run(['git', 'show', 'HEAD:'+relative], repo)
    expected = pointer(tracked)
    row = {'path': path.relative_to(tree).as_posix(),
           'repository': repo.relative_to(tree).as_posix(),
           'revision': run(['git', 'rev-parse', 'HEAD'], repo).decode().strip()}
    if expected:
        row['git_lfs_pointer'] = expected
        with path.open('rb') as source:
            pending = pointer(source.read(2048))
        if pending:
            if pending != expected:
                raise ValueError('working pointer differs from HEAD: '+relative)
            if not hydrate:
                raise ValueError('unresolved Git LFS archive: '+row['path'])
            if shutil.disk_usage(tree).free < 2*expected['bytes'] + 1024**3:
                raise ValueError('insufficient disk to download and materialize '+relative)
            if not shutil.which('git-lfs'):
                raise ValueError('git-lfs is required to materialize '+relative)
            run(['git', 'lfs', 'install', '--local', '--skip-smudge'], repo)
            run(['git', 'lfs', 'pull', '--include='+relative, '--exclude='], repo)
            row['materialized_with_normal_git_lfs'] = True
        if path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
            raise ValueError('materialized file does not match Git LFS SHA-256/size: '+relative)
    elif sha(path) != hashlib.sha256(tracked).hexdigest():
        raise ValueError('non-LFS prebuilt differs from tracked HEAD: '+relative)
    row.update(bytes=path.stat().st_size, sha256=sha(path))
    row.update(archive_check(path, webview=row['path'] ==
                            'external/chromium-webview/prebuilt/arm/webview.apk'))
    return row


def discover(tree):
    found = []
    inactive = []
    prefix = 'external/chromium-webview/prebuilt/'
    for base, dirs, files in os.walk(tree, followlinks=False):
        if '.find-ignore' in files:
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if x not in PRUNE and not (Path(base)/x).is_symlink()]
        for name in files:
            path = Path(base)/name
            if path.suffix.lower() not in ARCHIVES or path.is_symlink() or path.stat().st_size > 2048:
                continue
            rel = path.relative_to(tree).as_posix()
            try:
                if not pointer(path.read_bytes()):
                    continue
            except ValueError as error:
                raise ValueError(rel+': '+str(error)) from error
            if rel.startswith(prefix) and rel[len(prefix):].split('/')[0] in ('arm64', 'x86', 'x86_64'):
                inactive.append(rel)
            else:
                found.append(path)
    return found, inactive


def verify(tree, hydrate=False):
    tree = tree.resolve(strict=True)
    paths, inactive = discover(tree)
    required = tree/'external/chromium-webview/prebuilt/arm/webview.apk'
    if not required.is_file():
        raise ValueError('required ARM32 WebView input missing: '+str(required))
    if required not in paths:
        paths.insert(0, required)
    report = {'schema_version': 1, 'result': 'FAIL', 'target_arch': 'arm',
              'scope': 'Git LFS archive inputs and ARM32 WebView integrity only; no full platform or hardware validation',
              'inputs': [], 'unselected_webview_architectures': inactive}
    for path in paths:
        try:
            report['inputs'].append(materialize(tree, path, hydrate))
        except INPUT_ERRORS as error:
            report.update(error=str(error), failed_input=path.relative_to(tree).as_posix())
            return report
    remaining, _ = discover(tree)
    if remaining:
        raise ValueError('archive Git LFS pointers remain: '+', '.join(str(x.relative_to(tree)) for x in remaining))
    report['result'] = 'PASS'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--hydrate', action='store_true')
    args = parser.parse_args()
    try:
        result = verify(args.tree, args.hydrate)
    except INPUT_ERRORS as error:
        result = {'result': 'FAIL', 'scope': 'platform prebuilt input validation', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['result'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
