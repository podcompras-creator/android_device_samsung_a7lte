#!/usr/bin/env python3
"""Reproduce the audited Samsung a7lte Pie overlay from pinned upstream trees.

Authoritative a7lte overrides are in templates/device/a7lte. Proprietary inventory
and verified partition sizes are intentionally left untouched if already present.
"""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--android-root', type=Path, default=ROOT/'android')
a = p.parse_args()
src = ROOT/'sources/a7lte'
common_src = ROOT/'sources/common'
if not (src/'device.mk').is_file() or not (common_src/'BoardConfigCommon.mk').is_file():
    p.error('pinned sources/a7lte and sources/common checkouts are required')
d = a.android_root.resolve()/'device/samsung/a7lte'
common = d.parent/'msm8916-common'
shutil.copytree(src, d, ignore=shutil.ignore_patterns('.git', 'patches', 'camera', 'overlay'), dirs_exist_ok=True)
for name in ['cm.mk', 'vendorsetup.sh']:
    (d/name).unlink(missing_ok=True)
# Remove only superseded generated paths, never private/generated blob inventory.
for name in ['camera', 'overlay/frameworks']:
    if (d/name).is_dir():
        shutil.rmtree(d/name)
shutil.copytree(ROOT/'templates/device/a7lte', d, dirs_exist_ok=True)
shutil.copytree(common_src, common, ignore=shutil.ignore_patterns('.git'), dirs_exist_ok=True)

# Make common ramdisk modules consume this device's fstab without defining a
# second module or installing two different sources to the same destination.
p = common/'rootdir/Android.mk'
s = p.read_text()
for module, old, variable in [
        ('fstab.qcom', 'etc/$(LOCAL_MODULE)', 'TARGET_DEVICE_FSTAB'),
        ('twrp.fstab', '../recovery/$(LOCAL_MODULE)', 'TARGET_DEVICE_TWRP_FSTAB')]:
    marker = f'LOCAL_MODULE       := {module}\n'
    start = s.index(marker)
    stop = s.index('include $(BUILD_PREBUILT)', start)
    stanza = s[start:stop]
    oldline = f'LOCAL_SRC_FILES    := {old}'
    assert stanza.count(oldline) == 1
    stanza = stanza.replace(oldline, f'''ifneq ($({variable}),)
LOCAL_SRC_FILES    := ../../../../$({variable})
else
{oldline}
endif''')
    s = s[:start] + stanza + s[stop:]
p.write_text(s)

# Expose the existing property_override helper to the device extension and fix
# upstream's transposed vendor model/device properties.
p = common/'include/init_msm8916.h'
s = p.read_text().replace('void init_target_properties();', 'void init_target_properties();\nvoid property_override(char const prop[], char const value[]);')
p.write_text(s)
p = common/'init/init_msm8916.cpp'
s = p.read_text().replace('"ro.product.device", "ro.product.vendor.model", device', '"ro.product.device", "ro.product.vendor.device", device').replace('"ro.product.model", "ro.product.vendor.device", model', '"ro.product.model", "ro.product.vendor.model", model')
p.write_text(s)

# A7 calibration replaces common NV, while common cfg/ini files are retained.
p = common/'msm8916.mk'
s = p.read_text()
line = '    $(LOCAL_PATH)/configs/wifi/WCNSS_qcom_wlan_nv.bin:$(TARGET_COPY_OUT_SYSTEM)/etc/firmware/wlan/prima/WCNSS_qcom_wlan_nv.bin'
assert s.count(line) == 1
s = s.replace('    $(LOCAL_PATH)/configs/wifi/WCNSS_qcom_cfg.ini:$(TARGET_COPY_OUT_SYSTEM)/etc/firmware/wlan/prima/WCNSS_qcom_cfg.ini \\\n' + line, '''    $(LOCAL_PATH)/configs/wifi/WCNSS_qcom_cfg.ini:$(TARGET_COPY_OUT_SYSTEM)/etc/firmware/wlan/prima/WCNSS_qcom_cfg.ini
ifneq ($(TARGET_HAS_CUSTOM_WLAN_NV),true)
PRODUCT_COPY_FILES += \\\n''' + line + '\nendif')
# Use A7 keys in the two destinations already owned by the common product.
s = s.replace('# Keylayout\nPRODUCT_COPY_FILES', '# Keylayout\nMSM8916_KEYLAYOUT_PATH := $(if $(TARGET_DEVICE_KEYLAYOUT_PATH),$(TARGET_DEVICE_KEYLAYOUT_PATH),$(LOCAL_PATH)/keylayout)\nPRODUCT_COPY_FILES')
for name in ['sec_touchkey.kl', 'gpio-keys.kl']:
    s = s.replace('$(LOCAL_PATH)/keylayout/' + name + ':', '$(MSM8916_KEYLAYOUT_PATH)/' + name + ':')
# LineageOS 16 uses one audio service for core/effect/soundtrigger. The old
# standalone effect service name does not exist. LiveDisplay evolved to 2.0.
s = s.replace('    android.hardware.audio.effect@2.0-service \\\n', '')
s = s.replace('vendor.lineage.livedisplay@1.0-service-legacymm', 'vendor.lineage.livedisplay@2.0-service-legacymm')
# This SM-A700FD is GSM/WCDMA/LTE, not one of the common CDMA variants.
s = '\n'.join(line for line in s.splitlines() if 'android.hardware.telephony.cdma.xml:' not in line) + '\n'
p.write_text(s)
print(f'Prepared Samsung a7lte and common overlay in {a.android_root.resolve()}')
