#!/usr/bin/env bash
# Record the actual Android build invocation; never substitute audit fixtures.
set -o pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TREE=${1:-"$ROOT/verification/platform"}
mkdir -p "$ROOT/logs/immediate-build"
LOG="$ROOT/logs/immediate-build/bootimage-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
(
    cd "$TREE" || exit 2
    echo 'COMMAND: source build/envsetup.sh; lunch lineage_a7lte-userdebug; mka bootimage'
    source build/envsetup.sh
    lunch lineage_a7lte-userdebug
    lunch_rc=$?
    echo "lunch_exit_code=$lunch_rc"
    # Execute the requested make wrapper too, so its actual prerequisite error
    # is captured even if product discovery already failed.
    export TARGET_PRODUCT=lineage_a7lte TARGET_BUILD_VARIANT=userdebug TARGET_BUILD_TYPE=release
    mka bootimage
    build_rc=$?
    echo "mka_bootimage_exit_code=$build_rc"
    exit "$build_rc"
) > "$LOG" 2>&1
rc=$?
tail -n 50 "$LOG" > "$ROOT/logs/immediate-build/last-50-lines.log"
printf '%s\n' "$LOG" > "$ROOT/logs/immediate-build/latest-log-path.txt"
echo "Build log: $LOG"
cat "$ROOT/logs/immediate-build/last-50-lines.log"
exit "$rc"
