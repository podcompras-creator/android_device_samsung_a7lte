# SELinux audit — native Samsung a7lte / LineageOS 16

The device policy fragment is in `templates/device/a7lte/sepolicy`, copied into
the device tree by prepare-device. It declares the Samsung EFS block-device type,
labels actual `/proc/simslot_count` and virtual Samsung sensor/MDNIE nodes, and
uses existing Qualcomm domain-entry types for the legacy `/system/bin` daemon
paths referenced by common Samsung init. Two new allow rules let init read
the SIM-count node used by libinit and let fsck read/write the EFS block device
that the fstab explicitly marks for ext4 checking. AOSP Pie already labels `/efs` as `efs_file`.
The firmware FAT mounts also need the firmware_file context mount option.

## Real checks performed

Downloaded the legitimate LineageOS 16 platform, Lineage and Qualcomm legacy
policy source trees. Exact Git revisions are in
`logs/sepolicy-audit-sources.lock.json`. Debian's official m4/checkpolicy packages
and SELinux development headers were extracted locally, with package SHA-256 in
`logs/sepolicy-audit-host-packages.sha256`. The Android Pie `checkfc.c` was compiled
against those headers and libsepol. No firmware/phone data was used for these tests.

`python3 tooling/audit-policy.py` assembles the monolithic
`sepolicy_neverallows` inputs in the same pattern/directory order as Pie
system/sepolicy/Android.mk and definitions.mk, targeting ARM, MLS 1/1024,
userdebug, non-Treble, legacy camera HAL1, no ASAN, no compatible-property split,
no platform text relocations. Definitions, selected file list and result are
recorded in `logs/sepolicy-audit-build.json`. It invokes
`checkpolicy -M -c 30` **without `-N`**. Final result: **exit 0**, binary under
`out/policy-audit/sepolicy`.

Android Pie checkfc validates both the device file_contexts and all combined
selected source file_contexts against the compiled policy: **exit 0**. See
`logs/sepolicy-audit-checkfc.log` and `sepolicy-audit-checkfc-combined.log`.
Context type-reference checks are also recorded in `sepolicy-audit-validation.json`.

These checks do not replace the full Android build's policy/CIL packaging,
sepolicy_tests, installed filesystem validation, or on-device enforcing tests.
No runtime AVCs have been collected and no enforcing ROM has been demonstrated.

## Errors corrected; original failures preserved

Unmodified userdebug Qualcomm policy bypassed neverallow checks and selected
manufacturing test policy. Re-enabling checks revealed 1325 assertions. Removing
the unused manufacturing test directory from a7lte's policy inputs reduced that
to 623. Actual selected rules were then corrected by the explicit, reproducible
`patches/qcom-sepolicy-a7lte.patch`; no policy files were silently dropped.

- Restrict `hal_perf` process/sysfs operations to the actual `hal_perf_default`
  server. On non-Treble builds the attribute also contains application clients;
  server permissions were consequently granted to apps, violating isolation.
- Remove cross-process `/proc` reads from the manufacturing qti-testscripts
  debug domain and cross-app proc reads from dataservice_app. Domains remain
  declared/selected; these blanket grants are not part of Samsung A7 operation.
- Remove DAC-bypass capabilities forbidden by platform policy. Node access must
  instead use explicit init/ueventd ownership and modes, then device AVC evidence.
- Remove impossible sysfs/cgroup object creation and sysfs-directory writes.
  Correct three sysfs label declarations from file_type to fs_type/sysfs_type,
  preventing generic writable-file rules from treating sysfs as ordinary files.
- The Qualcomm RFS custom neverallow already excludes init. Add vendor_init to
  that same exclusion, reflecting Android 9's split-init execution domain. This
  adds no allow rule and preserves the custom assertion for every other domain;
  existing platform init permissions had contradicted the old assertion.
- Exclude isolated_app from inherited global sysfs reads, preserving Pie's
  isolated-process restrictions.

Failures from each iteration remain in `logs/sepolicy-audit-checkpolicy-*.log`.
The patch is compile-checked, not an on-device permission-validation result.
The common boot command line remains permissive for bring-up. Device BoardConfig
must set `SELINUX_IGNORE_NEVERALLOWS := false` after the upstream includes.

## Reprodução fora deste workspace

Python 3.9+ e ferramentas nativas m4/checkpolicy são necessários. O Containerfile
inclui os pacotes de compilação checkpolicy/libsepol/libselinux. Para restaurar
somente as pequenas fontes de policy:

```sh
python3 scripts/fetch-reference-sources.py --name platform-sepolicy --name lineage-sepolicy --name sepolicy-legacy
# Na primeira aplicação; para reruns, git apply --reverse --check identifica patch já aplicado.
git -C sources/sepolicy-legacy apply ../../patches/qcom-sepolicy-a7lte.patch
tooling/build-checkfc.sh
python3 tooling/audit-policy.py
```

O script agora aceita `--android-tree /plataforma/completa`, `--m4`,
`--checkpolicy` e `--checkfc`. Com checkfc disponível, também refaz a montagem m4 e
validação dos contextos locais e combinados; se não estiver instalado, registra
explicitamente que essa etapa não foi executada. As fontes necessárias são
checadas antes da compilação. O script não baixa nem executa binários vendor.
