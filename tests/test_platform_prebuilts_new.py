"""Prebuilt validation regression fixtures; no downloaded or installable APKs."""
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('platform_inputs', ROOT/'ci/verify-platform-prebuilts.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def fixture_apk(machine=40, omit=None):
    header = bytearray(52)
    header[:6] = b'\x7fELF\x01\x01'
    struct.pack_into('<HH', header, 16, 3, machine)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        files = {'AndroidManifest.xml': b'fixture manifest', 'classes.dex': b'fixture dex',
                 'resources.arsc': b'fixture resources',
                 'lib/armeabi-v7a/libwebviewchromium.so': bytes(header)}
        for name, data in files.items():
            if name != omit:
                archive.writestr(name, data)
    return output.getvalue()


def as_pointer(payload):
    return M.MARKER + ('oid sha256:'+hashlib.sha256(payload).hexdigest()
                       +'\nsize '+str(len(payload))+'\n').encode()


class PlatformPrebuilts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a7lte-prebuilt-fixture-')
        self.tree = Path(self.tmp.name)
        self.repo = self.tree/'external/chromium-webview/prebuilt/arm'
        self.repo.mkdir(parents=True)
        self.path = self.repo/'webview.apk'
        self.payload = fixture_apk()
        self.commit_pointer(self.payload)

    def tearDown(self):
        self.tmp.cleanup()

    def commit_pointer(self, payload):
        self.path.write_bytes(as_pointer(payload))
        for args in (['init','-q'], ['add','webview.apk'],
                     ['-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                      '-c','commit.gpgsign=false','commit','-qm','synthetic pointer fixture']):
            subprocess.run(['git',*args], cwd=self.repo, check=True, capture_output=True)

    def client(self, payload):
        original = M.run
        def dispatch(args, cwd):
            if args[:3] == ['git','lfs','install']:
                return b''
            if args[:3] == ['git','lfs','pull']:
                self.path.write_bytes(payload)
                return b''
            return original(args, cwd)
        return dispatch

    def test_text_pointer_fails_before_signing(self):
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('unresolved Git LFS', report['error'])
        self.assertTrue(self.path.read_bytes().startswith(M.MARKER))

    def test_exact_materialization_hash_crc_and_arm32(self):
        with patch.object(M,'run',side_effect=self.client(self.payload)), patch.object(M.shutil,'which',return_value='/fixture/git-lfs'), patch.object(M.shutil,'disk_usage',return_value=SimpleNamespace(free=2*1024**3)):
            report = M.verify(self.tree, True)
        self.assertEqual(report['result'], 'PASS')
        self.assertTrue(report['inputs'][0]['zip_crc_verified'])
        self.assertTrue(report['inputs'][0]['arm32_jni_verified'])
        self.assertEqual(report['inputs'][0]['sha256'], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(M.pointer(subprocess.check_output(['git','show','HEAD:webview.apk'],cwd=self.repo))['bytes'], len(self.payload))

    def test_wrong_download_hash_rejected(self):
        with patch.object(M,'run',side_effect=self.client(b'wrong payload')), patch.object(M.shutil,'which',return_value='/fixture/git-lfs'), patch.object(M.shutil,'disk_usage',return_value=SimpleNamespace(free=2*1024**3)):
            report = M.verify(self.tree, True)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('SHA-256/size', report['error'])

    def test_insufficient_space_keeps_pointer_and_skips_download(self):
        before = self.path.read_bytes()
        with patch.object(M.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            report = M.verify(self.tree, True)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('insufficient disk', report['error'])
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_native_architecture_rejected(self):
        bad = fixture_apk(machine=183)
        self.commit_pointer(bad)
        self.path.write_bytes(bad)
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('ELF32 ARM', report['error'])

    def test_missing_jni_rejected(self):
        bad = fixture_apk(omit='lib/armeabi-v7a/libwebviewchromium.so')
        self.commit_pointer(bad)
        self.path.write_bytes(bad)
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('nonempty entry', report['error'])

    def test_java_unsupported_compression_rejected_early(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_BZIP2) as archive:
            archive.writestr('AndroidManifest.xml', b'fixture manifest')
        bad = output.getvalue()
        self.commit_pointer(bad)
        self.path.write_bytes(bad)
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('Android/Java ZIP compression', report['error'])

    def test_crc_failure_even_when_object_sha_matches(self):
        bad = bytearray(self.payload)
        with zipfile.ZipFile(io.BytesIO(bad)) as archive:
            entry = archive.getinfo('classes.dex')
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        bad[offset] ^= 1
        self.commit_pointer(bad)
        self.path.write_bytes(bad)
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('CRC', report['error'])

    def test_nonselected_arch_and_staging_are_not_hydrated(self):
        self.path.write_bytes(self.payload)
        inactive = self.tree/'external/chromium-webview/prebuilt/arm64/webview.apk'
        inactive.parent.mkdir(parents=True)
        inactive.write_bytes(as_pointer(b'not the selected architecture'))
        mirror = self.tree/'.a7lte-port'
        mirror.mkdir(); (mirror/'.find-ignore').write_text('staging only\n')
        (mirror/'example.apk').write_bytes(as_pointer(b'not a product input'))
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'PASS')
        self.assertEqual(report['unselected_webview_architectures'], ['external/chromium-webview/prebuilt/arm64/webview.apk'])
        self.assertEqual(len(report['inputs']), 1)

    def test_non_lfs_source_change_is_not_silently_accepted(self):
        self.path.write_bytes(self.payload)
        subprocess.run(['git','add','webview.apk'],cwd=self.repo,check=True)
        subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                        '-c','commit.gpgsign=false','commit','-qm','tracked synthetic archive'],cwd=self.repo,check=True)
        self.path.write_bytes(fixture_apk(machine=183))
        report = M.verify(self.tree)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('differs from tracked HEAD', report['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
