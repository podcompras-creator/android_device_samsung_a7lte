#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Authentication transform ported from Bifrost/SamloaderKotlin CryptUtils.kt,
# Copyright (c) 2021 Zachary Wander. See tooling/fus-auth/LICENSE.txt.
"""Read-only Samsung FUS firmware availability query. No download init or device IDs."""
import argparse, datetime, hashlib, http.cookiejar, json, struct, sys
import urllib.error, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://neofussvr.sslcs.cdngc.net/'
VERSION = 'A700FDXXS1CSB1/A700FDZTO1CSB1/A700FDXXU1CPF1/A700FDXXS1CSB1'
AUTH_SHA256 = '6f969176bbe3eca193b51509313ca45d32366cf1825a907f04fde5b64d3f35b4'
SHIFT = (0,5,10,15,4,9,14,3,8,13,2,7,12,1,6,11)


def authenticate(seed, blob):
    if len(seed) != 16 or len(blob) < 56:
        raise ValueError('Auth requires a 16-byte nonce seed and valid parameter data')
    if hashlib.sha256(blob).hexdigest() != AUTH_SHA256:
        raise ValueError('Auth parameter SHA-256 mismatch')
    header = struct.unpack_from('<14I', blob)
    table = blob[56:]
    block = [0] * 320
    block[:16] = seed
    state = [0] * 64
    final = header[3]
    for row in range(9):
        start = row * 32
        for idx in range(16): block[start+16+idx] = block[start+SHIFT[idx]]
        for group in range(4):
            g4, g16 = group*4, group*16
            base = final+header[5]+header[11]+6144*(group+row*4)
            for k in range(4):
                blk = row*16+g4+k
                pos = blk*4096+block[start+16+g4+k]*16
                source = table[pos:pos+16]
                at = final+header[5]+blk*32
                selector = table[at:at+32]
                if len(source)!=16 or len(selector)!=32: raise ValueError('Auth data bounds')
                for output in range(4):
                    accumulator=0
                    for bit in range(8):
                        value=selector[output*8+bit]
                        index=(value>>3)&31
                        b=source[index] if index<16 else 0
                        accumulator |= ((b>>(7-(value&7)))&1)<<(7-bit)
                    state[g16+k*4+output]=accumulator
            for k in range(4):
                a,b,c,d=(state[g16+k+x] for x in (0,4,8,12))
                t=table[base+1536*k:base+1536*(k+1)]
                if len(t)!=1536: raise ValueError('Auth lookup bounds')
                left=(16*t[(a&0xf0)|(b>>4)]^t[256+((a&15)<<4|(b&15))])&255
                right=(16*t[512+((c&0xf0)|(d>>4))]^t[768+((c&15)<<4|(d&15))])&255
                block[(row+1)*32+g4+k]=(16*t[1024+((left&0xf0)|(right>>4))]^t[1280+((left&15)<<4|(right&15))])&255
    return bytes(table[final+i*256+block[288+SHIFT[i]]] for i in range(16)).hex()


def logic_check(version, nonce):
    if len(version)<16: raise ValueError('Version too short for logic check')
    return ''.join(version[ord(c)&15] for c in nonce)


def inform_body(version, nonce, legacy):
    parts=version.split('/')
    if len(parts)!=4: raise ValueError('Expected AP/CSC/CP/DATA version')
    message=ET.Element('FUSMsg');head=ET.SubElement(message,'FUSHdr')
    for name,value in [('ProtoVer','1.0' if legacy else '1'),('SessionID','0'),('MsgID','1')]:ET.SubElement(head,name).text=value
    body=ET.SubElement(message,'FUSBody');put=ET.SubElement(body,'Put')
    fields={'ACCESS_MODE':'2' if legacy else '1','BINARY_NATURE':'1','LOGIC_CHECK':logic_check(version,nonce),'CLIENT_LANGUAGE':'1033'}
    if legacy:
        fields.update(CLIENT_PRODUCT='Smart Switch',CLIENT_VERSION='4.3.23123_1',DEVICE_IMEI_PUSH='',DEVICE_FW_VERSION=version,DEVICE_LOCAL_CODE='ZTO',DEVICE_AID_CODE='ZTO',DEVICE_MODEL_NAME='SM-A700FD',DEVICE_CONTENTS_DATA_VERSION=parts[3],DEVICE_CSC_CODE2_VERSION=parts[1],DEVICE_PDA_CODE1_VERSION=parts[0],DEVICE_PHONE_FONT_VERSION=parts[2])
    else:
        ET.SubElement(put,'CmdID').text='1'
        fields.update(REQUEST_TYPE='2',BINARY_SW_VERSION=version,DEVICE_SN_NUMBER='',BINARY_LOCAL_CODE='ZTO',BINARY_MODEL_NAME='SM-A700FD')
    for name,value in fields.items():ET.SubElement(ET.SubElement(put,name),'Data').text=value
    get=ET.SubElement(body,'Get');ET.SubElement(get,'CmdID').text='2';ET.SubElement(get,'LATEST_FW_VERSION' if legacy else 'BINARY_SW_VERSION')
    return ET.tostring(message,encoding='utf-8',xml_declaration=True)


