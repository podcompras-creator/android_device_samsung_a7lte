#!/usr/bin/env bash
set -eo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TREE="$ROOT/android"
TARGET=nothing
JOBS=${BUILD_JOBS:-3}
LAYOUT=
while (($#)); do
    case "$1" in
        --tree) TREE=$2; shift 2 ;;
        --target) TARGET=$2; shift 2 ;;
        --jobs) JOBS=$2; shift 2 ;;
        --layout) LAYOUT=$2; shift 2 ;;
        -h|--help) echo 'Usage: build-rom.sh [--tree DIR] [--target nothing|kernel|policy|images|bacon] [--jobs N] [--layout JSON]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || exit 2
case "$TARGET" in
    nothing) GOALS=(nothing) ;;
    kernel) GOALS=(kernel) ;;
    policy) GOALS=(sepolicy) ;;
    images) GOALS=(bootimage recoveryimage systemimage) ;;
    bacon) GOALS=(bacon) ;;
    *) echo "Unknown target: $TARGET" >&2; exit 2 ;;
esac
TREE=$(cd "$TREE" && pwd)
mkdir -p "$ROOT/logs/platform"
LOG="$ROOT/logs/platform/build-${TARGET}-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee "$LOG") 2>&1
trap 'rc=$?; echo "build_exit_code=$rc target=$TARGET"' EXIT
[[ -f "$TREE/build/envsetup.sh" ]] || { echo 'BLOCKED: platform not synced; use sync-platform.sh --tree DIR --sync on a larger volume. Manifest/dependency validation is independently runnable.'; exit 78; }
if [[ "$TARGET" == images || "$TARGET" == bacon ]]; then
    [[ -n "$LAYOUT" ]] || { echo 'Image packing requires --layout JSON from verify-stock-layout.py; compile-only goals do not.'; exit 78; }
    python3 "$ROOT/scripts/check-build-inputs.py" --tree "$TREE" --layout "$LAYOUT"
fi
# Android 9 supplies its JDK; do not accidentally build with host Java 21.
if [[ -x "$TREE/prebuilts/jdk/jdk8/linux-x86/bin/java" ]]; then
    export JAVA_HOME="$TREE/prebuilts/jdk/jdk8/linux-x86"
    export PATH="$JAVA_HOME/bin:$PATH"
fi
command -v python2 >/dev/null || { echo 'BLOCKED: Python 2.7 required by legacy Android 9 tools; see docs/build.md / Containerfile.'; exit 78; }
cd "$TREE"
# Android envsetup is not nounset-safe. No missing-dependency or neverallow bypass.
source build/envsetup.sh
export ALLOW_MISSING_DEPENDENCIES=false
lunch lineage_a7lte-userdebug
m -j"$JOBS" "${GOALS[@]}"
