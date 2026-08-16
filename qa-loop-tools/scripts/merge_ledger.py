#!/usr/bin/env python3
"""Deterministically merge a round's LEDGER fragment into the loop ledger.

Usage:
  merge_ledger.py <ledger.json> <fragment.json> <round-number>
  merge_ledger.py resolve <ledger.json> <finding-id> <status> <round> [note]
  merge_ledger.py set-round <ledger.json> <round> [sha]
  merge_ledger.py open <ledger.json> [auto|proposal|all]
  merge_ledger.py archive <loop-dir> [name]

Merge mode: the fragment is {"findings": [...]}. Existing findings are
updated (scalar fields overwritten, evidence lists unioned, status_history
appended for this round); unknown findings are added with first_seen_round
defaulting to this round. Findings absent from the fragment are left
untouched. Prints a terse JSON summary on stdout.

Resolve mode: records a human/orchestrator decision on one finding — e.g.
wontfix for a proposal the human already declined — appending to
status_history and stamping the note, so decided issues never need
hand-editing and never linger open.

set-round: round bookkeeping without hand-editing — sets "round" and, when a
sha is given, whichever of round_start_sha/build_sha the ledger uses.

open: prints the open/partial findings (status_history stripped) as JSON —
the sanctioned way to build an implementer brief; write it into briefs/.

archive: moves a finished loop's state (ledger.json, rounds.md, REPORT.md,
coverage.json, fragments/, briefs/, .phase) into <loop-dir>/archive/<name>/,
so a fresh loop starts clean instead of piling files at one level. Default
name: timestamp plus the ledger's sha.
"""
import json, os, sys

VALID_STATUS = {"open", "partial", "fixed", "wontfix", "disputed"}

def resolve(args):
    if len(args) < 4:
        print("usage: merge_ledger.py resolve <ledger.json> <finding-id> "
              "<open|partial|fixed|wontfix|disputed> <round> [note]",
              file=sys.stderr)
        sys.exit(2)
    path, fid, status = args[0], args[1], args[2]
    if status not in VALID_STATUS:
        print(f"merge_ledger: invalid status '{status}' "
              f"(want one of {sorted(VALID_STATUS)})", file=sys.stderr)
        sys.exit(1)
    try:
        rnd = int(args[3])
    except ValueError:
        print(f"merge_ledger: round must be an integer, got '{args[3]}'",
              file=sys.stderr)
        sys.exit(1)
    note = args[4] if len(args) > 4 else ""
    with open(path) as fh:
        ledger = json.load(fh)
    for f in ledger.get("findings", []):
        if f.get("id") == fid:
            hist = f.setdefault("status_history", [])
            if not any(e.get("round") == rnd and e.get("status") == status
                       for e in hist):
                hist.append({"round": rnd, "status": status})
            f["current_status"] = status
            if note:
                prev = (f.get("note") or "").strip()
                stamp = f"RESOLVED (round {rnd}): {note}"
                f["note"] = f"{prev} | {stamp}" if prev else stamp
            with open(path, "w") as out:
                json.dump(ledger, out, indent=2)
                out.write("\n")
            print(json.dumps({"id": fid, "status": status, "round": rnd}))
            return
    print(f"merge_ledger: no finding with id '{fid}'", file=sys.stderr)
    sys.exit(1)

def union_evidence(old, new):
    if not isinstance(old, dict):
        old = {}
    if not isinstance(new, dict):
        return old
    out = dict(old)
    for k, v in new.items():
        if isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = v
    return out

def set_round(args):
    if len(args) < 2:
        print("usage: merge_ledger.py set-round <ledger.json> <round> [sha]",
              file=sys.stderr)
        sys.exit(2)
    path = args[0]
    try:
        rnd = int(args[1])
    except ValueError:
        print(f"merge_ledger: round must be an integer, got '{args[1]}'",
              file=sys.stderr)
        sys.exit(1)
    sha = args[2] if len(args) > 2 else None
    with open(path) as fh:
        ledger = json.load(fh)
    ledger["round"] = rnd
    out = {"round": rnd}
    if sha:
        key = ("build_sha" if "build_sha" in ledger
               and "round_start_sha" not in ledger else "round_start_sha")
        ledger[key] = sha
        out[key] = sha
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    print(json.dumps(out))

