$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
$(call inherit-product, device/samsung/a7lte/device.mk)
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)
PRODUCT_DEVICE := a7lte
PRODUCT_NAME := lineage_a7lte
PRODUCT_BRAND := samsung
PRODUCT_MODEL := SM-A700FD
PRODUCT_MANUFACTURER := samsung
