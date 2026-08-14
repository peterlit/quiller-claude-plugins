#!/usr/bin/env python3
"""Deterministically merge a round's LEDGER fragment into the loop ledger.

Usage: merge_ledger.py <ledger.json> <fragment.json> <round-number>

The fragment is {"findings": [...]}. Existing findings are updated (scalar
fields overwritten, evidence lists unioned, status_history appended for this
round); unknown findings are added with first_seen_round defaulting to this
round. Findings absent from the fragment are left untouched (targeted passes
do not re-report everything). Prints a terse JSON summary on stdout.
"""
import json, sys

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
