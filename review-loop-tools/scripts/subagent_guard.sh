#!/usr/bin/env bash
# SubagentStop contract validator for the review/qa loops.
# While a round is in its review/testing phase, verify every fragment written
# so far is valid: LEDGER fragments need a findings array whose entries carry
# id/severity/current_status; *.results.json fragments need a results array of
# {tc, status} entries. A malformed fragment blocks the subagent from finishing
# (exit 2) so it fixes its own output, instead of costing the orchestrator a
# full re-dispatch round-trip.
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
VALID_TC = {"passed", "failed", "blocked", "skipped"}
for name in sorted(os.listdir(frag_dir)):
    if not name.endswith(".json"):
        continue
    path = os.path.join(frag_dir, name)
    try:
        with open(path) as fh:
            data = json.load(fh)
        if name.endswith(".results.json"):
            results = data.get("results")
            if not isinstance(results, list):
                raise ValueError("no results array")
            for r in results:
                if not r.get("tc") or r.get("status") not in VALID_TC:
                    raise ValueError(f"bad result entry {r!r} "
                                     f"(need tc + status in {sorted(VALID_TC)})")
        else:
            findings = data.get("findings")
            if not isinstance(findings, list):
                raise ValueError("no findings array")
            for f in findings:
                for k in ("id", "severity", "current_status"):
                    if not f.get(k):
                        raise ValueError(
                            f"finding {f.get('id', '<no id>')} missing '{k}'")
    except Exception as e:
        # Grace period: a parallel worker may be mid-write.
        if time.time() - os.path.getmtime(path) < 10:
            continue
        print(f"subagent_guard: fragment {path} is invalid ({e}). Write a "
              f"valid JSON fragment — write to a temp file, then mv it into "
              f"place. LEDGER fragments need findings with id/severity/"
              f"current_status; results fragments need tc + status.",
              file=sys.stderr)
        sys.exit(1)
EOF
done
exit 0
