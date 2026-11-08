#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/tooling/boot-sources"
OUT="$ROOT/host/boot-tools"
mkdir -p "$OUT" "$ROOT/logs/phase3-boot"
python3 - "$ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); lock=json.loads((r/'tooling/boot-sources.lock.json').read_text())
for row in lock['sources']:
 p=r/'tooling/boot-sources'/row['path']
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
  raise SystemExit('Pinned boot source missing/changed: '+str(p))
print('PASS: pinned upstream boot-tool sources verified')
PY
gcc -O2 -Wall "$SRC/dtbtool.c" -o "$OUT/dtbToolLineage"
g++ -std=c++11 -O2 -Wall -I"$SRC/include" "$ROOT/tooling/boot-header-probe.cpp" -o "$OUT/boot-header-probe"
cat > "$OUT/mkbootimg" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
exec python3 "$ROOT/tooling/boot-sources/mkbootimg" "$@"
WRAP
chmod +x "$OUT/mkbootimg"
"$OUT/boot-header-probe"
"$OUT/mkbootimg" --help >/dev/null
printf 'PASS: dtbToolLineage compiled, Android header compiled, pinned Python mkbootimg runnable\n'
