#!/usr/bin/env python3
"""Check a7lte source-level HAL/module/manifest contracts; not a full Soong/VINTF build."""
import argparse, hashlib, json, re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--android-root',type=Path,default=ROOT/'android')
p.add_argument('--output',type=Path,default=ROOT/'logs/phase3-hal-contracts.json')
a=p.parse_args(); android=a.android_root.resolve(); errors=[]

def packages(text):
    logical=re.sub(r'\\\n', ' ', text)
    return set(token for line in logical.splitlines() if re.match(r'\s*PRODUCT_PACKAGES\s*\+=',line)
               for token in line.split('+=',1)[1].split() if not token.startswith('#'))

common=android/'device/samsung/msm8916-common'
dev=android/'device/samsung/a7lte'
pkgs=packages((common/'msm8916.mk').read_text()) | packages((dev/'device.mk').read_text())
modules={}; proofs=json.loads((ROOT/'logs/phase3-hal-sources.json').read_text()); verified=0
for x in proofs:
    if 'local' not in x: continue
    file=ROOT/x['local']
    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=x['sha256']:
        errors.append('source hash mismatch: '+x['local']); continue
    verified+=1
    if file.name in ('Android.mk','Android.bp'):
        text=file.read_text()
        names=re.findall(r'(?:LOCAL_MODULE|LOCAL_PACKAGE_NAME)\s*:?=\s*([^\s#]+)',text)
        names+=re.findall(r'\bname:\s*"([^"]+)"',text)
        for name in names: modules.setdefault(name,[]).append(x['local'])

# package -> manifest name, version, transport, required interfaces/instances.
contracts=[
 ('android.hardware.audio@2.0-service','audio','2.0','hwbinder',{'IDevicesFactory':['default']}),
 ('android.hardware.audio.effect@2.0-impl','audio.effect','2.0','hwbinder',{'IEffectsFactory':['default']}),
 ('android.hardware.soundtrigger@2.0-impl','soundtrigger','2.0','hwbinder',{'ISoundTriggerHw':['default']}),
 ('android.hardware.bluetooth@1.0-service','bluetooth','1.0','hwbinder',{'IBluetoothHci':['default']}),
 ('android.hardware.wifi@1.0-service','wifi','1.2','hwbinder',{'IWifi':['default']}),
 ('hostapd','wifi.hostapd','1.0','hwbinder',{'IHostapd':['default']}),
 ('wpa_supplicant','wifi.supplicant','1.1','hwbinder',{'ISupplicant':['default']}),
 ('android.hardware.camera.provider@2.4-impl-legacy','camera.provider','2.4','passthrough',{'ICameraProvider':['legacy/0']}),
 ('android.hardware.graphics.allocator@2.0-service','graphics.allocator','2.0','hwbinder',{'IAllocator':['default']}),
 ('android.hardware.graphics.composer@2.1-impl','graphics.composer','2.1','passthrough',{'IComposer':['default']}),
 ('android.hardware.graphics.mapper@2.0-impl','graphics.mapper','2.0','passthrough',{'IMapper':['default']}),
 ('android.hardware.gnss@1.0-impl','gnss','1.0','passthrough',{'IGnss':['default']}),
 ('android.hardware.light@2.0-impl','light','2.0','passthrough',{'ILight':['default']}),
 ('android.hardware.sensors@1.0-impl','sensors','1.0','passthrough',{'ISensors':['default']}),
 ('android.hardware.vibrator@1.0-impl','vibrator','1.0','passthrough',{'IVibrator':['default']}),
 ('android.hardware.memtrack@1.0-impl','memtrack','1.0','passthrough',{'IMemtrack':['default']}),
 ('android.hardware.renderscript@1.0-impl','renderscript','1.0','passthrough',{'IDevice':['default']}),
 ('android.hardware.broadcastradio@1.0-impl','broadcastradio','1.0','passthrough',{'IBroadcastRadioFactory':['default']}),
 ('android.hardware.keymaster@3.0-impl','keymaster','3.0','passthrough',{'IKeymasterDevice':['default']}),
 ('android.hardware.drm@1.0-impl','drm','1.0','passthrough',{'ICryptoFactory':['default'],'IDrmFactory':['default']}),
 ('android.hardware.power@1.0-service','power','1.0','hwbinder',{'IPower':['default']}),
 ('android.hardware.usb@1.0-service.basic','usb','1.0','hwbinder',{'IUsb':['default']}),
 ('android.hardware.configstore@1.1-service','configstore','1.0','hwbinder',{'ISurfaceFlingerConfigs':['default']}),
 ('rild','radio','1.1','hwbinder',{'IRadio':['slot1','slot2']}),
 ('rild','radio.deprecated','1.0','hwbinder',{'IOemHook':['slot1','slot2']}),
 ('vendor.lineage.livedisplay@2.0-service-legacymm','vendor.lineage.livedisplay','2.0','hwbinder',{'IDisplayModes':['default'],'IPictureAdjustment':['default']})]
