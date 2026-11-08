"""Synthetic malformed-file tests; no real Samsung firmware is represented."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('stock_layout', Path(__file__).resolve().parents[1] / 'scripts/verify-stock-layout.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def pit_fixture():
    names = ['BOOT', 'RECOVERY', 'SYSTEM', 'USERDATA', 'CACHE', 'PERSIST']
    blob = struct.pack('<II', M.PIT_MAGIC, len(names)) + bytes(20)
    for index, name in enumerate(names):
        # 2000 is a starting SECTOR, deliberately unlike a sector size.
        fields = (0, 2, index, 1, 0, 2000 + index * 10000, 8192, 0, 0)
        blob += struct.pack('<9I', *fields)
        for s in (name, name.lower() + '.img', ''):
            blob += s.encode().ljust(32, b'\0')
    return blob.ljust(4096, b'\0')


def boot_fixture(dt=True):
    header = b'ANDROID!' + struct.pack('<10I', 16, 0x80008000, 16, 0x82000000, 0, 0, 0x81e00000, 2048, 16 if dt else 0, 0)
    header += bytes(1632 - len(header))
    blob = header.ljust(2048, b'\0') + b'K' * 16 + bytes(2032) + b'R' * 16 + bytes(2032)
    if dt:
        blob += b'QCDT' + bytes(2044)
    return blob


class StockLayoutTests(unittest.TestCase):
    def test_mmc_start_offset_is_not_byte_blocksize(self):
        entries, sizes = M.parse_pit(pit_fixture(), 512)
        self.assertEqual(entries[0]['offset_bytes'], 2000 * 512)
        self.assertEqual(sizes['boot'], 8192 * 512)
        self.assertNotEqual(sizes['boot'], 8192 * 2000)

    def test_malformed_pit(self):
        good = pit_fixture()
        for bad in (good[:20], good[:100], b'BAD!' + good[4:], good[:4] + struct.pack('<I', 1025) + good[8:], good + b'not-padding'):
            with self.subTest(length=len(bad)):
                with self.assertRaises(M.LayoutError):
                    M.parse_pit(bad, 512)
        with self.assertRaises(M.LayoutError):
            M.parse_pit(good, 4096)

    def test_overlap_and_unsafe_name(self):
        good = bytearray(pit_fixture())
        struct.pack_into('<I', good, 28 + 132 + 20, 2001)
        with self.assertRaisesRegex(M.LayoutError, 'Overlapping'):
            M.parse_pit(good, 512)
        good = bytearray(pit_fixture())
        good[28 + 36:28 + 68] = b'../BOOT'.ljust(32, b'\0')
        with self.assertRaisesRegex(M.LayoutError, 'unsafe'):
            M.parse_pit(good, 512)

    def test_boot_geometry_payload_and_partition_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'boot.img'
            p.write_bytes(boot_fixture())
            result = M.parse_boot(p, 8192)
            self.assertEqual(result['geometry'], M.EXPECTED)
            self.assertEqual(result['dt_size'], 16)
            with self.assertRaisesRegex(M.LayoutError, 'exceeds PIT'):
                M.parse_boot(p, 4096)
            p.write_bytes(boot_fixture()[:-100])
            with self.assertRaisesRegex(M.LayoutError, 'truncated'):
                M.parse_boot(p, 8192)
            blob = bytearray(boot_fixture())
            struct.pack_into('<I', blob, 8 + 3 * 4, 0x83000000)
            p.write_bytes(blob)
            with self.assertRaisesRegex(M.LayoutError, 'BoardConfig'):
                M.parse_boot(p, 8192)
            p.write_bytes(boot_fixture(dt=False))
            self.assertEqual(M.parse_boot(p, 8192)['dt_size'], 0)

    def test_identity_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prop = root / 'build.prop'
            prop.write_text('ro.product.model=SM-A700FD\nro.build.PDA=A700FDXXS1CSB1\n')
            pit = root / 'stock.pit'; pit.write_bytes(pit_fixture())
            boot = root / 'boot.img'; boot.write_bytes(boot_fixture())
            recovery = root / 'recovery.img'; recovery.write_bytes(boot_fixture())
            make, report = M.verify(pit, boot, recovery, prop, 512, root / 'partition-sizes.mk')
            self.assertTrue(report['layout_verified'])
            self.assertEqual(report['layout_format'], 1)
            self.assertEqual(len(report['makefile']['sha256']), 64)
            self.assertIn('BOARD_SYSTEMIMAGE_PARTITION_SIZE := 4194304', make)
            prop.write_text('ro.product.model=SM-A700F\nro.build.PDA=A700FDXXS1CSB1\n')
            with self.assertRaises(M.LayoutError):
                M.identity(prop)
            prop.write_text('ro.product.model=SM-A700FD\nro.build.PDA=A700FDXXU1BOLD\n')
            with self.assertRaises(M.LayoutError):
                M.identity(prop)


if __name__ == '__main__':
    unittest.main()
