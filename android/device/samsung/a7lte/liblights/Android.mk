# Reuse the pinned Samsung HAL implementation with A7-specific sysfs paths.
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_SRC_FILES := ../../../../hardware/samsung/liblights/lights.c
LOCAL_C_INCLUDES := $(LOCAL_PATH)/include
LOCAL_SHARED_LIBRARIES := liblog
LOCAL_STATIC_LIBRARIES := liblights_helper
LOCAL_MODULE := lights.$(TARGET_BOARD_PLATFORM)
LOCAL_MODULE_RELATIVE_PATH := hw
LOCAL_PROPRIETARY_MODULE := true
LOCAL_MODULE_TAGS := optional
include $(BUILD_SHARED_LIBRARY)
