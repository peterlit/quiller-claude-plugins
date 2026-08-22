#!/usr/bin/env bash
# PreToolUse (Agent) hook: when the orchestrator dispatches a subagent while a
# loop phase is in flight, stamp ":dispatched" on the marker automatically.
# Removes a plumbing turn per dispatch, and makes it impossible to stamp
# without dispatching. Pass loop dirs as args (default both).
set -euo pipefail
cat >/dev/null 2>&1 || true
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=(.review-loop .qa-loop)
for d in "${dirs[@]}"; do
  [ -f "$d/.phase" ] || continue
  p="$(cat "$d/.phase")"
  case "$p" in
    *:dispatched|*:waiting:*) ;;
    round*|seed*) printf '%s:dispatched\n' "$p" > "$d/.phase" ;;
  esac
done
exit 0
