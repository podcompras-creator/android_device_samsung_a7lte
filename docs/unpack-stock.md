# Stock firmware staging without root

`safe-unpack-stock.py` stages selected payloads from a downloaded firmware ZIP or
Samsung TAR/TAR.MD5. It accepts nested ZIP → TAR/TAR.MD5 (up to the configured
depth), without unpacking bootloaders or running code from the firmware.

```sh
python3 scripts/safe-unpack-stock.py firmware.zip --output /large-disk/a7lte-stock-payloads
```

The new output directory contains `payloads/` with SYSTEM, boot, recovery, cache,
PIT and recognized CSC metadata files, and `firmware-payloads.json` with source
archive chains, sizes and SHA-256 values. Existing output is refused. The script
checks appended Samsung TAR MD5 footers when present; MD5 equality is a transport
integrity check, **not** Samsung signature or firmware identity validation.
`extract-stock.py` separately checks the model/build properties inside SYSTEM.

Archive paths, encrypted ZIP members, symlinks, hardlinks, devices, GNU sparse TAR
members, duplicate selected basenames, excessive nesting, declared/actual sizes
and member counts are checked. Default limits are 16 GiB per member, 32 GiB total
including nested containers, 10,000 members and two nested archive levels. Change
them explicitly for larger legitimate firmware; do not relax them to mask a
malformed download. Failures leave an `unpack-error.json` and partial evidence in
the new output; rerun into another empty directory.

## SYSTEM image conversion and inspection

This staging script does not itself unpack ext4 or Android sparse filesystems.
The cloud now has pinned local `lz4`, `simg2img`, `debugfs` and `mkfs.ext4` tools;
see [stock-tools.md](stock-tools.md). Bootstrap without sudo using
`python3 scripts/fetch-stock-tools.py` (or `--offline` for cached packages), then
`export PATH="$PWD/host/stock-tools/bin:$PATH"`. A real synthetic ext4/sparse/LZ4
roundtrip and read-only debugfs extraction passed. On another Linux distribution,
the equivalent system packages are `lz4`, `android-sdk-libsparse-utils` and
`e2fsprogs`. Typical stages are:

```sh
lz4 -d system.img.ext4.lz4 system.img.ext4
simg2img system.img.ext4 system.raw.img
```

Run `lz4` only if the downloaded payload is actually LZ4. Run `simg2img` only if
its first four bytes are Android sparse magic `3a ff 26 ed`; an ordinary ext4
image is already raw. Preserve the original payload and hashes. These conversions
need room for both original and raw images, which can require several GiB.

Use `debugfs` read-only to inspect raw ext4 without mounting it:

```sh
debugfs -R 'cat /build.prop' system.raw.img
debugfs -R 'stat /lib/hw/camera.msm8916.so' system.raw.img
```

For filesystem extraction, use a disposable unprivileged environment with no host
credentials and an empty staging directory. Do not use `debugfs -w`, do not mount
writable firmware, and do not run firmware executables. A full `rdump` can create
symlinks and special entries from an untrusted filesystem; it is deliberately not
automated here. Prefer dumping the explicit candidate files plus `build.prop`
from the raw image into the expected SYSTEM directory, checking links/paths,
then invoke `extract-stock.py`. The blob extractor independently rejects paths
that resolve outside the supplied SYSTEM root and never executes proprietary
binaries.

`cache.img` may contain CSC packages/metadata; its presence alone does not prove
the ZTO region. Check the CSC package identity/sales code separately. Neither
archive filenames nor a mirror's download page prove the exact AP/CSC contents.

Validation performed: `python3 tests/test_unpack_stock.py` passes ten synthetic
archive tests, including ZIP traversal, TAR/ZIP links, devices, duplicate selected
names, byte/member budgets, nested TAR.MD5 integrity and existing-output
preservation. No real CSB1 archive was available for this test.
