#!/usr/bin/env bash
# Optional review-loop commit guard.
# Env knobs (set in the repo/session, not committed):
#   REVIEW_LOOP_MAX_DIFF  - max staged changed lines allowed (default: unlimited)
#   REVIEW_LOOP_TEST_CMD  - test command that must pass before a commit is allowed
# Exit non-zero to block the tool call.
set -euo pipefail

# Only act on git commits. Read the intended command from stdin if provided.
input="$(cat 2>/dev/null || true)"
cmd=""
if command -v jq >/dev/null 2>&1 && [ -n "$input" ]; then
  cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
fi
case "$cmd" in
  *"git commit"*) : ;;      # a commit — run the checks below
  "" ) : ;;                 # unknown input shape — fail open, allow
  * ) exit 0 ;;             # some other bash command — allow
esac

if [ -n "${REVIEW_LOOP_MAX_DIFF:-}" ]; then
  lines="$(git diff --cached --numstat | awk '{a+=$1; d+=$2} END {print a+d+0}')"
  if [ "${lines:-0}" -gt "$REVIEW_LOOP_MAX_DIFF" ]; then
    echo "commit_guard: staged diff ${lines} lines exceeds REVIEW_LOOP_MAX_DIFF=${REVIEW_LOOP_MAX_DIFF}" >&2
    exit 2
  fi
fi

if [ -n "${REVIEW_LOOP_TEST_CMD:-}" ]; then
  if ! bash -c "$REVIEW_LOOP_TEST_CMD"; then
    echo "commit_guard: tests failed (REVIEW_LOOP_TEST_CMD), blocking commit" >&2
    exit 2
  fi
fi
exit 0
