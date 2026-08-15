#!/usr/bin/env python3
"""Merge a tester chunk's per-test-case results into the round coverage manifest.

Usage: merge_coverage.py <coverage.json> <results-fragment.json> <round-number>

Fragment schema:
  {"results": [{"tc": "TC-2.1", "status": "passed|failed|blocked|skipped", "reason": ""}]}
coverage.json schema:
  {"rounds": {"<round>": {"TC-2.1": {"status": "...", "reason": "..."}}}}
Later results for the same TC in the same round overwrite earlier ones (re-runs).
"""
import json, os, sys

VALID = {"passed", "failed", "blocked", "skipped"}

def die(msg):
    print(f"merge_coverage: {msg}", file=sys.stderr)
    sys.exit(1)

def main():
    if len(sys.argv) != 4:
        die("usage: merge_coverage.py <coverage.json> <results-fragment.json> <round>")
    cov_path, frag_path = sys.argv[1], sys.argv[2]
    try:
        rnd = int(sys.argv[3])
    except ValueError:
        die(f"round must be an integer, got '{sys.argv[3]}'")
    cov = {"rounds": {}}
    if os.path.exists(cov_path):
        with open(cov_path) as fh:
            cov = json.load(fh)
    with open(frag_path) as fh:
        frag = json.load(fh)
    results = frag.get("results")
    if not isinstance(results, list):
        die(f"{frag_path} has no results array")
    bucket = cov.setdefault("rounds", {}).setdefault(str(rnd), {})
    for r in results:
        tc, status = r.get("tc"), r.get("status")
        if not tc or status not in VALID:
            die(f"bad result entry {r!r} (need tc + status in {sorted(VALID)})")
        bucket[tc] = {"status": status, "reason": r.get("reason", "")}
        if r.get("persona"):
            bucket[tc]["persona"] = r["persona"]
    with open(cov_path, "w") as fh:
        json.dump(cov, fh, indent=2)
        fh.write("\n")
    print(json.dumps({"round": rnd, "recorded": len(results),
                      "round_total": len(bucket)}))

if __name__ == "__main__":
    main()
