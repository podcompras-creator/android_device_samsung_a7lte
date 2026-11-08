#!/usr/bin/env bash
# Deliberate bring-up mode requested by the operator; no ZIP readiness gate.
set -o pipefail
cd "$ANDROID_TREE" || exit 2
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
brunch a7lte
