#!/usr/bin/env bash
# Stop-hook stall guard for the review/qa loops.
# Blocks the main agent from ending its turn while a loop round is in flight
# (phase marker starts with "round" or "seed") unless the marker says an
# agent is dispatched (":dispatched", stripped by the SubagentStop hook when
# the agent returns) or the orchestrator is honestly waiting on something
# that is not a subagent (":waiting:<reason>", cleared only by the
# orchestrator). Pass loop dirs as arguments so each plugin guards only its
# own loop (default: both). Zero-cost no-op when no loop is running.
set -euo pipefail
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=(.review-loop .qa-loop)

input="$(cat 2>/dev/null || true)"
# Don't re-block a continuation we already forced (prevents infinite loops).
if printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if d.get("stop_hook_active") else 1)' 2>/dev/null; then
  exit 0
fi

for d in "${dirs[@]}"; do
  if [ -f "$d/.phase" ]; then
    phase="$(cat "$d/.phase")"
    case "$phase" in
      *:waiting:*)
        # Honest non-subagent wait (backoff, a background task, a human).
        # The orchestrator clears it when it resumes.
        ;;
      *:dispatched)
        # An agent for this phase is dispatched and running — waiting is
        # legitimate. The SubagentStop hook strips this suffix when the agent
        # returns, so a turn that ends AFTER the result without acting is
        # still caught.
        ;;
      round*|seed*)
        echo "loop_guard: $d round in flight (phase: $phase). If you have NOT yet dispatched this phase's subagent, do so now — do not end the turn on a promise. If a subagent you already dispatched is still running in the background, do NOT dispatch a duplicate: say you are waiting for it and stop (the session resumes when it completes). If the loop is genuinely finished or waiting on the human, first update $d/.phase to 'done' or 'awaiting-human'." >&2
        exit 2
        ;;
    esac
  fi
done
exit 0
