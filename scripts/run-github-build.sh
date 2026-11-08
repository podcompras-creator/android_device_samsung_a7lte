#!/usr/bin/env bash
# Dispatch an already-published workflow; never publishes source or guesses a repo.
set -euo pipefail
REPOSITORY=
REF=
DESTINATION=
WATCH=false
while (($#)); do
    case "$1" in
        --repository) REPOSITORY=$2; shift 2 ;;
        --ref) REF=$2; shift 2 ;;
        --output) DESTINATION=$2; shift 2 ;;
        --watch) WATCH=true; shift ;;
        -h|--help) echo 'Usage: run-github-build.sh --repository OWNER/REPO [--ref BRANCH] [--watch] [--output DIRECTORY]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo '--repository OWNER/REPO is required' >&2; exit 2; }
command -v gh >/dev/null || { echo 'GitHub CLI is required' >&2; exit 78; }
# gh auth status is not sufficient on every CLI version; verify a real API request.
gh api user --jq .login >/dev/null || { echo 'BLOCKED: reconnect GitHub authentication; never send a token in chat.' >&2; exit 78; }
if [[ -z "$REF" ]]; then REF=$(gh api "repos/$REPOSITORY" --jq .default_branch); fi
[[ -n "$REF" && "$REF" != -* ]] || { echo 'Invalid ref' >&2; exit 2; }
gh api "repos/$REPOSITORY/actions/workflows/build_rom.yml" --jq .state | rg -qx active || { echo 'Published build_rom.yml must be enabled in the selected repository.' >&2; exit 78; }
COMMIT=$(gh api "repos/$REPOSITORY/commits/$REF" --jq .sha)
STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run build_rom.yml --repo "$REPOSITORY" --ref "$REF"
echo "Workflow dispatched: https://github.com/$REPOSITORY/actions/workflows/build_rom.yml"
if [[ "$WATCH" != true ]]; then exit 0; fi
RUN_ID=
for _ in {1..20}; do
    CANDIDATES=$(gh run list --repo "$REPOSITORY" --workflow build_rom.yml --event workflow_dispatch --limit 20 --json databaseId,headSha,createdAt)
    RUN_ID=$(python3 - "$COMMIT" "$STARTED" "$CANDIDATES" <<'PY'
import json,sys
rows=[r for r in json.loads(sys.argv[3]) if r['headSha']==sys.argv[1] and r['createdAt']>=sys.argv[2]]
print(min(rows,key=lambda r:r['databaseId'])['databaseId'] if rows else '')
PY
)
    [[ -n "$RUN_ID" ]] && break
    sleep 3
done
[[ -n "$RUN_ID" ]] || { echo 'Dispatch accepted, run ID not yet visible. Do not dispatch again; inspect the workflow URL.' >&2; exit 75; }
echo "Run: https://github.com/$REPOSITORY/actions/runs/$RUN_ID"
rc=0
gh run watch "$RUN_ID" --repo "$REPOSITORY" --exit-status || rc=$?
if [[ -n "$DESTINATION" ]]; then
    mkdir -p "$DESTINATION"
    gh run download "$RUN_ID" --repo "$REPOSITORY" --dir "$DESTINATION" || { echo 'No downloadable artifacts available; retaining build log.' >&2; }
    gh run view "$RUN_ID" --repo "$REPOSITORY" --log > "$DESTINATION/actions-run.log" || true
fi
exit "$rc"
