#!/usr/bin/env bash
# UserPromptSubmit hook: when a prompt invokes a loop skill, measure this
# session's transcript and warn if it is large. Measured: the identical
# plumbing request costs ~3.3x more in a 550K-context session than in a fresh
# one — the single largest lever, and it needs no code. Usage:
#   session_guard.sh [threshold_mb]   (default 2)
set -euo pipefail
thr="${1:-2}"
input="$(cat 2>/dev/null || true)"
python3 - "$input" "$thr" <<'PYEOF'
import json, os, re, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
prompt = d.get("prompt", "") or ""
if not re.search(r"review[- ]loop|qa[- ]loop", prompt, re.I):
    sys.exit(0)
tp = d.get("transcript_path", "") or ""
size = os.path.getsize(tp) if tp and os.path.exists(tp) else 0
mb, thr = size / 1048576, float(sys.argv[2])
if mb > thr:
    print(f"LOOP COST WARNING: this session's transcript is {mb:.1f} MB (threshold {thr:g} MB). "
          f"Measured: loop plumbing requests cost ~3x more in a large session — over a 22-round "
          f"history that was 8.5M vs 2.6M tokens. Start the loop in a FRESH session unless the "
          f"human accepts the cost; state the choice at the gate.")
else:
    print(f"loop session check: transcript {mb:.1f} MB — fine for a loop.")
PYEOF
exit 0
