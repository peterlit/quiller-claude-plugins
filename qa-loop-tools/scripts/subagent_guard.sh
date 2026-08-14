#!/usr/bin/env bash
# SubagentStop contract validator for the review/qa loops.
# While a round is in its review/testing phase, verify every LEDGER fragment
# written so far is valid JSON with a findings array. A malformed fragment
# blocks the subagent from finishing (exit 2) so it fixes its own output,
# instead of costing the orchestrator a full re-dispatch round-trip.
set -euo pipefail
cat >/dev/null 2>&1 || true   # drain stdin; the payload isn't needed

for d in .review-loop .qa-loop; do
  [ -f "$d/.phase" ] || continue
  case "$(cat "$d/.phase")" in
    *review*|*testing*) : ;;
    *) continue ;;
  esac
  [ -d "$d/fragments" ] || continue
  python3 - "$d/fragments" <<'EOF' || exit 2
import json, os, sys, time
frag_dir = sys.argv[1]
for name in sorted(os.listdir(frag_dir)):
    if not name.endswith(".json"):
        continue
    path = os.path.join(frag_dir, name)
    try:
        with open(path) as fh:
            data = json.load(fh)
        if not isinstance(data.get("findings"), list):
            raise ValueError("no findings array")
    except Exception as e:
        # Grace period: a parallel worker may be mid-write.
        if time.time() - os.path.getmtime(path) < 10:
            continue
        print(f"subagent_guard: fragment {path} is invalid ({e}). Write a "
              f"valid JSON fragment with a findings array — write to a temp "
              f"file, then mv it into place.", file=sys.stderr)
        sys.exit(1)
EOF
done
exit 0
