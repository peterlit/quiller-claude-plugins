#!/usr/bin/env bash
# Dumb NFR sampler for the qa-loop. Records raw timestamped samples of the app
# process; the ux-tester interprets them (so thresholds stay debatable findings,
# not baked-in policy). Simulator apps run as native macOS processes, so host
# tools see them directly — no proxy or Instruments needed.
#
# Usage (primary — follows the app across relaunches, never self-exits;
# the orchestrator must stop it explicitly):
#   nfr_sampler.sh <udid> <bundle-id> <outfile.jsonl> [interval_seconds]
# Usage (legacy — pins one PID, exits when that process dies):
#   nfr_sampler.sh <pid> <outfile.jsonl> [interval_seconds]
#
# Emits one JSON object per line. Every record carries the pid (null while the
# app is not running), so post-hoc analysis can separate stints across
# relaunches and never misreads a relaunch as a memory drop:
#   {"ts":..,"pid":123,"rss_mb":..,"cpu_pct":..,"net_in_bytes":..,"net_out_bytes":..}
#   {"ts":..,"pid":null,"app_running":false}
# net_* fields are 0 if nettop is unavailable or unreadable.
set -euo pipefail

sample_pid() {  # $1=pid $2=outfile ; returns 1 if the pid vanished
  local pid="$1" out="$2" ts psout rss_kb cpu rss_mb net_in net_out netline
  ts="$(date +%s)"
  psout="$(ps -o rss=,pcpu= -p "$pid" 2>/dev/null || true)"
  [ -z "$psout" ] && return 1
  rss_kb="$(printf '%s' "$psout" | awk '{print $1}')"
  cpu="$(printf '%s' "$psout" | awk '{print $2}')"
  rss_mb="$(awk "BEGIN{printf \"%.1f\", ${rss_kb:-0}/1024}")"
  net_in=0; net_out=0
  if command -v nettop >/dev/null 2>&1; then
    netline="$(nettop -P -x -l 1 -p "$pid" -J bytes_in,bytes_out 2>/dev/null | tail -n 1 || true)"
    case "$netline" in
      *,*)
        net_in="$(printf '%s' "$netline" | awk -F, '{print $(NF-2)+0}')"
        net_out="$(printf '%s' "$netline" | awk -F, '{print $(NF-1)+0}')"
        ;;
    esac
  fi
  printf '{"ts":%s,"pid":%s,"rss_mb":%s,"cpu_pct":%s,"net_in_bytes":%s,"net_out_bytes":%s}\n' \
    "$ts" "$pid" "$rss_mb" "${cpu:-0}" "${net_in:-0}" "${net_out:-0}" >> "$out"
  return 0
}

case "${1:-}" in
  ''|*[!0-9]*) mode=bundle ;;
  *) mode=pid ;;
esac

if [ "$mode" = "pid" ]; then
  pid="${1:?usage: nfr_sampler.sh <pid> <outfile.jsonl> [interval]}"
  out="${2:?usage: nfr_sampler.sh <pid> <outfile.jsonl> [interval]}"
  interval="${3:-2}"
  mkdir -p "$(dirname "$out")"
  while kill -0 "$pid" 2>/dev/null; do
    sample_pid "$pid" "$out" || break
    sleep "$interval"
  done
else
  udid="${1:?usage: nfr_sampler.sh <udid> <bundle-id> <outfile.jsonl> [interval]}"
  bundle="${2:?usage: nfr_sampler.sh <udid> <bundle-id> <outfile.jsonl> [interval]}"
  out="${3:?usage: nfr_sampler.sh <udid> <bundle-id> <outfile.jsonl> [interval]}"
  interval="${4:-2}"
  mkdir -p "$(dirname "$out")"
  while :; do
    # Re-resolve the app PID each tick via launchctl on the simulator, so the
    # sampler follows the app across relaunches instead of dying with a PID.
    pid="$(xcrun simctl spawn "$udid" launchctl list 2>/dev/null \
      | awk -v b="UIKitApplication:$bundle[" 'index($3, b) == 1 {print $1; exit}')" || pid=""
    case "$pid" in
      ''|-|*[!0-9]*)
        printf '{"ts":%s,"pid":null,"app_running":false}\n' "$(date +%s)" >> "$out"
        ;;
      *)
        sample_pid "$pid" "$out" || true
        ;;
    esac
    sleep "$interval"
  done
fi
