# Samsung a7lte / Android 9 device integration audit

Authoritative local overrides: `templates/device/a7lte`. Generated trees:
`android/device/samsung/a7lte` and `msm8916-common`. Reproduce with
`python3 scripts/prepare-device.py` (or `--android-root PATH`); it requires the
pinned original `sources/a7lte` and `sources/common` checkouts and preserves an
independently generated proprietary inventory and stock `partition-sizes.mk`.
No OPPO source, DTB, HAL or calibration was used.

## Concrete corrections

- Converted CM13 product identifiers/vendor inheritance to LineageOS 16.
- Migrated hardware-key resources to the Pie `lineage-sdk` overlay path, verified
  against actual LineageOS 16 resource definitions. A7 overlay has precedence.
- Uses only the common Pie camera wrapper; the obsolete CM13 wrapper is excluded.
  Stock camera/sensors HALs must be renamed `camera.vendor.msm8916.so` and
  `sensors.vendor.msm8916.so`, respectively, by vendor generation.
- Removed duplicate TWRP fstab installation; common prebuilt modules consume
  `TARGET_DEVICE_FSTAB` and `TARGET_DEVICE_TWRP_FSTAB` overrides. No second module
  definition is introduced.
- Removed duplicate WLAN NV target and duplicate sec_touchkey/gpio-keys targets;
  common product accepts the A7-specific calibration and keylayout path while
  retaining its common cfg/ini and touchscreen keylayout.
- `/system` is mounted normally (`wait`, not `recoveryonly`): this is a legacy
  non-system-as-root device, and common `on fs` calls `mount_all fstab.qcom`.
- Removed unverified fota-as-misc mapping. Firmware vfat mounts use the existing
  Qualcomm `firmware_file` context; fixed the inherited malformed fmask value.
  Preserved the userdata encryption footer and existing ext4/f2fs alternatives.
- libinit sets a7lte/SM-A700FD and DSDS/LTE, using the common extension point.
  Fixed upstream's transposed vendor model/device property names. Default radio
  mode is GSM/WCDMA/LTE (9 per slot), not CDMA-inclusive global mode (10).
- Provides source-built `lights.msm8916` using the pinned Samsung lights source,
  with A7 LED-class backlight nodes confirmed in the compiled kernel source and
  the Samsung sec_touchkey node. Generic conflicting lights HALs are disabled by `TARGET_PROVIDES_LIBLIGHT`; the
  downloaded CAF display Android.mk confirms that condition.
- Recovery density is xxhdpi, matching 1080x1920 A7; proprietary SDClang is not
  requested because the selected GCC7.2 toolchain builds this kernel. The device
  explicitly selects that exact GCC path/prefix instead of depending on an
  upstream conditional wildcard or silently falling back to GCC4.9.
- Removed historical unaligned/unverified image sizes from active configuration.
  All image sizes must come from `partition-sizes.mk` generated from the stock PIT;
  image builds are gated separately. Historical sizes remain in original sources
  and the first preserved archive, not silently rounded or guessed.
- Neverallow compiler checks are explicitly enabled. Optional Qualcomm testing
  policy directories are excluded; that code is for manufacturing/debug tools,
  not this product. Runtime permissive boot remains an explicit bring-up setting.

## Verification performed

GNU Make actually evaluated the A7, Samsung common and Samsung qcom-common
product/BoardConfig files using the downloaded upstream files. It resolved
ARM/cortex-a53, the A7 variant configuration, xxhdpi recovery and
`SELINUX_IGNORE_NEVERALLOWS=false`; 66 evaluated copy targets have no duplicate
destinations. This narrow audit deliberately does not claim to evaluate missing
platform inheritance, proprietary modules or the complete Android build graph.
Inputs/results: `logs/device-audit-make-input.mk`, `device-audit-make-result.log`,
`device-audit-copy-destinations.log`.

`prepare-device.py` was rerun and compared using SHA-256 across all generated
files; output was byte-identical, including the independently maintained blob
inventory. XML syntax was parsed. Kernel, zImage, all five compiled DTBs, dt.img
and original raw build logs were not changed by this audit.
SELinux has a separate actual compiler audit, including failed attempts and
restrictive corrections; see `docs/sepolicy-audit.md` and `logs/sepolicy-audit-*`.

## Remaining limits

This is a corrected, reproducible source integration, not a verified shipping
ROM. Full Android lunch/Ninja/module linkage, compiled HALs, all platform resource
merges, VINTF and target image construction require the full checkout and exact
CSB1 proprietary files. Native PN547 NFC userspace/configuration and ANT modules
still need stock-firmware and full-build validation; no unrelated Samsung NFC
stack was imported from the newer unverified reference tree. Actual hardware
access, DSDS, encryption, recovery, firmware selection, display/touch and enforcing
SELinux need testing on the SM-A700FD. No runtime success is claimed.
