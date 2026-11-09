"""Focused static-artifact checks using temporary synthetic bytes only.

Fixtures exercise the packaging parser; they contain no usable kernel, ramdisk,
filesystem or firmware and never touch the project's artifacts directory.
"""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'built_artifacts_new', ROOT/'ci/validate-built-artifacts.py')
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def synthetic_boot(*, kernel=b'KERN'):
    """Build the minimum parseable legacy header and one synthetic QCDT entry."""
    page = 2048
    # This is a parser fixture, not a valid device tree.
    fdt = bytes.fromhex('d00dfeed') + struct.pack('>I', 40) + bytes(32)
    dt = (struct.pack('<4sII', b'QCDT', 3, 1)
          + struct.pack('<10I', 239, 8, 0, 0, 0, 0, 0, 0, page, page))
    dt = dt.ljust(page, b'\0') + fdt.ljust(page, b'\0')
    ramdisk = b'RAMD'
    os_word = ((9 << 14) << 11) | ((2019-2000) << 4) | 2
    header = bytearray(page)
    header[:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8,
                     len(kernel), 0x80008000, len(ramdisk), 0x82000000,
                     0, 0x80F00000, 0x81E00000, page, len(dt), os_word)
    sha1 = hashlib.sha1()
    for payload in (kernel, ramdisk, b'', dt):
        sha1.update(payload)
        sha1.update(struct.pack('<I', len(payload)))
    header[576:608] = sha1.digest().ljust(32, b'\0')
    return (bytes(header) + kernel.ljust(page, b'\0')
            + ramdisk.ljust(page, b'\0') + dt + b'SEANDROIDENFORCE')


SYSTEM_BYTES = b'SYNTHETIC-SYSTEM-DATA-PAYLOAD'


def synthetic_ota(path, *, device='a7lte', payload=True, boot=None):
    entries = {
        'META-INF/com/android/metadata':
            f'pre-device={device}\nota-type=BLOCK\n'.encode(),
        'META-INF/com/google/android/update-binary': b'fixture-updater',
        'META-INF/com/google/android/updater-script': b'fixture-script',
        'boot.img': synthetic_boot() if boot is None else boot,
    }
    if payload:
        entries['system.new.dat'] = SYSTEM_BYTES
        entries['system.transfer.list'] = b'4\n1\n0\n0\nnew 2,0,1\n'
    # Stored entries allow a deterministic payload-bitflip CRC negative case.
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, contents in entries.items():
            archive.writestr(name, contents)


