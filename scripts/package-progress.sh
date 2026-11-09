#!/usr/bin/env bash
# Preserve initial build artifacts; package only after validation.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT=${1:-"$ROOT/artifacts/a7lte-actions-project.tar.gz"}
OUTPUT=$(realpath -m "$OUTPUT")
[[ ! -e "$OUTPUT" && "$OUTPUT" != "$ROOT/artifacts/a7lte-progress.tar.gz" && "$OUTPUT" != "$ROOT/artifacts/a7lte-update.tar.gz" ]] || { echo 'The original progress archive is preserved; choose another output name.' >&2; exit 2; }
cd "$ROOT"
(cd artifacts && sha256sum -c "$ROOT/logs/continuation/original-artifacts.sha256") >/dev/null
python3 - <<'PY'
from pathlib import Path
import hashlib
root=Path('artifacts'); rows=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name not in {'SHA256SUMS','UPDATE-SHA256SUMS','PHASE3-SHA256SUMS'} and '.tar.gz' not in p.name:
        rows.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root)))
(root/'PHASE3-SHA256SUMS').write_text('\n'.join(rows)+'\n')
PY
TMP=$(mktemp /tmp/a7lte-update.XXXXXX.tar.gz)
trap 'rm -f "$TMP"' EXIT
mkdir -p "$(dirname "$OUTPUT")"
tar -czf "$TMP" --exclude='*.tar.gz' --exclude='*.tar.gz.sha256' --exclude='__pycache__' --exclude='tooling/git-repo' \
    README.md STATUS.md Containerfile local_manifests.xml .find-ignore .github ci sources.lock.json host-tools.lock.json scripts manifests patches templates tests android docs logs artifacts tooling sources/hal-audit sources/dtbtool.c sources/dtbtool.origin.json
mv "$TMP" "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
echo "$OUTPUT"
