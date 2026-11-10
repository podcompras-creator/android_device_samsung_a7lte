#!/usr/bin/env python3
"""Read-only verification of a real delivered ROM artifact in bounded RAM.

Read authorized download URL and GitHub artifact metadata as JSON on stdin.
Only writes an evidence report; never creates, edits or flashes a ROM image.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LIMIT=1024**3

def main():
 c=json.load(sys.stdin);size=int(c['artifact_bytes'])
 expected=c['artifact_sha256'].removeprefix('sha256:')
 if not 0<size<=LIMIT or not re.fullmatch('[a-f0-9]{64}',expected):
  raise ValueError('Invalid expected artifact size/digest')
 blob=io.BytesIO();h=hashlib.sha256();total=0
 with urllib.request.urlopen(c['download_url'],timeout=60) as r:
  while True:
   block=r.read(1024*1024)
   if not block:break
   total+=len(block)
   if total>size:raise ValueError('Download exceeds exact artifact size')
   h.update(block);blob.write(block)
 if total!=size or h.hexdigest()!=expected:raise ValueError('Artifact SHA256/size mismatch')
 blob.seek(0)
 with zipfile.ZipFile(blob) as outer:
  if outer.testzip() is not None:raise ValueError('Outer artifact CRC failure')
  names=outer.namelist()
  if len(names)!=len(set(names)):raise ValueError('Duplicate artifact entries')
  candidates=[n for n in names if Path(n).name==c['rom_name']]
  if len(candidates)!=1:raise ValueError('Expected exactly one generated ROM ZIP')
  info=outer.getinfo(candidates[0])
  if not 0<info.file_size<=LIMIT:raise ValueError('Inner ROM exceeds RAM inspection bound')
  rom=io.BytesIO();h=hashlib.sha256()
  with outer.open(info) as r:
   while True:
    block=r.read(1024*1024)
    if not block:break
    rom.write(block);h.update(block)
  if h.hexdigest()!=c['rom_sha256']:raise ValueError('ROM differs from original native build hash')
  spec=importlib.util.spec_from_file_location('built',ROOT/'ci/validate-built-artifacts.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  rom.seek(0);validation=module.validate_ota_zip(rom)
  report={'result':validation['result'],'scope':'Independent full delivered artifact and original generated ROM SHA256/CRC plus existing static Samsung OTA validator; no signature or hardware test','artifact_id':c['artifact_id'],'artifact_sha256':expected,'artifact_bytes':total,'rom_name':c['rom_name'],'rom_sha256':h.hexdigest(),'rom_bytes':info.file_size,'rom_stored_on_disk':False,'device_tested':False,'flash_ready':False,'validation':validation}
  (ROOT/'logs/build-launch/actions-run8-delivered-rom-verification.json').write_text(json.dumps(report,indent=2)+'\n')
  with zipfile.ZipFile(rom) as archive:
   updater=archive.read('META-INF/com/google/android/updater-script').decode()
   (ROOT/'logs/build-launch/actions-run8-updater-script.txt').write_text(updater)
  print(json.dumps({k:v for k,v in report.items() if k!='validation'},indent=2))
 return 0 if report['result']=='PASS' else 2

if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as error:
  message=re.sub(r'(https?://[^\s?]+)\?[^\s]+',r'\1?<redacted>',str(error))
  print(json.dumps({'result':'FAIL','scope':'Delivered artifact verification','error':message}));raise SystemExit(2)
