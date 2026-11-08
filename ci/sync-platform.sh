#!/usr/bin/env bash
# Keep enough runner space to finish and upload logs instead of losing the VM.
set -uo pipefail
mkdir -p "$GITHUB_WORKSPACE/logs"
cd "$ANDROID_TREE" || exit 2
SYNC_PID=
cleanup() {
    if [[ -n "$SYNC_PID" ]] && kill -0 "$SYNC_PID" 2>/dev/null; then
        kill -TERM -- "-$SYNC_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM
setsid python3 "$PORT_ROOT/tooling/repo" sync -c -j8 --force-sync --no-clone-bundle --no-tags \
    > >(tee "$GITHUB_WORKSPACE/logs/repo-sync.log") 2>&1 &
SYNC_PID=$!
disk_stop=false
while kill -0 "$SYNC_PID" 2>/dev/null; do
    { date -u +%FT%TZ; df -h "$ANDROID_TREE"; free -m; } | tee -a "$GITHUB_WORKSPACE/logs/runner-resources.log"
    free_kib=$(df -Pk "$ANDROID_TREE" | awk 'NR==2 {print $4}')
    if ((free_kib < 2097152)); then
        echo "::error::repo sync stopped with ${free_kib} KiB free; reserving2GiB so Actions can preserve logs."
        disk_stop=true
        kill -TERM -- "-$SYNC_PID" 2>/dev/null || true
        break
    fi
    sleep 15
done
wait "$SYNC_PID"
rc=$?
if [[ "$disk_stop" == true ]]; then rc=78; fi
echo "repo_sync_exit_code=$rc disk_reserve_stop=$disk_stop" | tee "$GITHUB_WORKSPACE/logs/sync-result.txt"
exit "$rc"
