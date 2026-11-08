# a7lte native Pie HAL contract audit

This is a **source contract audit**, not a full Android linker/VINTF compatibility
build or a claim that a HAL starts on the phone. The expected legacy Samsung
proprietary components still need exact CSB1 ELF dependency/symbol validation.
The diagnostic profile may deliberately keep Android services disabled; manifest
entries describe the integrated implementation contract, not a successful start.

## Source-backed corrections

- The common product requested `android.hardware.audio.effect@2.0-service`, which
  does not exist in the selected Pie hardware/interfaces tree. Its actual
  `android.hardware.audio@2.0-service` registers core audio, effects and optional
  soundtrigger interfaces. The nonexistent module was removed; both implementation
  libraries remain and the soundtrigger declaration was added.
- The inherited LiveDisplay package/interface was version 1.0 (`IColor`). The
  current LineageOS 16 sources actually define
  `vendor.lineage.livedisplay@2.0-service-legacymm`; its source registers
  `IDisplayModes/default` and `IPictureAdjustment/default`. Product and manifest
  now match that source instead of requesting the old nonexistent module.
- Added the source-defined Bluetooth 1.0 implementation/service and configstore
  1.1 service. The latter implements the existing 1.0 SurfaceFlinger contract. Wi-Fi service
  module `@1.0-service` legitimately implements IWifi version 1.2; supplicant1.1
  and hostapd1.0 contracts were checked against the actual source build files.
- Added missing manifest entries for the selected legacy camera provider,
  GNSS, light, sensors, vibrator, memtrack, RenderScript, broadcast radio and DRM
  implementations. These use 32-bit passthrough transport because the product
  selects those libraries rather than separate HIDL service executables.
- Retained the Lineage **legacy** camera provider and device adapters from
  `hardware/lineage/interfaces`; they are not missing generic camera modules.
  Camera provider instance is `legacy/0`, exactly as requested by Pie's
  CameraProviderManager. This change does not assert camera blob ABI compatibility.
- `android.hardware.usb@1.0-service.basic` is legitimate: it comes from the
  Lineage interfaces USB basic adapter, not AOSP's differently named USB default.
- Explicitly selected source `rild` and `libril` with radio 1.1 and deprecated
  OEM-hook 1.0 manifest instances `slot1` and `slot2`. The historical two-process
  Samsung design uses the normal single-slot source build and client `-c 2` for
  the second service name. **SIM_COUNT=2 was not blindly added**: Pie libril would
  register both slots in each process and conflict with that design. Exact Samsung
  callback ABI and second-process lifecycle remain unvalidated; the current
  diagnostic profile keeps radio disabled.
- Removed the common CDMA feature permission from this GSM/WCDMA/LTE SM-A700FD.
- NFC and IR were advertised by the generic common manifest without an installed
  matching implementation. The A7-specific default manifest no longer advertises
  either. NFC is a real PN547 source integration task still blocked by its exact
  userspace configuration/firmware; no unrelated Samsung/OPPO stack was copied.

The authoritative manifest is `templates/device/a7lte/manifest.xml`, selected by
A7 `device.mk`. `prepare-device.py` regenerates both A7 files and the small common
product corrections. It preserves the parent's diagnostic boot modifications.

## Legitimate PN547 and ANT source findings

The native A7 kernel DTS declares PN547, and its actual driver creates `/dev/pn547`
when CONFIG_NFC_PN547 is selected. The legitimate LineageOS NXP NFC source supports
PN547C2, but its example configuration names `/dev/pn54x` and is explicitly an
example. Substituting that example would not prove correct board tuning, firmware,
clock, antenna or secure-element configuration. The source snapshots/origins are
under `sources/hal-audit/nfc-ant/android_hardware_nxp_nfc`; exact stock configuration
and firmware remain necessary before enabling an NFC service/feature declaration.

The existing ANT choice `BOARD_ANT_WIRELESS_DEVICE := "vfs-prerelease"` is an
accepted branch in the actual LineageOS 16 ANT source. It builds `libantradio` and
selects `/dev/smd5` (commands) and `/dev/smd6` (data). `AntHalService`,
`com.dsi.ant.antradio_library`, and its copied permission XML are present in the
legitimate platform repositories already declared by the Lineage manifest.
No replacement transport or extra external dependency was invented. The transport
still needs real modem firmware/hardware testing.

## Executed targeted checks

`python3 scripts/audit-hal-contracts.py` checks 26 source-backed HAL contracts,
module names, manifest interfaces/instances/transports, source snapshot hashes and
camera/sensors wrapper lookup names. The report includes exact source definitions
and unresolved ABI/runtime work. At final run it validated 101 fetched source
files with no contract errors. Input provenance/pins and SHA-256 values are in
`logs/phase3-hal-sources.json`; failed speculative source paths are retained as
404 evidence rather than treated as downloaded modules.

The actual camera and sensors wrappers load the `vendor` legacy HAL variant,
requiring `camera.vendor.msm8916.so` and `sensors.vendor.msm8916.so`. This was
coordinated with the proprietary dependency audit; the script explicitly reports
that filenames do not prove compatible ELF symbols. In particular historical A7
RILs import old protobuf and RIL_SIM_SAP field symbols; stock `libril` must not be
installed over the source Pie implementation merely to hide those requirements.

No previous 46-test suite or kernel compilation was repeated for this audit.
No original boot/kernel/DTB artifacts were altered.

## Exact CSB1 boot-ramdisk comparison

The official Samsung FUS retrieval now supplies boot/recovery/PIT from
A700FDXXS1CSB1. This comparison uses the inventoried boot text files under
`logs/phase3-boot/stock-ramdisks/boot`, whose source boot image SHA-256 is
`01e1ff5ad1d1530cb922ae884f6796794e3dadae620341107fd5ebc993e27e12`.
The original image and extracted ramdisk were preserved.

Stock `init.target.rc` mounts APNHLOS at `/firmware` and MODEM at
`/firmware-modem`, with FAT uid/gid 1000. Native paths already agreed; both
fstab entries now use that verified ownership instead of inherited gid 1026.
Stock explicitly checks persist and EFS before ext4 mounts. Native fstab now
requests `wait,check` for both and retains `nosuid,nodev`; this maps the intent
to Pie fs_mgr rather than importing Samsung's old `check_fs` init command.
Stock `ueventd.qcom.rc` confirms ANT nodes `/dev/smd5` and `/dev/smd6`, both
0660 system/system. This supports the selected source transport but does not
prove a working ANT firmware path.

Stock `init.carrier.rc` references `/dev/sec-nfc`; this generic permission
command does not establish the exact PN547 userspace/firmware configuration.
Neither an unrelated NFC stack nor the NXP example config was installed.
The same carrier script confirms the historical second RIL process with
`libsec-ril-dsds.so` and client 2; this is evidence for the source design,
not an ABI/runtime validation.

`logs/phase3-hal-stock-comparison.json` records six passing text checks,
source hashes and limitations. Stock SYSTEM still needs recovery and ELF
dependency checking. Runtime remains untested. No kernel or Android build
was started for these final comparisons.
