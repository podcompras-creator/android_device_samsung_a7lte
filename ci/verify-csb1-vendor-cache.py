#!/usr/bin/env python3
"""Check cached vendor bytes/recipes, without claiming legacy ABI compatibility."""
import argparse,hashlib,json
from pathlib import Path,PurePosixPath

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def validate(vendor,contract):
 vendor=vendor.resolve(strict=True);r=json.loads((vendor/'vendor-audit.json').read_text())
 if r.get('schema_version')!=2 or r.get('model')!='SM-A700FD' or r.get('firmware')!='A700FDXXS1CSB1':raise ValueError('cache identity/schema mismatch')
 for name,expected in [('vendor-review.json',r['review_plan_sha256']),('stock-inventory.json',r['inventory_sha256'])]:
  if sha(vendor/name)!=expected:raise ValueError('cache metadata changed: '+name)
 if sha(contract)!=r['native_contract_sha256']:raise ValueError('source contract changed')
 if set(r['generated_makefiles'])!={'Android.mk','a7lte-vendor.mk','BoardConfigVendor.mk'}:raise ValueError('incomplete recipe inventory')
 for name,expected in r['generated_makefiles'].items():
  if sha(vendor/name)!=expected:raise ValueError('cache recipe changed: '+name)
 inv=json.loads((vendor/'stock-inventory.json').read_text());plan=json.loads((vendor/'vendor-review.json').read_text());rows={x['source']:x for x in inv['files']};count=0
 for item in plan['files']:
  if item['action']=='skip':continue
  rel=PurePosixPath(item['source'])
  if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe cache source path')
  p=vendor/'proprietary'/rel
  if not p.resolve(strict=True).is_relative_to(vendor) or sha(p)!=rows[item['source']]['sha256']:raise ValueError('cache blob changed: '+str(rel))
  count+=1
 if count!=r['selected_files'] or count==0:raise ValueError('cache selection mismatch')
 return count

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vendor',type=Path,required=True);a=p.parse_args()
 try:count=validate(a.vendor,Path(__file__).resolve().parents[1]/'scripts/native-contracts.json')
 except (OSError,ValueError,KeyError) as e:p.exit(2,f'Cache validation failed: {e}\n')
 print(f'PASS: {count} cached CSB1 files and generated recipes match recorded hashes; ABI/device unverified')
if __name__=='__main__':main()
