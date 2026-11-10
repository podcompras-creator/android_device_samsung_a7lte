#!/usr/bin/env bash
# Source/progress archive only. Never creates a ROM or modifies preserved images.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT=${1:?Usage: package-progress-xz.sh NEW-OUTPUT.tar.xz}
OUTPUT=$(realpath -m "$OUTPUT")
PROFILE=${2:-core}
EXTRA_EXCLUDES=()
case "$PROFILE" in
    full) ;;
    core)
        # These historical/debug outputs remain in the untouched older archive.
        # Keep original zImage/DTBs/dt.img and the latest genuine run8 boot here.
        EXTRA_EXCLUDES=(--exclude='artifacts/vmlinux'
            --exclude='artifacts/boot-audit'
            --exclude='artifacts/android-run6-unvalidated/boot.img'
            --exclude='artifacts/android-run6-header-repack/boot.img'
            --exclude='artifacts/android-run7-unvalidated/boot.img'
            --exclude='artifacts/ril-protobuf-isolation-prototype/*.so')
        ;;
    *) echo 'Profile must be core or full.' >&2; exit 2 ;;
esac
[[ "$OUTPUT" == *.tar.xz && ! -e "$OUTPUT" ]] || {
    echo 'Choose a new .tar.xz output; existing packages are preserved.' >&2
    exit 2
}
mkdir -p "$(dirname "$OUTPUT")"
# Bound the new archive to the available disk, retaining a 16 MiB reserve.
A7LTE_PACKAGE_LIMIT=$(python3 - "$(dirname "$OUTPUT")" <<'PY'
import shutil,sys
limit=min(64*1024**2, shutil.disk_usage(sys.argv[1]).free-16*1024**2)
if limit < 32*1024**2:
    raise SystemExit('Insufficient free disk for bounded consolidated packaging.')
print(limit)
PY
)
export A7LTE_PACKAGE_LIMIT
TMP=$(mktemp "$(dirname "$OUTPUT")/.a7lte-progress.XXXXXX.tar.xz")
trap 'rm -f "$TMP"' EXIT
cd "$ROOT"
tar -cf - --exclude='*.tar.gz' --exclude='*.tar.xz' --exclude='*.bundle' \
    --exclude='__pycache__' --exclude='tooling/git-repo' \
    "${EXTRA_EXCLUDES[@]}" \
    README.md STATUS.md Containerfile local_manifests.xml .find-ignore .github ci \
    sources.lock.json host-tools.lock.json scripts manifests patches templates \
    tests android docs logs artifacts tooling sources/hal-audit \
    sources/dtbtool.c sources/dtbtool.origin.json | \
python3 -c 'import os,resource; cap=int(os.environ["A7LTE_PACKAGE_LIMIT"]); resource.setrlimit(resource.RLIMIT_FSIZE,(cap,cap)); os.execvp("xz",["xz","-6","-T1","--lzma2=dict=64MiB","-c"])' > "$TMP"
# The temporary archive lives beside the output, so this rename needs no copy.
mv "$TMP" "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
echo "$OUTPUT"