manifest=ET.parse(dev/'manifest.xml').getroot(); declarations={}
for h in manifest.findall('hal'):
    name=h.findtext('name'); version=h.findtext('version'); transport=h.find('transport')
    for i in h.findall('interface'):
        for inst in i.findall('instance'):
            key=(name,version,i.findtext('name'),inst.text)
            if key in declarations:errors.append('duplicate declaration: '+str(key))
            declarations[key]=(transport.text,transport.get('arch'))
rows=[]
for package,name,version,transport,interfaces in contracts:
    if not name.startswith('vendor.'):name='android.hardware.'+name
    if package not in pkgs: errors.append('missing PRODUCT_PACKAGES: '+package)
    if package not in modules:errors.append('missing fetched module definition: '+package)
    for iface,instances in interfaces.items():
        for instance in instances:
            key=(name,version,iface,instance)
            if key not in declarations:errors.append('missing manifest declaration: '+str(key))
            elif declarations[key]!=(transport,'32' if transport=='passthrough' else None):
                errors.append('transport mismatch: '+str(key))
    rows.append(dict(module=package,hal=name,version=version,transport=transport,interfaces=interfaces,source_definitions=modules.get(package,[])))
for forbidden in ['android.hardware.audio.effect@2.0-service','vendor.lineage.livedisplay@1.0-service-legacymm']:
    if forbidden in pkgs: errors.append('obsolete/unprovided module selected: '+forbidden)
for unprovided in ['android.hardware.nfc','android.hardware.ir']:
    if any(k[0]==unprovided for k in declarations):errors.append('unprovided default HAL advertised: '+unprovided)
if 'DEVICE_MANIFEST_FILE := $(A7LTE_PATH)/manifest.xml' not in (dev/'device.mk').read_text():errors.append('device manifest is not selected by product')
# Actual default paths selected by the source wrappers, separate from ABI proof.
wrappers=[]
for kind in ['camera','sensors']:
    paths=list((common/('camera' if kind=='camera' else 'sensors_wrapper')).glob('*.[cC]*'))
    matches=[str(x.relative_to(android)) for x in paths if 'hw_get_module_by_class("'+kind+'", "vendor"' in x.read_text(errors='replace')]
    if not matches:errors.append('missing native wrapper lookup: '+kind)
    wrappers.append(dict(kind=kind,source=matches,required_stock_name=kind+'.vendor.msm8916.so',abi_validated=False))
report=dict(result='PASS' if not errors else 'FAIL',scope='Source-level module/manifest/wrapper contracts only; not full build, VINTF compatibility test, linker validation or device boot',verified_source_files=verified,contracts=rows,wrappers=wrappers,errors=errors,unresolved=['CSB1 proprietary ELF symbols/ABI and service runtime','NFC PN547 stock tuning/configuration/firmware; not advertised by default','ANT source path is vfs-prerelease /dev/smd5,/dev/smd6, hardware transport untested','RIL two-process Samsung callback/service registration ABI; diagnostic profile keeps it disabled'])
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n'); print(report['result'],len(rows),'HAL contracts;',verified,'hash-verified source files;',len(errors),'errors')
for error in errors:print(error)
raise SystemExit(bool(errors))
