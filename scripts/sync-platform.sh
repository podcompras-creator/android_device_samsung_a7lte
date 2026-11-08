#!/usr/bin/env bash
# Full fetch is opt-in via --sync; --manifest-only is useful on small builders.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
MODE=manifest-only
JOBS=${SYNC_JOBS:-4}
TREE=
LOCKED=
while (($#)); do
    case "$1" in
        --tree) TREE=$2; shift 2 ;;
        --manifest-only) MODE=manifest-only; shift ;;
        --sync) MODE=sync; shift ;;
        --jobs) JOBS=$2; shift 2 ;;
        --locked-manifest) LOCKED=$2; shift 2 ;;
        -h|--help) echo 'Usage: sync-platform.sh --tree DIRECTORY [--manifest-only|--sync] [--jobs N] [--locked-manifest FILE]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ -n "$TREE" && "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo '--tree and positive --jobs required' >&2; exit 2; }
mkdir -p "$TREE"
TREE=$(cd "$TREE" && pwd)
LOGS="$ROOT/logs/platform/sync-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$LOGS"
exec > >(tee "$LOGS/sync.log") 2>&1
trap 'rc=$?; echo "sync_exit_code=$rc mode=$MODE"' EXIT
readarray -t CONFIG < <(python3 - "$ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); c=json.loads((r/'manifests/platform.lock.json').read_text())
assert hashlib.sha256((r/'tooling/repo').read_bytes()).hexdigest()==c['launcher_sha256'], 'repo launcher hash differs'
for k in ['manifest_url','manifest_revision','repo_url','repo_revision']: print(c[k])
PY
)
[[ ${#CONFIG[@]} == 4 ]] || exit 2
if [[ "$MODE" == sync ]]; then
    FREE=$(df -Pk "$TREE" | awk 'NR==2 {print $4}')
    MIN=${MIN_SYNC_FREE_KIB:-209715200}
    [[ "$MIN" =~ ^[1-9][0-9]*$ ]] || { echo "MIN_SYNC_FREE_KIB must be numeric"; exit 2; }
    if (( FREE < MIN )); then
        echo "Need at least $MIN KiB free before full sync; found $FREE. Manifest-only works here."
        exit 78
    fi
fi
if [[ -n "$LOCKED" ]]; then
    LOCKED=$(realpath "$LOCKED")
    python3 "$ROOT/scripts/export-resolved-manifest.py" "$LOCKED" "$LOGS/replay-input.xml"
fi
cd "$TREE"
if [[ -n "$LOCKED" ]]; then
    if [[ -f .repo/local_manifests/a7lte.xml ]]; then
        cmp -s .repo/local_manifests/a7lte.xml "$ROOT/manifests/a7lte-dependencies.xml" || { echo 'Local a7lte manifest differs; preserve/reconcile it before locked replay'; exit 2; }
        rm .repo/local_manifests/a7lte.xml
    fi
    # All remotes in replay-input.xml are absolute; no relative file:// remotes.
    python3 "$ROOT/tooling/repo" init --standalone-manifest -u "file://$LOGS/replay-input.xml" --depth=1 --no-clone-bundle --repo-url="${CONFIG[2]}" --repo-rev="${CONFIG[3]}"
else
python3 "$ROOT/tooling/repo" init -u "${CONFIG[0]}" -b "${CONFIG[1]}" --depth=1 --no-clone-bundle --repo-url="${CONFIG[2]}" --repo-rev="${CONFIG[3]}"
mkdir -p .repo/local_manifests
cp "$ROOT/manifests/a7lte-dependencies.xml" .repo/local_manifests/a7lte.xml
fi
python3 "$ROOT/tooling/repo" manifest -o "$LOGS/manifest-expanded.xml"
python3 "$ROOT/scripts/check-manifest.py" "$LOGS/manifest-expanded.xml"
if [[ "$MODE" == sync ]]; then
    python3 "$ROOT/tooling/repo" sync -c --no-clone-bundle --no-tags -j"$JOBS"
    python3 "$ROOT/tooling/repo" manifest -r -o "$LOGS/manifest-resolved.xml"
    python3 "$ROOT/scripts/export-resolved-manifest.py" "$LOGS/manifest-resolved.xml" "$LOGS/a7lte-platform.lock.xml"
    python3 "$ROOT/scripts/apply-overlay.py" --tree "$TREE"
fi
