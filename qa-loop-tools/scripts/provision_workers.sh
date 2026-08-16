#!/usr/bin/env bash
# Provision or tear down ephemeral worker simulators for parallel qa-loop passes.
#
# Usage:
#   provision_workers.sh up <count> [device-type-id] [runtime-id]
#   provision_workers.sh down
#
# `up` (re)creates qa-worker-1..N from a clean slate (existing qa-worker-*
# devices are deleted first, so every pass starts deterministic), boots them,
# creates an isolated scratch dir per worker (testers must write helper
# scripts and temp files ONLY there — shared /tmp paths collide across
# parallel workers), and prints
# {"workers":[{"name":"qa-worker-1","udid":"...","scratch":".qa-loop/scratch/qa-worker-1"}, ...]}.
# `down` shuts down and deletes every qa-worker-* device and removes
# ./.qa-loop/scratch. Run from the target repo root.
# Defaults: newest iPhone device type, newest available iOS runtime.
set -euo pipefail

cmd="${1:?usage: provision_workers.sh up <count> | down}"

list_workers() {
  xcrun simctl list -j devices | python3 -c '
import json, sys
for devs in json.load(sys.stdin)["devices"].values():
    for d in devs:
        if d["name"].startswith("qa-worker-"):
            print(d["udid"])'
}

delete_workers() {
  for udid in $(list_workers); do
    xcrun simctl shutdown "$udid" 2>/dev/null || true
    xcrun simctl delete "$udid"
  done
}

case "$cmd" in
  down)
    delete_workers
    rm -rf ./.qa-loop/scratch 2>/dev/null || true
    echo '{"workers":[]}'
    ;;
  up)
    count="${2:?usage: provision_workers.sh up <count>}"
    runtime="${4:-$(xcrun simctl list -j runtimes | python3 -c '
import json, sys
rs = [r["identifier"] for r in json.load(sys.stdin)["runtimes"]
      if r.get("isAvailable") and "iOS" in r["identifier"]]
print(rs[-1])')}"
    # Default device type: the newest iPhone the chosen runtime supports.
    # A runtime's supportedDeviceTypes list is ordered newest-first (unlike the
    # global devicetypes list, which has no useful ordering).
    devtype="${3:-$(xcrun simctl list -j runtimes | python3 -c '
import json, sys
rt = sys.argv[1]
for r in json.load(sys.stdin)["runtimes"]:
    if r["identifier"] == rt:
        ts = [t["identifier"] for t in r.get("supportedDeviceTypes", [])
              if "iPhone" in t["identifier"] and "SE" not in t["identifier"]]
        print(ts[0])
        break' "$runtime")}"
    delete_workers   # clean slate: remove leftovers from a previous run
    out=""
    for i in $(seq 1 "$count"); do
      udid="$(xcrun simctl create "qa-worker-$i" "$devtype" "$runtime")"
      xcrun simctl bootstatus "$udid" -b >/dev/null
      scratch=".qa-loop/scratch/qa-worker-$i"
      mkdir -p "$scratch"
      [ -n "$out" ] && out+=","
      out+="{\"name\":\"qa-worker-$i\",\"udid\":\"$udid\",\"scratch\":\"$scratch\"}"
    done
    echo "{\"workers\":[$out]}"
    ;;
  *)
    echo "unknown command: $cmd" >&2; exit 1;;
esac
