#!/usr/bin/env python3
"""Fetch an authorized direct HTTPS firmware URL, or verify a local stock archive.
This does not solve CAPTCHA, log in, scrape gated download links, or flash a device.
Published mirror MD5 values identify packages; they do not authenticate Samsung.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile

MODEL = 'SM-A700FD'
AP = 'A700FDXXS1CSB1'
CSC = 'A700FDZTO1CSB1'
CP = 'A700FDXXU1CPF1'


def check_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('Use a direct HTTPS URL without embedded credentials')


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def digest_file(path):
    digests = {'md5': hashlib.md5(), 'sha256': hashlib.sha256()}
    with path.open('rb') as src:
        for data in iter(lambda: src.read(1024 * 1024), b''):
            for h in digests.values(): h.update(data)
    return {name: h.hexdigest() for name, h in digests.items()}


def verify_archive(path, expected_md5=None, expected_sha256=None):
    hashes = digest_file(path)
    for key, expected in [('md5', expected_md5), ('sha256', expected_sha256)]:
        if expected and hashes[key].lower() != expected.lower():
            raise ValueError(f'{key} mismatch: package rejected')
    # Read central directory only; never extract untrusted archive paths here.
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if not names or len(names) > 10000:
            raise ValueError('Empty or implausibly large ZIP directory')
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise ValueError('Unsafe member path in firmware ZIP')
        if not any(AP in name and CSC in name for name in names):
            raise ValueError('Archive filenames do not identify exact AP and ZTO CSC')
    return {'model_expected': MODEL, 'ap_expected': AP, 'csc_expected': CSC,
            'cp_expected': CP, 'bytes': path.stat().st_size, **hashes,
            'zip_members': names,
            'validation_scope': 'hash and ZIP directory; build.prop, PIT and image contents still require audit'}


def download(url, destination, maximum_bytes):
    check_url(url)
    if destination.exists():
        raise ValueError('Destination exists; use verify or choose a new path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.part')
    if temporary.exists():
        raise ValueError('Partial file exists; preserve/inspect it or choose a new output path')
    request = urllib.request.Request(url, headers={'User-Agent': 'a7lte-stock-fetch/1.0'})
    opener = urllib.request.build_opener(HTTPSRedirect())
    with opener.open(request, timeout=45) as response:
        check_url(response.url)
        if response.status != 200:
            raise ValueError(f'Expected HTTP 200; received {response.status}')
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type or 'application/json' in content_type:
            raise ValueError('Server returned a page/JSON, not a firmware archive')
        length = response.headers.get('Content-Length')
        length = int(length) if length is not None else None
        if length is not None and length > maximum_bytes:
            raise ValueError('Download exceeds --max-bytes')
        free = shutil.disk_usage(destination.parent).free
        required = (length if length is not None else maximum_bytes) + 64 * 1024**2
        if free < required:
            raise ValueError(f'Insufficient free disk: need {required}, available {free} bytes')
        total = 0
        with temporary.open('xb') as out:
            while True:
                data = response.read(1024 * 1024)
                if not data: break
                total += len(data)
                if total > maximum_bytes:
                    raise ValueError('Download exceeded maximum size; partial file retained')
                out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if length is not None and total != length:
            raise ValueError('Truncated download; partial file retained')
    return temporary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('sources', help='show verified indexes and package-specific mirror checksums')
    for command in ['download', 'verify']:
        q = sub.add_parser(command)
        q.add_argument('archive', type=Path)
        q.add_argument('--expected-md5')
        q.add_argument('--expected-sha256')
        if command == 'download':
            q.add_argument('--url', required=True, help='direct HTTPS URL acquired through authorized site flow')
            q.add_argument('--max-bytes', type=int, default=3 * 1024**3)
    a = p.parse_args(argv)
    try:
        if a.command == 'sources':
            print(Path(__file__).with_name('firmware-sources.json').read_text())
            return 0
        if not (a.expected_md5 or a.expected_sha256):
            p.error('Provide a package-specific expected MD5 or SHA-256; do not mix mirror checksums')
        for key, length in [('expected_md5', 32), ('expected_sha256', 64)]:
            value = getattr(a, key)
            if value is not None and (len(value) != length or any(c not in '0123456789abcdefABCDEF' for c in value)):
                p.error(f'Invalid {key}')
        target = a.archive
        if a.command == 'download':
            if a.max_bytes <= 0: p.error('--max-bytes must be positive')
            target = download(a.url, a.archive, a.max_bytes)
        report = verify_archive(target, a.expected_md5, a.expected_sha256)
        report['verified_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if a.command == 'download':
            os.link(target, a.archive)  # refuse a destination created during download
            target.unlink()
        report_path = a.archive.with_name(a.archive.name + '.inventory.json')
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
