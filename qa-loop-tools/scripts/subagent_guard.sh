#!/usr/bin/env bash
# SubagentStop contract validator for the review/qa loops.
# While a round is in its review/testing phase, verify every fragment written
# so far is valid: LEDGER fragments need a findings array whose entries carry
# id/severity/current_status; *.results.json fragments need a results array of
# {tc, status} entries. A malformed fragment blocks the subagent from finishing
# (exit 2) so it fixes its own output, instead of costing the orchestrator a
# full re-dispatch round-trip.
set -euo pipefail
input="$(cat 2>/dev/null || true)"
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=(.review-loop .qa-loop)
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Record the return in feedback/dispatches.jsonl (the PreToolUse hook
# recorded the start): wall-clock per dispatch for the run summary.
# field_log.py records only while a loop phase is live and never fails.
for d in "${dirs[@]}"; do
  [ -f "$d/.phase" ] || continue
  printf '%s' "$input" | python3 "$here/field_log.py" dispatch-end "$d" \
    >/dev/null 2>&1 || true
done

# A subagent just finished. Decrement the LIVE-dispatch count kept by
# dispatch_stamp.sh (briefs/.dispatched) and strip the ":dispatched" suffix
# only when it reaches zero — with a single-bit marker the first of two
# concurrent agents to return unmarked the other, and the Stop hook then
# blocked ordinary turns (measured). The count is decremented whenever a
# loop phase is live, WHATEVER the suffix says: a phase write that erased
# the suffix used to strand the count, and a dispatch made under
# ":waiting:" is counted too. A missing count file means one live dispatch
# under ":dispatched" (pre-0.14 state) and none otherwise.
# ":waiting:<reason>" is NOT touched — it is the orchestrator's to clear.
for d in "${dirs[@]}"; do
  if [ -f "$d/.phase" ]; then
    ph="$(cat "$d/.phase")"
    case "$ph" in
      round*|seed*)
        assumed=0
        case "$ph" in *:dispatched) assumed=1 ;; esac
        left="$(python3 - "$d/briefs/.dispatched" "$assumed" <<'PYEOF'
import fcntl, os, sys
p, assumed = sys.argv[1], int(sys.argv[2])
try:
    with open(p, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        raw = fh.read().strip()
        try: n = int(raw) if raw else assumed
        except ValueError: n = assumed
        n = max(0, n - 1)
        fh.seek(0); fh.truncate(); fh.write(f"{n}\n")
except FileNotFoundError:
    n = 0
print(n)
PYEOF
)"
        if [ "${left:-0}" -le 0 ]; then
          case "$ph" in *:dispatched)
            sed -i '' 's/:dispatched$//' "$d/.phase" 2>/dev/null \
              || sed -i 's/:dispatched$//' "$d/.phase" ;;
          esac
        fi ;;
    esac
  fi
done

for d in "${dirs[@]}"; do
  [ -f "$d/.phase" ] || continue
  case "$(cat "$d/.phase")" in
    *review*|*testing*) : ;;
    *) continue ;;
  esac
  [ -d "$d/fragments" ] || continue
  python3 - "$d/fragments" "$(cat "$d/.phase")" <<'EOF' || exit 2
import json, os, re, sys, time
frag_dir = sys.argv[1]
# Closeout fragments must carry the suite counts — but only while the
# CLOSEOUT review is the phase in flight, so a closeout fragment left by an
# earlier pass never blocks a later reviewer.
in_closeout = "closeout" in (sys.argv[2] if len(sys.argv) > 2 else "")
CLOSEOUT_NAME = re.compile(r"round-[A-Za-z0-9._-]*closeout[A-Za-z0-9._-]*\.json")

def check_suites(data):
    """`suites`: {"<target>": {"executed": n, "failed": n, "skipped": n}}.
    The report's Closeout table renders from it; "green" once hid 8 of 13 UI
    tests skipped, and a run that reported 29 executed / 14 skipped only in
    prose left the table empty (measured, twice)."""
    if "suites" not in data:
        raise ValueError(
            "closeout fragment has no top-level 'suites' — add "
            '"suites": {"<test target>": {"executed": n, "failed": n, '
            '"skipped": n}} with one entry per suite you ran; if you ran '
            'none, "suites": {} plus "suites_note": "<why>"')
    suites = data["suites"]
    if not isinstance(suites, dict):
        raise ValueError("'suites' must be an object of target -> counts")
    if not suites:
        note = data.get("suites_note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("'suites' is empty: add \"suites_note\": \"<why no "
                             "suite ran>\" (e.g. no test targets; fold-in only)")
    for name, t in suites.items():
        if not isinstance(t, dict):
            raise ValueError(f"suites[{name!r}] must be an object")
        for k in ("executed", "failed", "skipped"):
            v = t.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"suites[{name!r}].{k} must be a non-negative "
                                 f"integer, got {v!r}")
VALID_TC = {"passed", "failed", "blocked", "skipped"}
# Only police files the merge will actually consume; orchestrator briefs and
# other artifacts in this directory are not ours to validate (they belong in
# briefs/ anyway). Panel artifacts (candidates, verified, raw) live in the
# fragments/panel/ SUBDIR, outside this flat scan by construction — no name
# exemption here, so a genuine ledger fragment can never dodge policing by
# its filename.
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
            if in_closeout and CLOSEOUT_NAME.fullmatch(name):
                check_suites(data)
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
                if is_new and "evidence" in f:
                    ev = f["evidence"]
                    ok = (isinstance(ev, list) and ev and all(isinstance(x, str) for x in ev)) or (
                        isinstance(ev, dict) and any(ev.get(k) for k in ("screenshots", "repro", "measurements")))
                    if not ok:
                        raise ValueError(
                            f"new finding {f['id']}: 'evidence' must be a non-empty "
                            f"list of file:line strings, or an object with non-empty "
                            f"screenshots/repro/measurements — got {ev!r}")
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
              f"current_status; results fragments need tc + status; a "
              f"closeout fragment also needs suites.",
              file=sys.stderr)
        sys.exit(1)
EOF
done
exit 0
