#!/usr/bin/env bash
# stop.sh <udid> — ask the driver on that simulator to exit.
UDID="${1:?usage: stop.sh <udid>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 "$HERE/qa.py" "$UDID" quit || true
sleep 2; pkill -f "test-without-building.*id=$UDID" 2>/dev/null; rm -f "/private/tmp/qa-driver/$UDID/alive"; echo "stopped $UDID"
