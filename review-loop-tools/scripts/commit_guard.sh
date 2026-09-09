#!/usr/bin/env bash
# Optional review-loop commit guard.
# Usage: commit_guard.sh [loop-dir]   (hooks pass .review-loop / .qa-loop)
# Env knobs (set in the repo/session, not committed):
#   REVIEW_LOOP_MAX_DIFF  - max staged changed lines allowed (default: unlimited)
#   REVIEW_LOOP_TEST_CMD  - test command that must pass before a commit is allowed
# Exit non-zero to block the tool call.
set -euo pipefail

loopdir="${1:-}"

# Read the intended command from stdin if provided.
input="$(cat 2>/dev/null || true)"
cmd=""
if command -v jq >/dev/null 2>&1 && [ -n "$input" ]; then
  cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
fi

# Staging discipline — active only while a loop is live (.phase exists).
# The loop-dir .gitignore allowlist decides what belongs in git; -A/-f/
# directory adds are how scratch enters history (measured: a committed
# "fragments 2/" and a tracked .pyc in one host repo). Stage named files.
if [ -n "$loopdir" ] && [ -f "$loopdir/.phase" ]; then
  case "$cmd" in
    *"git add"*)
      ldre="$(printf '%s' "$loopdir" | sed 's/\./\\./g')"
      if printf '%s' "$cmd" | grep -qE 'git add[^|;&]*[[:space:]](-A|--all)([[:space:]]|$)'; then
        echo "commit_guard: 'git add -A/--all' is blocked during a loop — stage the exact files you changed by path" >&2
        exit 2
      fi
      if printf '%s' "$cmd" | grep -qE 'git add[^|;&]*[[:space:]](-f|--force)([[:space:]]|$)'; then
        echo "commit_guard: 'git add -f' is blocked during a loop — if the allowlist ignores it, it is scratch and stays out of git" >&2
        exit 2
      fi
      if printf '%s' "$cmd" | grep -qE 'git add[^|;&]*[[:space:]]\.(/)?([[:space:]]|$|;)'; then
        echo "commit_guard: 'git add .' is blocked during a loop — stage the exact files you changed by path" >&2
        exit 2
      fi
      if printf '%s' "$cmd" | grep -qE "git add[^|;&]*[[:space:]](\./)?${ldre}(/)?([[:space:]]|\$|;)"; then
        echo "commit_guard: directory-adding ${loopdir} is blocked — add its conclusion files by name (REPORT.md, ledger.json, rounds.md, ...)" >&2
        exit 2
      fi
      ;;
  esac
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
