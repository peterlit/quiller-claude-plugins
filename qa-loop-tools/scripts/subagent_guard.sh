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

# A subagent just finished: the phase's "dispatched" state is over. Strip the
# suffix so the Stop hook can again tell "waiting" from "forgot to act".
for d in .review-loop .qa-loop; do
  if [ -f "$d/.phase" ]; then
    case "$(cat "$d/.phase")" in
      *:dispatched) sed -i '' 's/:dispatched$//' "$d/.phase" 2>/dev/null \
                    || sed -i 's/:dispatched$//' "$d/.phase" ;;
    esac
  fi
done

for d in .review-loop .qa-loop; do
  [ -f "$d/.phase" ] || continue
  case "$(cat "$d/.phase")" in
    *review*|*testing*) : ;;
    *) continue ;;
  esac
  [ -d "$d/fragments" ] || continue
  python3 - "$d/fragments" <<'EOF' || exit 2
import json, os, re, sys, time
frag_dir = sys.argv[1]
VALID_TC = {"passed", "failed", "blocked", "skipped"}
# Only police files the merge will actually consume; orchestrator briefs and
# other artifacts in this directory are not ours to validate (they belong in
# briefs/ anyway).
FRAGMENT_NAME = re.compile(r"(seed|round-[A-Za-z0-9._-]+)\.json")
known = set()
ledger_path = os.path.join(os.path.dirname(frag_dir), "ledger.json")
if os.path.exists(ledger_path):
    try:
        with open(ledger_path) as fh:
            known = {f.get("id") for f in json.load(fh).get("findings", [])}
    except Exception:
        pass
for name in sorted(os.listdir(frag_dir)):
    if not FRAGMENT_NAME.fullmatch(name):
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
                for k in ("id", "current_status"):
                    if not f.get(k):
                        raise ValueError(
                            f"finding {f.get('id', '<no id>')} missing '{k}'")
                is_new = f.get("id") not in known
                if is_new and not f.get("severity"):
                    raise ValueError(f"new finding {f['id']} missing 'severity'")
                if is_new and not f.get("claim"):
                    raise ValueError(
                        f"new finding {f['id']} missing 'claim' — state the "
                        f"defect and its concrete failure mode; the ledger "
                        f"must stand alone")
                for e in f.get("status_history") or []:
                    if not isinstance(e.get("round"), int):
                        raise ValueError(
                            f"finding {f.get('id')}: status_history round "
                            f"must be an integer, got {e.get('round')!r} "
                            f"(or omit status_history — the merge adds it)")
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
