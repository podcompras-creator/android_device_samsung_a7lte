"""Targeted runner acquisition tests: synthetic archives, no firmware download."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_stock_fetch', ROOT / 'ci/fetch-csb1-system.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def ap_tar(footer=True, members=None):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as tar:
        for name, payload in members or [('boot.img', b'BOOT'), ('recovery.img', b'RECOVERY'), ('system.img.ext4', b'SYNTHETIC_SYSTEM')]:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    raw = data.getvalue()
    if footer:
        raw += hashlib.md5(raw).hexdigest().encode() + b'  AP_SYNTHETIC.tar\n'
    return raw


def ap_zip(payload):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('AP_SYNTHETIC.tar.md5', payload)
    return data.getvalue()


class RunnerStockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stage = Path(self.tmp.name)

    def test_complete_ap_crc_and_tar_md5(self):
        raw = ap_tar()
        with zipfile.ZipFile(io.BytesIO(ap_zip(raw))) as archive:
            selected, report = m.consume_ap(archive, archive.infolist()[0], self.stage)
        self.assertEqual(set(selected), {'boot.img', 'recovery.img', 'system'})
        self.assertTrue(report['zip_entry_crc_verified'])
        self.assertEqual(report['bytes'], len(raw))
        self.assertEqual(report['tar_md5']['state'], 'matched')
        self.assertEqual(report['sha256'], hashlib.sha256(raw).hexdigest())

    def test_crc_failure_in_footer_is_not_ignored(self):
        raw = ap_tar()
        zipped = bytearray(ap_zip(raw))
        name_length, extra_length = struct.unpack_from('<HH', zipped, 26)
        offset = 30 + name_length + extra_length
        zipped[offset + len(raw) - 1] ^= 1
        with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
            with self.assertRaises(zipfile.BadZipFile):
                m.consume_ap(archive, archive.infolist()[0], self.stage)
        self.assertFalse((self.stage / 'system').exists())

    def test_wrong_tar_md5_with_valid_zip_crc_rejected(self):
        raw = ap_tar(False)
        raw += b'0' * 32 + b'  AP_SYNTHETIC.tar\n'
        with zipfile.ZipFile(io.BytesIO(ap_zip(raw))) as archive:
            with self.assertRaisesRegex(ValueError, 'MD5'):
                m.consume_ap(archive, archive.infolist()[0], self.stage)

    def test_truncated_ap_stream_rejected(self):
        reader = m.AuditedReader(io.BytesIO(b'abc'), 4)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            reader.finish()

    def test_duplicate_or_unsafe_payload_rejected(self):
        for members in [[('boot.img', b'A'), ('boot.img', b'B')], [('../boot.img', b'A')]]:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(io.BytesIO(ap_zip(ap_tar(members=members)))) as archive:
                    with self.assertRaises(ValueError):
                        m.consume_ap(archive, archive.infolist()[0], Path(tmp))

    def test_local_low_space_fails_before_network_without_publishing(self):
        # This test only runs the real free-space guard on this small sandbox.
        if shutil.disk_usage(self.stage).free >= m.MIN_FREE:
            self.skipTest('Host has enough space; guard is exercised on the small local environment')
        dest = self.stage / 'output'
        process = subprocess.run(['python3', str(ROOT / 'ci/fetch-csb1-system.py'), '--output', str(dest)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(process.returncode, 1)
        report = json.loads((dest / 'fetch-result.json').read_text())
        self.assertFalse(report['success'])
        self.assertIn('9 GiB', report['error'])
        self.assertNotIn('http_events', report)
        self.assertFalse((dest / 'system').exists())

    def test_real_synthetic_ext4_identity_gate(self):
        tools = ROOT / 'host/stock-tools/bin'
        if not (tools / 'mkfs.ext4').exists():
            self.skipTest('Local optional ext4 tools not bootstrapped')
        old_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(tools) + ':' + old_path
        self.addCleanup(os.environ.__setitem__, 'PATH', old_path)
        source = self.stage / 'root'
        source.mkdir()
        props = 'ro.product.model=SM-A700FD\nro.product.manufacturer=samsung\nro.product.device=a7lte\nro.build.PDA=A700FDXXS1CSB1\nro.build.version.incremental=A700FDXXS1CSB1\n'
        (source / 'build.prop').write_text(props)
        raw = self.stage / 'source.img'
        with raw.open('wb') as out:
            out.truncate(16 * 1024**2)
        subprocess.run([str(tools / 'mkfs.ext4'), '-q', '-F', '-d', str(source), str(raw)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stage = self.stage / 'working'
        stage.mkdir()
        sparse = stage / 'system.img.ext4'
        subprocess.run([str(tools / 'img2simg'), str(raw), str(sparse)], check=True)
        report = {}
        extracted, converted = m.materialize_system(sparse, stage, report)
        self.assertEqual((extracted / 'build.prop').read_text(), props)
        self.assertEqual(report['system_identity']['pda'], 'A700FDXXS1CSB1')
        self.assertEqual(report['raw_system']['sha256'], m.sha256_file(raw))
        self.assertEqual(converted.stat().st_size, 16 * 1024**2)
        self.assertFalse((self.stage / 'system').exists())


    def test_configurable_range_chunk_boundary_and_cache(self):
        helper = m.module('ci_chunk_fixture', 'scripts/fetch-fus-stock-components.py')
        chunk_size = 2 * 1024**2
        plain = bytes(range(256)) * (chunk_size // 256) + b'0123456789abcdef'
        fields = {'BINARY_BYTE_SIZE': str(len(plain)), 'MODEL_PATH': '/neofus/9/',
                  'BINARY_NAME': 'SM-A700FD_1_20190319093540_yipiin0bmb_fac.zip.enc4',
                  'LOGIC_VALUE_FACTORY': '0123456789abcdef'}
        key = hashlib.md5(helper.fus.logic_check(helper.fus.VERSION, fields['LOGIC_VALUE_FACTORY']).encode()).hexdigest()
        encrypted = subprocess.run(['openssl', 'enc', '-e', '-aes-128-ecb', '-K', key, '-nopad'], input=plain, stdout=subprocess.PIPE, check=True).stdout
        requests = []
        class Response:
            status = 206
            def __init__(self, start, end):
                self.data = encrypted[start:end + 1]
                self.headers = {'Content-Range': f'bytes {start}-{end}/{len(encrypted)}'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, length): return self.data[:length]
        class Opener:
            def open(self, request, timeout):
                requested = request.get_header('Range')
                start, end = map(int, requested.removeprefix('bytes=').split('-'))
                requests.append((start, end))
                return Response(start, end)
        class Client:
            nonce = ''; signature = ''; opener = Opener()
        stream = helper.RangedZIP(Client(), fields, len(encrypted), chunk_size=chunk_size)
        stream.seek(chunk_size - 8)
        self.assertEqual(stream.read(24), plain[chunk_size - 8:])
        self.assertEqual(requests, [(0, chunk_size - 1), (chunk_size, len(encrypted) - 1)])
        self.assertEqual(stream.used, len(encrypted))
        stream.seek(3)
        self.assertEqual(stream.read(8), plain[3:11])
        self.assertEqual(len(requests), 2, 'Cached reads must not refetch')
        self.assertEqual(helper.RangedZIP(Client(), fields, len(encrypted)).chunk_size, 1024**2)
        for invalid in (0, 16, 1024**2 + 1, 17 * 1024**2):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                helper.RangedZIP(Client(), fields, len(encrypted), chunk_size=invalid)


if __name__ == '__main__':
    unittest.main()
