#!/usr/bin/env bash
# Dumb NFR sampler for the qa-loop. Records raw timestamped samples of the app
# process; the ux-tester interprets them (so thresholds stay debatable findings,
# not baked-in policy). Simulator apps run as native macOS processes, so host
# tools see them directly — no proxy or Instruments needed.
#
# Usage: nfr_sampler.sh <pid> <outfile.jsonl> [interval_seconds]
# Emits one JSON object per line:
#   {"ts":<epoch>,"rss_mb":<resident MB>,"cpu_pct":<%cpu>,"net_in_bytes":N,"net_out_bytes":N}
# Exits when the target process does. net_* fields are 0 if nettop is
# unavailable or unreadable.
set -euo pipefail

pid="${1:?usage: nfr_sampler.sh <pid> <outfile.jsonl> [interval_seconds]}"
out="${2:?usage: nfr_sampler.sh <pid> <outfile.jsonl> [interval_seconds]}"
interval="${3:-2}"

mkdir -p "$(dirname "$out")"

while kill -0 "$pid" 2>/dev/null; do
  ts="$(date +%s)"
  psout="$(ps -o rss=,pcpu= -p "$pid" 2>/dev/null || true)"
  [ -z "$psout" ] && break
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

  printf '{"ts":%s,"rss_mb":%s,"cpu_pct":%s,"net_in_bytes":%s,"net_out_bytes":%s}\n' \
    "$ts" "$rss_mb" "${cpu:-0}" "${net_in:-0}" "${net_out:-0}" >> "$out"
  sleep "$interval"
done
