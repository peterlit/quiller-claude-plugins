#!/usr/bin/env bash
# start.sh <udid> <app-bundle-id> — build the driver once (cached in ./dd)
# and start serving on the named simulator in the background. Idempotent:
# exits 0 at once if that device is already served.
# Logs: /private/tmp/qa-driver/<udid>/driver.log
#
# The target app is a PARAMETER — nothing app-specific is baked into the
# backend. Run this from a writable copy of the backend directory (the skill
# copies ${CLAUDE_PLUGIN_ROOT}/drivers/ios-xcuitest/ to .qa-loop/driver/ —
# never build inside the plugin cache; a plugin update would sweep it away).
set -euo pipefail
UDID="${1:?usage: start.sh <udid> <app-bundle-id>}"
BUNDLE_ID="${2:-${QA_DRIVER_BUNDLE_ID:-}}"
[ -n "$BUNDLE_ID" ] || { echo "usage: start.sh <udid> <app-bundle-id> (or set QA_DRIVER_BUNDLE_ID)" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="/private/tmp/qa-driver/$UDID"
mkdir -p "$ROOT/cmd" "$ROOT/out"
if pgrep -f "test-without-building.*id=$UDID" >/dev/null && python3 "$HERE/qa.py" "$UDID" --alive >/dev/null 2>&1; then echo "already serving $UDID"; exit 0; fi
rm -f "$ROOT/alive"
cd "$HERE"
# The pre-generated xcodeproj ships with the backend; xcodegen is only a
# fallback for someone who edited project.yml.
if [ ! -d QADriver.xcodeproj ]; then
  command -v xcodegen >/dev/null || { echo "QADriver.xcodeproj missing and xcodegen not installed" >&2; exit 1; }
  xcodegen generate >/dev/null
fi
if [ ! -f dd/built.ok ]; then
  xcodebuild build-for-testing -project QADriver.xcodeproj -scheme QADriver \
    -destination "id=$UDID" -derivedDataPath dd -quiet 2>&1 | grep -v "^$" | tail -5 || true
  # The UI-test runner product is QADriver-Runner.app (hyphenated — the
  # field version checked an unhyphenated name and never marked built.ok).
  if ls dd/Build/Products/*/QADriver-Runner.app >/dev/null 2>&1; then
    touch dd/built.ok
  fi
fi
[ -f dd/built.ok ] || { echo "driver build failed — see xcodebuild output above" >&2; exit 1; }
rm -f "$ROOT"/cmd/* "$ROOT"/out/* "$ROOT/alive"
printf '%s\n' "$BUNDLE_ID" > "$ROOT/bundle_id"
nohup env TEST_RUNNER_QA_DRIVER_BUNDLE_ID="$BUNDLE_ID" \
  xcodebuild test-without-building -project QADriver.xcodeproj -scheme QADriver \
  -destination "id=$UDID" -derivedDataPath dd -only-testing:QADriver/QADriverTests/testServe \
  > "$ROOT/driver.log" 2>&1 &
echo "starting driver on $UDID for $BUNDLE_ID (pid $!) — waiting for it to serve..."
for i in $(seq 1 120); do
  if python3 "$HERE/qa.py" "$UDID" --alive >/dev/null 2>&1; then echo "serving $UDID"; exit 0; fi
  sleep 1
done
echo "driver did not come up in 120 s; see $ROOT/driver.log"; tail -20 "$ROOT/driver.log"; exit 1
