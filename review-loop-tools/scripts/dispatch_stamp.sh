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
# Usage: dispatch_stamp.sh <loop-dir> [threshold_mb]   (default 2)
set -euo pipefail
d="${1:-.review-loop}"; thr="${2:-2}"
input="$(cat 2>/dev/null || true)"
[ -f "$d/.phase" ] || exit 0
p="$(cat "$d/.phase")"
case "$p" in
  *:waiting:*) exit 0 ;;
  *:dispatched)
    # Already marked: a SECOND live dispatch — count it and keep the mark.
    python3 - "$d/briefs/.dispatched" <<'PYEOF'
import fcntl, os, sys
p = sys.argv[1]
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "a+") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)
    fh.seek(0)
    try: n = int((fh.read() or "1").strip() or 1)
    except ValueError: n = 1
    fh.seek(0); fh.truncate(); fh.write(f"{n + 1}\n")
PYEOF
    exit 0 ;;
  round*|seed*) : ;;
  *) exit 0 ;;
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
    echo "dispatch_stamp: this session's transcript exceeds ${thr} MB — loop plumbing costs ~3x here (measured 8.5M vs 2.6M over 22 rounds). Confirm with the human: restart the loop in a FRESH session, or proceed here by running \`mkdir -p $d/briefs && touch $d/briefs/.session-ok\` and re-dispatching." >&2
    exit 2
  fi
  mkdir -p "$d/briefs"
  touch "$d/briefs/.session-ok"
fi
printf '%s:dispatched\n' "$p" > "$d/.phase"
mkdir -p "$d/briefs"
printf '1\n' > "$d/briefs/.dispatched"
exit 0