class BuiltArtifactsNewTests(unittest.TestCase):
    def test_tiny_samsung_boot_geometry_qcdt_and_sha1(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp)/'boot.img'
            image.write_bytes(synthetic_boot())
            before = hashlib.sha256(image.read_bytes()).hexdigest()
            result = VALIDATOR.validate_boot(image)
            self.assertEqual(result['result'], 'PASS', result['errors'])
            inspection = result['inspection']
            self.assertEqual(inspection['os_version'], '9.0.0')
            self.assertEqual(inspection['qcdt']['version'], 3)
            self.assertEqual(inspection['qcdt']['entries'], 1)
            self.assertFalse(inspection['device_boot_tested'])
            self.assertFalse(inspection['trailer']['samsung_signature_verified'])
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)

    def test_boot_rejects_geometry_trailer_and_payload_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp)/'boot.img'
            wrong_geometry = bytearray(synthetic_boot())
            struct.pack_into('<I', wrong_geometry, 12, 0x80009000)
            damaged_payload = bytearray(synthetic_boot())
            damaged_payload[2048] ^= 1
            cases = (
                ('geometry', wrong_geometry, 'kernel_address'),
                ('trailer', synthetic_boot()[:-1], 'trailer'),
                ('payload', damaged_payload, 'SHA1'),
            )
            for name, contents, expected_error in cases:
                with self.subTest(name=name):
                    image.write_bytes(contents)
                    result = VALIDATOR.validate_boot(image)
                    self.assertEqual(result['result'], 'FAIL')
                    self.assertIn(expected_error, ' '.join(result['errors']))

    def test_block_ota_checks_metadata_crc_and_embedded_boot(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'lineage-fixture.zip'
            synthetic_ota(archive)
            before = hashlib.sha256(archive.read_bytes()).hexdigest()
            result = VALIDATOR.validate_ota_zip(archive)
            self.assertEqual(result['result'], 'PASS', result['errors'])
            self.assertTrue(result['crc_verified'])
            self.assertTrue(result['non_ab_ota'])
            self.assertEqual(result['system_payloads'], ['system.new.dat'])
            self.assertEqual(result['embedded_boot']['result'], 'PASS')
            self.assertEqual(result['embedded_boot_sha256'],
                             hashlib.sha256(synthetic_boot()).hexdigest())
            self.assertFalse(result['ota_signature_verified'])
            self.assertFalse(result['device_tested'])
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)

    def test_ota_rejects_wrong_device_missing_payload_and_bad_crc(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'lineage-fixture.zip'
            with self.subTest(name='wrong device'):
                synthetic_ota(archive, device='different-device')
                result = VALIDATOR.validate_ota_zip(archive)
                self.assertEqual(result['result'], 'FAIL')
                self.assertIn('pre-device', ' '.join(result['errors']))
            with self.subTest(name='missing system payload'):
                synthetic_ota(archive, payload=False)
                result = VALIDATOR.validate_ota_zip(archive)
                self.assertEqual(result['result'], 'FAIL')
                self.assertIn('system.new.dat', ' '.join(result['errors']))
            with self.subTest(name='corrupt stored entry'):
                synthetic_ota(archive)
                raw = bytearray(archive.read_bytes())
                raw[raw.index(SYSTEM_BYTES)] ^= 1
                archive.write_bytes(raw)
                result = VALIDATOR.validate_ota_zip(archive)
                self.assertEqual(result['result'], 'FAIL')
                self.assertFalse(result['crc_verified'])
                self.assertIn('CRC', ' '.join(result['errors']))

    def test_product_out_empty_partial_rom_and_mismatched_boot(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            # Nested ZIPs and standalone system.img are deliberately not outputs
            # promised by this validator's top-level scan contract.
            (output/'nested').mkdir()
            (output/'nested/ignored.zip').write_bytes(b'ignored')
            (output/'system.img').write_bytes(b'fixture-system')
            initial_names = sorted(str(p.relative_to(output)) for p in output.rglob('*'))
            result = VALIDATOR.validate_product_out(output)
            self.assertEqual(result['result'], 'NO_ARTIFACTS')
            self.assertEqual(result['artifacts'], [])
            self.assertEqual(initial_names,
                             sorted(str(p.relative_to(output)) for p in output.rglob('*')))
            (output/'boot.img').write_bytes(synthetic_boot())
            result = VALIDATOR.validate_product_out(output)
            self.assertEqual(result['result'], 'PARTIAL')
            self.assertFalse(result['rom_zip_static_validated'])
            archive = output/'lineage-fixture.zip'
            synthetic_ota(archive)
            result = VALIDATOR.validate_product_out(output)
            self.assertEqual(result['result'], 'PASS', result['errors'])
            self.assertTrue(result['rom_zip_static_validated'])
            self.assertFalse(result['flash_ready'])
            self.assertFalse(result['device_tested'])
            self.assertEqual(len(result['artifacts']), 2)
            self.assertTrue(all(len(row['sha256']) == 64 for row in result['artifacts']))
            synthetic_ota(archive, boot=synthetic_boot(kernel=b'ALT!'))
            result = VALIDATOR.validate_product_out(output)
            self.assertEqual(result['result'], 'FAIL')
            ota = next(row for row in result['artifacts'] if row['kind'] == 'ota_zip')
            self.assertIn('differs', ' '.join(ota['errors']))


if __name__ == '__main__':
    unittest.main()
