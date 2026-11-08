#!/usr/bin/env python3
"""Synthetic archive safety checks; no stock firmware or device validation."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('safe_unpack', ROOT / 'scripts/safe-unpack-stock.py')
unpack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unpack)


def tar_bytes(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        for name, value, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                info.size = len(value); archive.addfile(info, io.BytesIO(value))
            elif kind == 'symlink':
                info.type = tarfile.SYMTYPE; info.linkname = value; archive.addfile(info)
            elif kind == 'hardlink':
                info.type = tarfile.LNKTYPE; info.linkname = value; archive.addfile(info)
            elif kind == 'device':
                info.type = tarfile.CHRTYPE; archive.addfile(info)
    return data.getvalue()


class UnpackStock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a7-unpack-test-')
        self.base = Path(self.tmp.name)
        self.source = self.base / 'firmware.zip'
        self.output = self.base / 'output'

    def tearDown(self):
        self.tmp.cleanup()

    def zip(self, entries):
        with zipfile.ZipFile(self.source, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries:
                archive.writestr(name, content)

    def test_nested_tar_md5_selects_only_supported_files(self):
        tar = tar_bytes([('system.img.ext4', b'SYSTEM', 'file'), ('boot.img', b'BOOT', 'file'),
                         ('sboot.bin', b'BOOTLOADER', 'file')])
        digest = hashlib.md5(tar, usedforsecurity=False).hexdigest().encode()
        self.zip([('AP_A700FD.tar.md5', tar + digest), ('notes.txt', b'ignored')])
        report = unpack.stage(self.source, self.output)
        self.assertEqual(len(report['payloads']), 2)
        self.assertEqual((self.output / 'payloads/system.img.ext4').read_bytes(), b'SYSTEM')
        self.assertFalse((self.output / 'payloads/sboot.bin').exists())
        self.assertEqual(report['archives'][1]['appended_md5']['state'], 'matched')
        self.assertFalse(report['firmware_identity_verified'])

    def test_zip_slip_rejected_even_for_ignored_member(self):
        self.zip([('../escaped', b'bad'), ('system.img', b'ok')])
        with self.assertRaisesRegex(ValueError, 'unsafe'): unpack.stage(self.source, self.output)
        self.assertFalse((self.base / 'escaped').exists())

    def test_zip_symlink_rejected(self):
        info = zipfile.ZipInfo('link'); info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.zip([(info, b'/etc/passwd'), ('system.img', b'ok')])
        with self.assertRaisesRegex(ValueError, 'links'): unpack.stage(self.source, self.output)

    def test_tar_link_and_special_members_rejected(self):
        for kind in ('symlink', 'hardlink', 'device'):
            with self.subTest(kind=kind):
                source = self.base / (kind + '.tar')
                source.write_bytes(tar_bytes([('unsafe', '/etc/passwd', kind), ('system.img', b'ok', 'file')]))
                with self.assertRaisesRegex(ValueError, 'links/special'):
                    unpack.stage(source, self.base / kind)

    def test_declared_size_limit(self):
        self.zip([('system.img', b'12345')])
        with self.assertRaisesRegex(ValueError, 'max-file-bytes'):
            unpack.stage(self.source, self.output, max_file_bytes=4)

    def test_member_limit(self):
        self.zip([('system.img', b'a'), ('boot.img', b'b')])
        with self.assertRaisesRegex(ValueError, 'max-members'):
            unpack.stage(self.source, self.output, max_members=1)

    def test_total_size_limit(self):
        self.zip([('system.img', b'123'), ('boot.img', b'456')])
        with self.assertRaisesRegex(ValueError, 'max-total-bytes'):
            unpack.stage(self.source, self.output, max_total_bytes=5)

    def test_tampered_md5_refused(self):
        tar = tar_bytes([('system.img', b'SYSTEM', 'file')])
        self.zip([('AP.tar.md5', tar + b'0' * 32)])
        with self.assertRaisesRegex(ValueError, 'MD5 mismatch'): unpack.stage(self.source, self.output)

    def test_duplicate_selected_name_refused(self):
        self.zip([('one/system.img', b'a'), ('two/system.img', b'b')])
        with self.assertRaisesRegex(ValueError, 'duplicate selected'): unpack.stage(self.source, self.output)

    def test_existing_output_is_preserved(self):
        self.zip([('system.img', b'ok')]); self.output.mkdir()
        keep = self.output / 'keep'; keep.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'empty'): unpack.stage(self.source, self.output)
        self.assertEqual(keep.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main(verbosity=2)
