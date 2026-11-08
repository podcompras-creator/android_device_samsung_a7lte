"""Targeted tests for the new metadata/range client; no device tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=module('fusmeta','query-samsung-fus.py')
r=module('fusrange','fetch-fus-stock-components.py')


class FUSMetadataTests(unittest.TestCase):
    def test_logic_published_vector(self):
        self.assertEqual(f.logic_check('0123456789abcdef','A0f'),'106')
    def test_auth_data_rejected_if_modified(self):
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            f.authenticate(b'0123456789abcdef',b'x'*100)
    def test_current_nonce_transform(self):
        blob=(ROOT/'tooling/fus-auth/auth_param.dat').read_bytes()
        signature=f.authenticate(b'0123456789abcdef',blob)
        self.assertRegex(signature,r'^[0-9a-f]{32}$')
        self.assertNotEqual(signature,f.authenticate(b'0123456789abcdeg',blob))
    def test_official_metadata_evidence(self):
        parsed=f.parse_response((ROOT/'logs/phase3-firmware/fus-query-20261108/02-NF_SmartDownloadBinaryInform.do.xml').read_bytes())
        self.assertEqual(parsed['results']['Status'],'S00')
        self.assertEqual(parsed['fields']['BINARY_SW_VERSION'],f.VERSION)
        self.assertEqual(parsed['fields']['BINARY_LOCAL_CODE'],'ZTO')
        self.assertEqual(parsed['fields']['BINARY_BYTE_SIZE'],'1935783696')
    def test_legacy_request_has_no_identifier(self):
        import xml.etree.ElementTree as E
        tree=E.fromstring(f.inform_body(f.VERSION,'0123456789abcdef',True))
        self.assertIn(tree.findtext('./FUSBody/Put/DEVICE_IMEI_PUSH/Data'),(None,''))
        self.assertEqual(tree.findtext('./FUSBody/Put/DEVICE_PDA_CODE1_VERSION/Data'),'A700FDXXS1CSB1')
    def test_range_decryption_and_seek(self):
        import hashlib
        class Response:
            status=206
            def __init__(self,data):self.data=data;self.headers={'Content-Range':'bytes 0-31/32'}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return self.data[:n]
        class Opener:
            def open(self,req,timeout):return Response(encrypted)
        class Client:
            nonce='';signature='';opener=Opener()
        fields={'BINARY_BYTE_SIZE':'32','MODEL_PATH':'/neofus/9/','BINARY_NAME':'SM-A700FD_1_20190319093540_yipiin0bmb_fac.zip.enc4','LOGIC_VALUE_FACTORY':'0123456789abcdef'}
        key=hashlib.md5(f.logic_check(f.VERSION,fields['LOGIC_VALUE_FACTORY']).encode()).hexdigest()
        plain=bytes(range(32))
        encrypted=subprocess.run(['openssl','enc','-e','-aes-128-ecb','-K',key,'-nopad'],input=plain,stdout=subprocess.PIPE,check=True).stdout
        stream=r.RangedZIP(Client(),fields,32)
        stream.seek(5);self.assertEqual(stream.read(4),plain[5:9])
        stream.seek(-2,2);self.assertEqual(stream.read(),plain[-2:])
        self.assertEqual(stream.used,32)
        denied=r.RangedZIP(Client(),fields,31)
        with self.assertRaisesRegex(ValueError,'budget'):denied.read(1)


    def test_range_reauthorizes_once_on_expired_session(self):
        import io, urllib.error, hashlib
        plain=b'0123456789abcdef'*2
        fields={'BINARY_BYTE_SIZE':'32','MODEL_PATH':'/neofus/9/','BINARY_NAME':'SM-A700FD_1_20190319093540_yipiin0bmb_fac.zip.enc4','LOGIC_VALUE_FACTORY':'0123456789abcdef','DEVICE_MODEL_TYPE':'9'}
        key=hashlib.md5(f.logic_check(f.VERSION,fields['LOGIC_VALUE_FACTORY']).encode()).hexdigest()
        encrypted=subprocess.run(['openssl','enc','-e','-aes-128-ecb','-K',key,'-nopad'],input=plain,stdout=subprocess.PIPE,check=True).stdout
        class Response:
            status=206;headers={'Content-Range':'bytes 0-31/32'}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return encrypted[:n]
        class Opener:
            calls=0
            def open(self,req,timeout):
                self.calls+=1
                if self.calls==1:raise urllib.error.HTTPError(req.full_url,401,'expired',{},io.BytesIO())
                return Response()
        class Client:
            nonce='0123456789abcdef';signature='';opener=Opener();queries=0;inits=0
            def query(self,legacy):
                self.queries+=1;return {'results':{'Status':'S00'},'fields':fields}
            def post(self,endpoint,payload,legacy):
                self.inits+=1;return {'results':{'Status':'S00'}}
        client=Client();stream=r.RangedZIP(client,fields,32)
        self.assertEqual(stream.read(32),plain)
        self.assertEqual((client.queries,client.inits,client.opener.calls),(1,1,2))


if __name__=='__main__':unittest.main()