def parse_response(data):
    root=ET.fromstring(data)
    def group(path):
        parent=root.find(path)
        return {} if parent is None else {child.tag:(child.findtext('Data') if child.find('Data') is not None else (child.text or '')) for child in parent}
    return {'fields':group('./FUSBody/Put'),'results':group('./FUSBody/Results')}


class FUS:
    def __init__(self, auth_data, output):
        self.blob=auth_data;self.output=output;self.nonce='';self.signature='';self.sequence=0
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.events=[]
    def post(self, endpoint, payload, legacy):
        # Standard published FUS challenge/response; no identifier supplied or fabricated.
        header=f'FUS nonce="{self.nonce}", signature="{self.signature}", nc="", type="", realm=""'
        req=urllib.request.Request(BASE+endpoint,data=payload,headers={'Authorization':header,'User-Agent':'Kiss2.0_FUS' if legacy else 'SMART 2.0'},method='POST')
        try:response=self.opener.open(req,timeout=30)
        except urllib.error.HTTPError as exc:response=exc
        with response:
            raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise ValueError('FUS metadata exceeds limit')
            seed=response.headers.get('NONCE','')
            if seed:
                self.nonce=seed[:16] if legacy else seed
                self.signature=authenticate(seed[:16].encode('ascii'),self.blob)
            self.sequence+=1
            path=self.output/f'{self.sequence:02d}-{endpoint}.xml'
            path.write_bytes(raw)
            event={'endpoint':BASE+endpoint,'http_status':response.status,'body_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'nonce_header_length':len(seed),'nonce_seed_bytes':16 if seed else 0,'response_file':path.name}
            self.events.append(event)
            if response.status!=200:raise ValueError(f'HTTP {response.status} from {endpoint}')
            return parse_response(raw)
    def query(self, legacy):
        self.nonce='';self.signature=''
        prefix='NF_Download' if legacy else 'NF_SmartDownload'
        self.post(prefix+'GenerateNonce.do',b'',legacy)
        return self.post(prefix+'BinaryInform.do',inform_body(VERSION,self.nonce,legacy),legacy)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    report={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model':'SM-A700FD','region':'ZTO','version':VERSION,'scope':'metadata only; no download initialization, no device identifiers','auth_source':'Bifrost MIT ed73a034d3b27d84c68b2c21622a9de6618455de','auth_parameter_sha256':AUTH_SHA256}
    client=FUS((ROOT/'tooling/fus-auth/auth_param.dat').read_bytes(),a.output)
    for label,legacy in [('modern',False),('legacy',True)]:
        try:report[label]=client.query(legacy)
        except (OSError,ValueError,ET.ParseError) as exc:report[label]={'error':str(exc)}
    modern=report.get('modern',{})
    report['availability_confirmed']=(modern.get('results',{}).get('Status') in ('S00','200') and modern.get('fields',{}).get('BINARY_SW_VERSION')==VERSION and modern.get('fields',{}).get('BINARY_MODEL_NAME')=='SM-A700FD' and modern.get('fields',{}).get('BINARY_LOCAL_CODE')=='ZTO')
    report['http_events']=client.events
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['availability_confirmed'] else 1


if __name__=='__main__':raise SystemExit(main())
