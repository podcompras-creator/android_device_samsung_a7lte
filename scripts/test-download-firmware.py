#!/usr/bin/env python3
"""Synthetic archive tests; no Samsung firmware authenticity claims."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('stock_fetch', Path(__file__).with_name('download-firmware.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FirmwareArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.zip'

    def create(self, name=None):
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr(name or f'{m.AP}_{m.CSC}_{m.CP}_HOME.tar.md5', b'SYNTHETIC TEST ONLY')
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_exact_names_and_expected_hash(self):
        expected = self.create()
        report = m.verify_archive(self.path, expected_sha256=expected)
        self.assertEqual(report['sha256'], expected)
        self.assertEqual(report['ap_expected'], m.AP)

    def test_wrong_package_hash_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            m.verify_archive(self.path, expected_sha256='0' * 64)

    def test_wrong_firmware_rejected(self):
        self.create('A700FDXXU1CPF1_HOME.tar.md5')
        with self.assertRaisesRegex(ValueError, 'exact AP'):
            m.verify_archive(self.path)

    def test_unsafe_member_rejected(self):
        self.create(f'../{m.AP}_{m.CSC}_HOME.tar.md5')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            m.verify_archive(self.path)

    def test_html_instead_of_zip_rejected(self):
        self.path.write_text('<html>login</html>')
        with self.assertRaises(zipfile.BadZipFile):
            m.verify_archive(self.path)

    def test_only_https_without_embedded_credentials(self):
        for url in ['http://example.com/file.zip', 'https://user:pass@example.com/a', 'file:///tmp/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.check_url(url)
        m.check_url('https://example.com/file.zip')

    def test_checksum_required_on_cli(self):
        self.create()
        with self.assertRaises(SystemExit) as cm:
            m.main(['verify', str(self.path)])
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
