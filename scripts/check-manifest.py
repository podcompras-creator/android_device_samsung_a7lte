#!/usr/bin/env python3
"""Validate real repo-expanded dependencies, not a hand-merged XML approximation."""
import argparse, json, xml.etree.ElementTree as E
p=argparse.ArgumentParser(); p.add_argument('manifest'); a=p.parse_args()
r=E.parse(a.manifest).getroot(); paths={}
for x in r.findall('project'):
    path=x.get('path',x.get('name'))
    if path in paths: raise SystemExit('Duplicate project path: '+path)
    paths[path]=x.attrib
required={
 'device/samsung/msm8916-common':'Galaxy-MSM8916/android_device_samsung_msm8916-common',
 'device/samsung/qcom-common':'LineageOS/android_device_samsung_qcom-common',
 'kernel/samsung/msm8916':'Galaxy-MSM8916/android_kernel_samsung_msm8916',
 'hardware/samsung':'LineageOS/android_hardware_samsung',
 'hardware/qcom/audio-caf/msm8916':'Galaxy-MSM8916/android_hardware_qcom_audio',
 'hardware/qcom/display-caf/msm8916':'LineageOS/android_hardware_qcom_display',
 'hardware/qcom/media-caf/msm8916':'LineageOS/android_hardware_qcom_media',
 'device/qcom/sepolicy-legacy':'LineageOS/android_device_qcom_sepolicy-legacy',
 'vendor/lineage':'LineageOS/android_vendor_lineage',
 'prebuilts/gcc/linux-x86/arm/arm-eabi-7.2':'Galaxy-MSM8916/android-prebuilts-gcc-linux-x86-arm-arm-eabi-7.2',
 'external/sony/boringssl-compat':'LineageOS/android_external_sony_boringssl-compat',
 'packages/resources/devicesettings':'LineageOS/android_packages_resources_devicesettings',
}
for path,name in required.items():
    assert path in paths, 'Missing dependency: '+path
    assert paths[path]['name']==name, (path, paths[path])
assert not any('oppo' in (path+' '+x['name']).lower() for path,x in paths.items()), 'Unexpected OPPO device dependency'
print(json.dumps({'result':'PASS','projects':len(paths),'required_dependencies':{p:paths[p] for p in required}},indent=2))
