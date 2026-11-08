# Experimental LineageOS 16 bring-up; stock layout is required for image targets.
DEVICE_PATH := device/samsung/a7lte
USE_CUSTOM_MIXER_PATHS := true
include device/samsung/msm8916-common/BoardConfigCommon.mk
DEVICE_PATH := device/samsung/a7lte
TARGET_KERNEL_CONFIG := msm8916_sec_defconfig
TARGET_KERNEL_VARIANT_CONFIG := msm8939_sec_a7_eur_defconfig
TARGET_KERNEL_SELINUX_CONFIG := selinux_defconfig
TARGET_KERNEL_SOURCE := kernel/samsung/msm8916
# Exact CSB1 boot/recovery use QCDT v3; preserve v2 artifact as historical evidence.
BOARD_DTBTOOL_ARGS := -3
# Use the exact toolchain already used for the successful standalone ARM build.
KERNEL_TOOLCHAIN := $(abspath prebuilts/gcc/linux-x86/arm/arm-eabi-7.2/bin)
KERNEL_TOOLCHAIN_PREFIX := arm-eabi-
TARGET_KERNEL_SELINUX_LOG_CONFIG :=
TARGET_USES_64_BIT_BINDER := true
TARGET_SCREEN_DENSITY := 480
# Samsung native lights HAL with the MSM8939 MDSS LED-class nodes.
TARGET_PROVIDES_LIBLIGHT := true
BOARD_BLUETOOTH_BDROID_BUILDCFG_INCLUDE_DIR := $(DEVICE_PATH)/bluetooth
TARGET_LIBINIT_MSM8916_DEFINES_FILE := $(DEVICE_PATH)/init/init_a7lte.cpp
# Image sizes must come from the verified SM-A700FD PIT, not historical guesses.
BOARD_BOOTIMAGE_PARTITION_SIZE :=
BOARD_RECOVERYIMAGE_PARTITION_SIZE :=
BOARD_SYSTEMIMAGE_PARTITION_SIZE :=
BOARD_USERDATAIMAGE_PARTITION_SIZE :=
BOARD_CACHEIMAGE_PARTITION_SIZE :=
BOARD_PERSISTIMAGE_PARTITION_SIZE :=
-include $(DEVICE_PATH)/partition-sizes.mk
TARGET_RECOVERY_DENSITY := xxhdpi
TARGET_DEVICE_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.qcom
TARGET_DEVICE_TWRP_FSTAB := $(DEVICE_PATH)/recovery/twrp.fstab
TARGET_HAS_CUSTOM_WLAN_NV := true
# The selected upstream GCC 7.2 toolchain is sufficient; no proprietary SDClang.
TARGET_USE_SDCLANG := false
# Enforce policy compiler neverallow checks even for a bring-up userdebug build.
BOARD_SEPOLICY_DIRS := $(filter-out device/qcom/sepolicy-legacy/test,$(BOARD_SEPOLICY_DIRS))
SELINUX_IGNORE_NEVERALLOWS := false
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.qcom
BOARD_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy
# Common branch requests permissive boot: enforcing remains a bring-up blocker.
-include vendor/samsung/a7lte/BoardConfigVendor.mk