def open_findings(args):
    if len(args) < 1:
        print("usage: merge_ledger.py open <ledger.json> [auto|proposal|all]",
              file=sys.stderr)
        sys.exit(2)
    path = args[0]
    routing = args[1] if len(args) > 1 else "all"
    if routing not in ("auto", "proposal", "all"):
        print(f"merge_ledger: routing filter must be auto|proposal|all, "
              f"got '{routing}'", file=sys.stderr)
        sys.exit(1)
    with open(path) as fh:
        ledger = json.load(fh)
    sel = []
    for f in ledger.get("findings", []):
        if f.get("current_status") not in ("open", "partial"):
            continue
        if routing != "all" and f.get("routing", "auto") != routing:
            continue
        sel.append({k: v for k, v in f.items() if k != "status_history"})
    print(json.dumps({"findings": sel}, indent=2))

def archive(args):
    import datetime, shutil
    if len(args) < 1:
        print("usage: merge_ledger.py archive <loop-dir> [name]",
              file=sys.stderr)
        sys.exit(2)
    loop_dir = args[0]
    sha = ""
    ledger_path = os.path.join(loop_dir, "ledger.json")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path) as fh:
                led = json.load(fh)
            sha = (led.get("round_start_sha") or led.get("build_sha") or "")[:7]
        except Exception:
            pass
    name = (args[1] if len(args) > 1 else
            datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            + (f"-{sha}" if sha else ""))
    dest = os.path.join(loop_dir, "archive", name)
    moved = []
    for item in ("ledger.json", "rounds.md", "REPORT.md", "coverage.json",
                 "fragments", "briefs", ".phase"):
        src = os.path.join(loop_dir, item)
        if os.path.exists(src):
            os.makedirs(dest, exist_ok=True)
            shutil.move(src, os.path.join(dest, item))
            moved.append(item)
    if not moved:
        print(f"merge_ledger: nothing to archive in {loop_dir}",
              file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"archived_to": dest, "moved": moved}))

def main():
    verbs = {"resolve": resolve, "set-round": set_round,
             "open": open_findings, "archive": archive}
    if len(sys.argv) >= 2 and sys.argv[1] in verbs:
        verbs[sys.argv[1]](sys.argv[2:])
        return
    ledger_path, frag_path, rnd = sys.argv[1], sys.argv[2], int(sys.argv[3])
    with open(ledger_path) as fh:
        ledger = json.load(fh)
    with open(frag_path) as fh:
        frag = json.load(fh)
    if not isinstance(frag.get("findings"), list):
        print(f"merge_ledger: {frag_path} has no findings array", file=sys.stderr)
        sys.exit(1)
    by_id = {f.get("id"): f for f in ledger.setdefault("findings", [])}
    updated = added = 0
    for nf in frag["findings"]:
        fid = nf.get("id")
        if not fid:
            print(f"merge_ledger: a finding in {frag_path} is missing an id",
                  file=sys.stderr)
            sys.exit(1)
        status = nf.get("current_status", "open")
        if fid in by_id:
            f = by_id[fid]
            for k, v in nf.items():
                if k in ("status_history", "first_seen_round", "evidence"):
                    continue
                f[k] = v
            if "evidence" in nf or "evidence" in f:
                f["evidence"] = union_evidence(f.get("evidence"), nf.get("evidence"))
            hist = f.setdefault("status_history", [])
            if not any(e.get("round") == rnd and e.get("status") == status
                       for e in hist):
                hist.append({"round": rnd, "status": status})
            f["current_status"] = status
            updated += 1
        else:
            nf.setdefault("first_seen_round", rnd)
            nf.setdefault("status_history", [{"round": rnd, "status": status}])
            nf["current_status"] = status
            by_id[fid] = nf
            ledger["findings"].append(nf)
            added += 1
    ledger["round"] = rnd
    with open(ledger_path, "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    print(json.dumps({"round": rnd, "updated": updated, "added": added,
                      "total": len(ledger["findings"])}))

if __name__ == "__main__":
    main()
