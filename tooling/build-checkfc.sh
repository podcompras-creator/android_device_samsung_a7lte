#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=${1:-"$ROOT/sources/platform-sepolicy/tools/checkfc.c"}
mkdir -p "$ROOT/host/bin"
if [[ -f "$ROOT/host/usr/lib/x86_64-linux-gnu/libsepol.a" ]]; then
    gcc -O2 -Wall -I"$ROOT/host/usr/include" "$SOURCE" -o "$ROOT/host/bin/checkfc" "$ROOT/host/usr/lib/x86_64-linux-gnu/libsepol.a" -l:libselinux.so.1
else
    SEPOL_ARCHIVE=$(gcc -print-file-name=libsepol.a)
    [[ -f "$SEPOL_ARCHIVE" ]] || { echo 'Native libsepol-dev static archive is required' >&2; exit 2; }
    gcc -O2 -Wall "$SOURCE" -o "$ROOT/host/bin/checkfc" "$SEPOL_ARCHIVE" -lselinux
fi
