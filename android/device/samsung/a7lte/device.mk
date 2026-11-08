TARGET_HAS_CUSTOM_WLAN_NV := true
TARGET_DEVICE_KEYLAYOUT_PATH := device/samsung/a7lte/keylayout
$(call inherit-product, device/samsung/msm8916-common/msm8916.mk)
#
# Copyright (C) 2015 The CyanogenMod Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

A7LTE_PATH := device/samsung/a7lte

# Overlay
DEVICE_PACKAGE_OVERLAYS := $(A7LTE_PATH)/overlay $(DEVICE_PACKAGE_OVERLAYS)

# Proprietary files
$(call inherit-product, vendor/samsung/a7lte/a7lte-vendor.mk)

# Device uses high-density artwork where available
PRODUCT_AAPT_CONFIG := normal
PRODUCT_AAPT_PREF_CONFIG := xxhdpi

# Boot animation
TARGET_SCREEN_HEIGHT := 1920
TARGET_SCREEN_WIDTH := 1080

# Permissions
PRODUCT_COPY_FILES += \
    external/ant-wireless/antradio-library/com.dsi.ant.antradio_library.xml:system/etc/permissions/com.dsi.ant.antradio_library.xml

# Audio Caliberations
PRODUCT_COPY_FILES += \
    $(A7LTE_PATH)/audio/acdb/Bluetooth_cal.acdb:system/etc/Bluetooth_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/General_cal.acdb:system/etc/General_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/Global_cal.acdb:system/etc/Global_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/Handset_cal.acdb:system/etc/Handset_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/Hdmi_cal.acdb:system/etc/Hdmi_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/Headset_cal.acdb:system/etc/Headset_cal.acdb \
    $(A7LTE_PATH)/audio/acdb/Speaker_cal.acdb:system/etc/Speaker_cal.acdb \
    $(A7LTE_PATH)/audio/Tfa9895.cnt:system/etc/Tfa9895.cnt

# Audio configuration
PRODUCT_COPY_FILES += \
    $(A7LTE_PATH)/audio/mixer_paths.xml:$(TARGET_COPY_OUT_VENDOR)/etc/mixer_paths.xml

# Keylayout
PRODUCT_COPY_FILES += \
    $(A7LTE_PATH)/keylayout/ft5x06_ts.kl:system/usr/keylayout/ft5x06_ts.kl \
    $(A7LTE_PATH)/keylayout/Synaptics_RMI4_TouchPad_Sensor.idc:system/usr/idc/Synaptics_RMI4_TouchPad_Sensor.idc \
    $(A7LTE_PATH)/keylayout/Synaptics_HID_TouchPad.idc:system/usr/idc/Synaptics_HID_TouchPad.idc \
    $(A7LTE_PATH)/keylayout/synaptics_dsx.kl:system/usr/keylayout/synaptics_dsx.kl \
    $(A7LTE_PATH)/keylayout/synaptics_rmi4_i2c.kl:system/usr/keylayout/synaptics_rmi4_i2c.kl

# Samsung A7 WLAN calibration, replacing the common default.
PRODUCT_COPY_FILES += \
    $(A7LTE_PATH)/wifi/WCNSS_qcom_wlan_nv.bin:system/etc/firmware/wlan/prima/WCNSS_qcom_wlan_nv.bin

# ANT+
PRODUCT_PACKAGES += \
   AntHalService \
   com.dsi.ant.antradio_library \
   libantradio

# Display
$(call inherit-product, frameworks/native/build/phone-xxhdpi-2048-dalvik-heap.mk)
$(call inherit-product, frameworks/native/build/phone-xxhdpi-2048-hwui-memory.mk)



PRODUCT_COPY_FILES += \
    $(A7LTE_PATH)/rootdir/etc/init.target.rc:root/init.target.rc

# Native Pie HIDL services absent from the historical common product.
PRODUCT_PACKAGES += \
    android.hardware.bluetooth@1.0-impl \
    android.hardware.bluetooth@1.0-service \
    android.hardware.configstore@1.1-service \
    rild \
    libril

# Device-specific declarations match source modules, not all common-board features.
DEVICE_MANIFEST_FILE := $(A7LTE_PATH)/manifest.xml
