#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Obtain selected stock headers/images by authorized Samsung FUS ranges.
Uses the metadata client and MIT Bifrost auth. Caps transfers, never flashes,
never invents identifiers, and never downloads the full SYSTEM payload.
"""
import argparse, collections, hashlib, importlib.util, io, json, struct, subprocess, sys, tarfile, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a7fus',ROOT/'scripts/query-samsung-fus.py')
fus=importlib.util.module_from_spec(spec);spec.loader.exec_module(fus)


def init_body(fields,nonce):
    import xml.etree.ElementTree as E
    name=fields['BINARY_NAME'];msg=E.Element('FUSMsg');head=E.SubElement(msg,'FUSHdr')
    for k,v in [('ProtoVer','1'),('SessionID','0'),('MsgID','1')]:E.SubElement(head,k).text=v
    put=E.SubElement(E.SubElement(msg,'FUSBody'),'Put')
    for k,v in dict(BINARY_NAME=name,BINARY_SW_VERSION=fus.VERSION,DEVICE_LOCAL_CODE='ZTO',DEVICE_MODEL_TYPE=fields['DEVICE_MODEL_TYPE'],LOGIC_CHECK=fus.logic_check(name[-25:-9],nonce)).items():E.SubElement(E.SubElement(put,k),'Data').text=v
    return E.tostring(msg,encoding='utf-8',xml_declaration=True)


class RangedZIP(io.RawIOBase):
    def __init__(self,client,fields,budget):
        self.client=client;self.fields=fields;self.pos=0;self.length=int(fields['BINARY_BYTE_SIZE']);self.budget=budget;self.used=0;self.cache=collections.OrderedDict();self.events=[]
        self.url='https://cloud-neofussvr.samsungmobile.com/NF_SmartDownloadBinaryForMass.do?file='+urllib.parse.quote(fields['MODEL_PATH']+fields['BINARY_NAME'])
        logic=fields['LOGIC_VALUE_FACTORY' if '_fac.' in fields['BINARY_NAME'] else 'LOGIC_VALUE_HOME']
        self.key=hashlib.md5(fus.logic_check(fus.VERSION,logic).encode()).hexdigest()
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        value=offset if whence==0 else self.pos+offset if whence==1 else self.length+offset
        if value<0:raise ValueError('Negative seek')
        self.pos=value;return self.pos
    def _chunk(self,index):
        if index in self.cache:
            self.cache.move_to_end(index);return self.cache[index]
        start=index*1024**2;end=min(start+1024**2,self.length)-1;expected=end-start+1
        if self.used+expected>self.budget:raise ValueError('FUS range transfer budget reached')
        c=self.client
        for attempt in range(2):
            header=f'FUS nonce="{c.nonce}", signature="{c.signature}", nc="", type="", realm=""'
            request=urllib.request.Request(self.url,headers={'Authorization':header,'User-Agent':'SMART 2.0','Range':f'bytes={start}-{end}'})
            try:
                response=c.opener.open(request,timeout=45)
                break
            except urllib.error.HTTPError as exc:
                if exc.code!=401 or attempt:raise
                exc.close()
                # Renew normal FUS authorization once; never substitute identifiers.
                renewed=c.query(False)
                if renewed['results'].get('Status') not in ('S00','200') or renewed['fields'].get('BINARY_NAME')!=self.fields['BINARY_NAME'] or renewed['fields'].get('BINARY_BYTE_SIZE')!=self.fields['BINARY_BYTE_SIZE']:
                    raise ValueError('FUS renewal did not confirm the identical package')
                initialized=c.post('NF_SmartDownloadBinaryInitForMass.do',init_body(renewed['fields'],c.nonce),False)
                if initialized['results'].get('Status') not in ('S00','200'):
                    raise ValueError('FUS renewal did not authorize download')
        with response as r:
            expected_range=f'bytes {start}-{end}/{self.length}'
            if r.status!=206 or r.headers.get('Content-Range')!=expected_range:raise ValueError('Server did not honor exact bounded Range')
            raw=r.read(expected+1)
            if len(raw)!=expected or len(raw)%16:raise ValueError('Invalid encrypted range size')
            self.used+=len(raw)
            data=subprocess.run(['openssl','enc','-d','-aes-128-ecb','-K',self.key,'-nopad'],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
            self.events.append({'url':self.url,'http_status':r.status,'content_range':expected_range,'encrypted_bytes':len(raw),'encrypted_sha256':hashlib.sha256(raw).hexdigest(),'decrypted_sha256':hashlib.sha256(data).hexdigest()})
            self.cache[index]=data
            while len(self.cache)>8:self.cache.popitem(last=False)
            return data
    def read(self,n=-1):
        if n<0:n=self.length-self.pos
        n=min(n,self.length-self.pos)
        if n<=0:return b''
        if n>4*1024**2:raise ValueError('Unexpected large random read')
        out=[]
        while n:
            data=self._chunk(self.pos//1024**2);within=self.pos%1024**2;part=data[within:within+n]
            if not part:raise ValueError('Short range read')
            out.append(part);self.pos+=len(part);n-=len(part)
        return b''.join(out)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-download-mib',type=int,default=150);p.add_argument('--max-component-mib',type=int,default=32);a=p.parse_args()
    if not 1<=a.max_download_mib<=150:p.error('Transfer cap must be1..150MiB')
    a.output.mkdir(parents=True,exist_ok=False)
    c=fus.FUS((ROOT/'tooling/fus-auth/auth_param.dat').read_bytes(),a.output)
    report={'scope':'partial official archive via authenticated bounded HTTPS Range; full archive CRC is not verified','requested_version':fus.VERSION,'components':[]}
    stream=None
    try:
        metadata=c.query(False);report['metadata']=metadata;fields=metadata['fields']
        if metadata['results'].get('Status') not in ('S00','200'):raise ValueError('Official metadata did not approve firmware')
        if fields['BINARY_SW_VERSION']!=fus.VERSION or fields['BINARY_MODEL_NAME']!='SM-A700FD' or fields['BINARY_LOCAL_CODE']!='ZTO':raise ValueError('Firmware metadata identity mismatch')
        init=c.post('NF_SmartDownloadBinaryInitForMass.do',init_body(fields,c.nonce),False);report['initialization']=init
        if init['results'].get('Status') not in ('S00','200'):raise ValueError('FUS did not authorize binary download')
        stream=RangedZIP(c,fields,a.max_download_mib*1024**2)
        with zipfile.ZipFile(stream) as z:
            report['zip_members']=[{'name':x.filename,'bytes':x.file_size,'compressed_bytes':x.compress_size,'crc32':f'{x.CRC:08x}','method':x.compress_type,'offset':x.header_offset} for x in z.infolist()]
            selected=[x for x in z.infolist() if x.filename.startswith(('AP_','CSC_')) and x.filename.endswith('.tar.md5')]
            for archive in selected:
                try:
                    with z.open(archive) as compressed,tarfile.open(fileobj=compressed,mode='r|') as tar:
                        for member in tar:
                            name=Path(member.name).name
                            report.setdefault('tar_headers_seen',[]).append({'archive':archive.filename,'member':member.name,'bytes':member.size})
                            if name in ('boot.img','recovery.img') or name.lower().endswith('.pit'):
                                if not member.isfile() or member.size>a.max_component_mib*1024**2:raise ValueError('Unsafe/oversized selected stock component')
                                raw=tar.extractfile(member).read(member.size+1)
                                if len(raw)!=member.size:raise ValueError('Short component')
                                target=a.output/name
                                if target.exists():raise ValueError('Duplicate selected component')
                                target.write_bytes(raw);report['components'].append({'path':name,'archive':archive.filename,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'zip_entry_crc_verified':False,'identity_scope':'official FUS exact-version archive; partial streamed TAR, complete image bytes'})
                            elif member.size>32*1024**2:
                                report.setdefault('stopped_before',[]).append({'archive':archive.filename,'member':name,'reason':'preserve bounded transfers; large SYSTEM/CACHE not read'})
                                break
                except (ValueError,tarfile.TarError,zipfile.BadZipFile) as exc:
                    report.setdefault('archive_errors',[]).append({'archive':archive.filename,'error':str(exc)})
        return 0
    except (OSError,ValueError,subprocess.CalledProcessError,zipfile.BadZipFile) as exc:
        report['error']=str(exc);return 1
    finally:
        report['http_events']=c.events
        if stream is not None:report['range_transfers']=stream.events;report['range_bytes']=stream.used
        (a.output/'components-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':raise SystemExit(main())
