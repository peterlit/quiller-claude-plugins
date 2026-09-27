#!/usr/bin/env bash
# PreToolUse (Agent) hook. Two jobs:
# 1. Stamp ":dispatched" on the phase marker when a dispatch happens during a
#    loop phase (no stamping turn; no stamping without dispatching).
# 2. The session-size gate at the FIRST dispatch of a loop: prompt-time
#    checks miss "build the feature, then run the loop" sessions (measured:
#    20 orchestrator turns at 217K context, unwarned, ~500K wasted). If the
#    transcript exceeds the threshold and no confirmation marker exists, the
#    dispatch is blocked once with instructions; briefs/.session-ok records
#    the go-ahead for the rest of the loop.
# 3. Count LIVE dispatches in briefs/.dispatched: two agents may run at once
#    (a panel-verifier alongside an implementer — the skill allows it), and
#    with a single-bit marker the FIRST return unmarked the second, after
#    which the Stop hook blocked ordinary turns (measured: three times in
#    one run, again the next). The SubagentStop hook decrements and strips
#    the suffix only when the count reaches zero.
#    The COUNT is the source of truth; the ":dispatched" suffix is its
#    display. Every dispatch made while a loop phase is live is counted —
#    under ":waiting:" too, and on top of whatever the count already is.
#    Measured: the closeout implementer was dispatched while the phase said
#    ":waiting:panel-final" (the skill prescribes exactly that), went
#    uncounted, and the next agent's return took the count 1 -> 0 and
#    stripped the mark with the implementer still running. A phase write
#    can erase the suffix; it cannot erase the count, and the Stop hook
#    reads the count.
# 4. Record the dispatch in feedback/dispatches.jsonl (start time, agent,
#    session size). The SubagentStop hook records the return, so the run
#    summary carries wall-clock per dispatch at no token cost (measured: one
#    field agent hand-timed every dispatch, the other had no timing at all).
#    A dispatch the gate BLOCKS is not recorded — it did not happen.
# Usage: dispatch_stamp.sh <loop-dir> [threshold_mb]   (default 2)
set -euo pipefail
d="${1:-.review-loop}"; thr="${2:-2}"
input="$(cat 2>/dev/null || true)"
[ -f "$d/.phase" ] || exit 0
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
logstart() {
  printf '%s' "$input" | python3 "$here/field_log.py" dispatch-start "$d" \
    >/dev/null 2>&1 || true
}
# bump <assumed>: add one live dispatch. <assumed> is what a MISSING or
# unreadable count file stands for — 1 under ":dispatched" (a pre-0.14
# marker means one agent is already live), 0 otherwise.
bump() {
  python3 - "$d/briefs/.dispatched" "$1" <<'PYEOF'
import fcntl, os, sys
p, assumed = sys.argv[1], int(sys.argv[2])
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "a+") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)
    fh.seek(0)
    raw = fh.read().strip()
    try: n = int(raw) if raw else assumed
    except ValueError: n = assumed
    fh.seek(0); fh.truncate(); fh.write(f"{max(0, n) + 1}\n")
PYEOF
}
p="$(cat "$d/.phase")"
case "$p" in
  round*|seed*) : ;;
  *) exit 0 ;;
esac
case "$p" in
  *:waiting:*)
    # The marker is the orchestrator's; the dispatch is still a dispatch.
    bump 0; logstart; exit 0 ;;
  *:dispatched)
    # Already marked: another live dispatch — count it and keep the mark.
    bump 1; logstart; exit 0 ;;
esac
if [ ! -f "$d/briefs/.session-ok" ]; then
  if ! python3 - "$input" "$thr" <<'PYEOF'
import json, os, sys
try:
    dd = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
tp = dd.get("transcript_path", "") or ""
size = os.path.getsize(tp) if tp and os.path.exists(tp) else 0
sys.exit(1 if size / 1048576 > float(sys.argv[2]) else 0)
PYEOF
  then
    python3 "$here/field_log.py" anomaly "$d" session-gate-blocked \
      "first dispatch blocked: session transcript over ${thr} MB" \
      --source dispatch_stamp.sh >/dev/null 2>&1 || true
    echo "dispatch_stamp: this session's transcript exceeds ${thr} MB — loop plumbing costs ~3x here (measured 8.5M vs 2.6M over 22 rounds). Confirm with the human: restart the loop in a FRESH session, or proceed here by running \`mkdir -p $d/briefs && touch $d/briefs/.session-ok\` and re-dispatching." >&2
    exit 2
  fi
  mkdir -p "$d/briefs"
  touch "$d/briefs/.session-ok"
fi
logstart
printf '%s:dispatched\n' "$p" > "$d/.phase"
# On top of the current count, never a reset to 1: an agent counted under
# ":waiting:" may still be running when the phase is rewritten bare.
bump 0
exit 0
