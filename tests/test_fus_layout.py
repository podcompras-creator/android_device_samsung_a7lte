"""New signed-PIT / partial FUS-report coverage with synthetic fixture data."""
import hashlib,importlib.util,json,struct,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

layout=load('fus_layout_parser',ROOT/'scripts/verify-stock-layout.py')
fixtures=load('old_fixture_builders',ROOT/'tests/test_stock_layout.py')

class FUSLayoutTests(unittest.TestCase):
    def test_signed_pit_fill_to_end_requires_explicit_partial(self):
        blob=bytearray(fixtures.pit_fixture()[:28+6*132])
        # USERDATA is placed last in logical storage, independently of table order.
        struct.pack_into('<II',blob,28+3*132+20,100000,0)
        blob+=b'S'*256
        with self.assertRaises(layout.LayoutError): layout.parse_pit(blob,512)
        entries,sizes=layout.parse_pit(blob,512,allow_signature_tail=True,allow_userdata_fill=True)
        self.assertIsNone(sizes['userdata'])
        self.assertEqual(sizes['boot'],4194304)

    def test_fus_hashes_and_partial_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            pit=root/'stock.pit';blob=bytearray(fixtures.pit_fixture()[:28+6*132])
            struct.pack_into('<II',blob,28+3*132+20,100000,0);pit.write_bytes(blob+b'S'*256)
            boot=root/'boot.img';boot.write_bytes(fixtures.boot_fixture())
            recovery=root/'recovery.img';recovery.write_bytes(fixtures.boot_fixture())
            version='A700FDXXS1CSB1/A700FDZTO1CSB1/A700FDXXU1CPF1/A700FDXXS1CSB1'
            fields=dict(BINARY_SW_VERSION=version,BINARY_MODEL_NAME='SM-A700FD',BINARY_LOCAL_CODE='ZTO',
                        DEVICE_PDA_CODE1_FILE='AP_SYNTHETIC.tar.md5',DEVICE_CSC_FILE='CSC_SYNTHETIC.tar.md5')
            report=dict(requested_version=version,metadata=dict(fields=fields,results=dict(Status='S00')),
                        initialization=dict(results=dict(Status='S00')),components=[])
            for p in (pit,boot,recovery):
                report['components'].append(dict(path=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    archive=fields['DEVICE_CSC_FILE' if p==pit else 'DEVICE_PDA_CODE1_FILE']))
            record=root/'synthetic-fus.json';record.write_text(json.dumps(report))
            mk,result=layout.verify(pit,boot,recovery,None,512,root/'sizes.mk',fus_components=record,allow_partial=True)
            self.assertFalse(result['layout_verified'])
            self.assertTrue(result['ready_for_boot_recovery'])
            self.assertIn('BOARD_USERDATAIMAGE_PARTITION_SIZE :=\n',mk)
            self.assertFalse(result['pit_trailer']['samsung_signature_verified'])
            boot.write_bytes(b'changed')
            with self.assertRaisesRegex(layout.LayoutError,'hash/size'):
                layout.fus_identity(record,dict(pit=pit,boot=boot,recovery=recovery))

if __name__=='__main__': unittest.main()
