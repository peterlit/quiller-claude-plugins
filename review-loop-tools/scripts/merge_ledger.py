#!/usr/bin/env python3
"""Deterministically merge a round's LEDGER fragment into the loop ledger.

Usage:
  merge_ledger.py <ledger.json> <fragment.json> <round-number>
  merge_ledger.py resolve <ledger.json> <finding-id> <status> <round> [note]

Merge mode: the fragment is {"findings": [...]}. Existing findings are
updated (scalar fields overwritten, evidence lists unioned, status_history
appended for this round); unknown findings are added with first_seen_round
defaulting to this round. Findings absent from the fragment are left
untouched. Prints a terse JSON summary on stdout.

Resolve mode: records a human/orchestrator decision on one finding — e.g.
wontfix for a proposal the human already declined — appending to
status_history and stamping the note, so decided issues never need
hand-editing and never linger open.
"""
import json, sys

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

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "resolve":
        resolve(sys.argv[2:])
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
