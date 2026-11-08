"""New regression coverage for offset44 OS-version handling; synthetic fixture."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('stock_layout_os',Path(__file__).resolve().parents[1]/'scripts/verify-stock-layout.py')
validator=importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)


def fixture():
    version=(9 << 14)  # 9.0.0
    patch=((2019-2000) << 4) | 2
    header=b'ANDROID!'+struct.pack('<10I',4,0x80008000,4,0x82000000,0,0x80f00000,0x81e00000,2048,16,(version << 11)|patch)
    header=header.ljust(2048,b'\0')
    return header+b'KERN'+bytes(2044)+b'RAMD'+bytes(2044)+b'QCDT'+bytes(2044)


class BootOSVersionTests(unittest.TestCase):
    def test_nonzero_pie_os_word_with_legacy_dt(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'synthetic.img'; image.write_bytes(fixture())
            result=validator.parse_boot(image,16384)
            self.assertEqual(result['os_version'],'9.0.0')
            self.assertEqual(result['os_patch_level'],'2019-02')
            self.assertEqual(result['format'],'legacy-samsung-dt')

    def test_modern_header_version_is_not_dt_size(self):
        with tempfile.TemporaryDirectory() as d:
            image=Path(d)/'synthetic.img'
            for version in (1,2):
                blob=bytearray(fixture()); struct.pack_into('<I',blob,40,version); image.write_bytes(blob)
                with self.assertRaisesRegex(validator.LayoutError,'not a supported'):
                    validator.parse_boot(image,16384)


if __name__=='__main__':
    unittest.main()
