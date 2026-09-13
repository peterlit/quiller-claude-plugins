#!/usr/bin/env bash
# Provision or tear down worker simulators for parallel qa-loop passes.
#
# Usage:
#   provision_workers.sh up <count> [device-type-id] [runtime-id] [--fresh]
#   provision_workers.sh down
#
# Names are NAMESPACED per target repo: qa-worker-<hash8>-N, where hash8 is
# the first 8 hex chars of sha256 of this repo root's absolute path. Two
# sessions on one Mac once ran the un-namespaced `up` the same minute and
# deleted each other's workers mid-run (measured 2026-09-09); create/delete
# now touch only THIS repo's prefix, never anyone else's devices.
#
# `up` REUSES an existing healthy worker (same name, device type, runtime)
# instead of recreating it: recreation issues a new UDID, and the per-device
# MCP simulator-control grants die with the old one (measured: three fresh
# wave-1 testers were refused every tap with the user away, and the run fell
# back to sequential). --fresh forces delete/recreate. Each output row
# carries "reused": a reused device keeps its grant; a created one has NONE
# until a human grants it — Stage 0's real-tap probe must cover it before
# the first dispatch wave.
#
# Prints {"workers":[{"name","udid","scratch","reused"}...]} and writes the
# same JSON to .qa-loop/scratch/workers.json (the manifest `down` trusts).
# `down` shuts down and deletes only this repo's workers and removes
# ./.qa-loop/scratch. Run from the target repo root.
# Defaults: newest iPhone device type, newest available iOS runtime.
set -euo pipefail

cmd="${1:?usage: provision_workers.sh up <count> [devtype] [runtime] [--fresh] | down}"
hash8="$(printf '%s' "$PWD" | /usr/bin/shasum -a 256 | cut -c1-8)"
prefix="qa-worker-${hash8}"

list_mine() {
  # udid<TAB>name<TAB>devtype<TAB>runtime<TAB>state, this repo's prefix only.
  xcrun simctl list -j devices | python3 -c '
import json, sys
prefix = sys.argv[1]
for runtime, devs in json.load(sys.stdin)["devices"].items():
    for d in devs:
        if d["name"].startswith(prefix + "-"):
            print("\t".join([d["udid"], d["name"],
                             d.get("deviceTypeIdentifier", ""), runtime,
                             d.get("state", "")]))' "$prefix"
}

remove_device() {
  xcrun simctl shutdown "$1" 2>/dev/null || true
  xcrun simctl delete "$1"
}

case "$cmd" in
  down)
    while IFS=$'\t' read -r udid _name _dt _rt _st; do
      [ -n "$udid" ] || continue
      remove_device "$udid"
    done <<EOF
$(list_mine)
EOF
    rm -rf ./.qa-loop/scratch 2>/dev/null || true
    echo '{"workers":[]}'
    ;;
  up)
    count="${2:?usage: provision_workers.sh up <count>}"
    fresh=0
    devtype_arg=""
    runtime_arg=""
    shift 2
    for arg in "$@"; do
      if [ "$arg" = "--fresh" ]; then
        fresh=1
      elif [ -z "$devtype_arg" ]; then
        devtype_arg="$arg"
      else
        runtime_arg="$arg"
      fi
    done
    runtime="${runtime_arg:-$(xcrun simctl list -j runtimes | python3 -c '
import json, sys
rs = [r["identifier"] for r in json.load(sys.stdin)["runtimes"]
      if r.get("isAvailable") and "iOS" in r["identifier"]]
print(rs[-1])')}"
    # Default device type: the newest iPhone the chosen runtime supports.
    # A runtime's supportedDeviceTypes list is ordered newest-first (unlike
    # the global devicetypes list, which has no useful ordering).
    devtype="${devtype_arg:-$(xcrun simctl list -j runtimes | python3 -c '
import json, sys
rt = sys.argv[1]
for r in json.load(sys.stdin)["runtimes"]:
    if r["identifier"] == rt:
        ts = [t["identifier"] for t in r.get("supportedDeviceTypes", [])
              if "iPhone" in t["identifier"] and "SE" not in t["identifier"]]
        print(ts[0])
        break' "$runtime")}"
    if [ "$fresh" = 1 ]; then
      while IFS=$'\t' read -r udid _name _dt _rt _st; do
        [ -n "$udid" ] || continue
        remove_device "$udid"
      done <<EOF
$(list_mine)
EOF
    fi
    existing="$(list_mine || true)"
    out=""
    for i in $(seq 1 "$count"); do
      name="$prefix-$i"
      udid=""
      reused=false
      while IFS=$'\t' read -r u n dt rt _st; do
        [ -n "$u" ] || continue
        [ "$n" = "$name" ] || continue
        if [ "$dt" = "$devtype" ] && [ "$rt" = "$runtime" ]; then
          udid="$u"; reused=true
        else
          remove_device "$u"   # wrong shape for this run: replace it
        fi
      done <<EOF
$existing
EOF
      if [ -z "$udid" ]; then
        udid="$(xcrun simctl create "$name" "$devtype" "$runtime")"
      fi
      xcrun simctl bootstatus "$udid" -b >/dev/null
      scratch=".qa-loop/scratch/$name"
      mkdir -p "$scratch"
      [ -n "$out" ] && out+=","
      out+="{\"name\":\"$name\",\"udid\":\"$udid\",\"scratch\":\"$scratch\",\"reused\":$reused}"
    done
    # Leftovers of OURS beyond <count> (a previous wider run) are removed.
    while IFS=$'\t' read -r udid name _dt _rt _st; do
      [ -n "$udid" ] || continue
      idx="${name##*-}"
      case "$idx" in
        (*[!0-9]*) continue;;
      esac
      if [ "$idx" -gt "$count" ]; then
        remove_device "$udid"
      fi
    done <<EOF
$(list_mine)
EOF
    manifest="{\"workers\":[$out]}"
    mkdir -p ./.qa-loop/scratch
    printf '%s\n' "$manifest" > ./.qa-loop/scratch/workers.json
    echo "$manifest"
    ;;
  *)
    echo "unknown command: $cmd" >&2; exit 1;;
esac
