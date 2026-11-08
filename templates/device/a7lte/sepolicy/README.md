# a7lte SELinux integration (Pie)

Includes Qualcomm legacy policy through msm8916-common. The device fragment adds
specific native Samsung partition/proc/sysfs labels and labels for legacy system
executables invoked by the inherited Samsung init. Their exec types/domain
transitions already exist in Qualcomm policy. `/efs` contents already use the
AOSP Pie `efs_file` context; no blanket EFS relabel or allow rules are added.

New allow rules let init read the SIM-count proc node that libinit uses and let
fsck check the EFS block device explicitly requested by the fstab check flag.
Additional permissions must come from real device AVCs, with the producer,
consumer and exact object identified. Never paste `audit2allow` output wholesale.

The inherited kernel command line uses permissive mode for bring-up. Neverallow
checks must remain enabled in the device BoardConfig despite upstream's userdebug
bypass. The selected monolithic Pie policy passes checkpolicy -M -c30 with neverallow
checks enabled (no -N). Android Pie checkfc validates both this device file_contexts
and the combined selected source file_contexts against that compiled policy.
These are real compilation/context checks, not a full Android image build. The
Android build-generated policy/CIL/context targets, filesystem tests and actual
AVC collection on SM-A700FD are still required before an enforcing release.
Permissive boot cannot establish an operational enforcing policy.
