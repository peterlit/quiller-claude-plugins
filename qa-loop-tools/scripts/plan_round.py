#!/usr/bin/env python3
"""Plan a qa round deterministically: select the test set and emit chunk manifests.

Usage: plan_round.py <loop-dir> <round> full|targeted
                     [--range <a>..<b>] [--workers N] [--max-tcs 5] [--repo <root>]

Inputs (all contracts the skill already establishes):
- TESTCASES.md: every test case starts a line with its id and tags, e.g.
      ### TC-2.1 [novice] [smoke] Checkout as a first-time user
  Tags: [novice] [power] [smoke] [perf]. A TC belongs to WF-<n> by its id.
- WORKFLOWS.md: one line per workflow naming the source paths it exercises:
      paths(WF-2): ios/App/Checkout/, Shared/Cart.swift
- ledger.json: open/partial auto-routed findings (their test_case / region)
  — fixes already rejected by fix review are skipped.

Targeted set = TCs of workflows whose paths intersect the diff in --range
               + TCs referenced by open/partial findings + [smoke] TCs.
Full set     = every TC.
Chunks: grouped by workflow, at most --max-tcs per dispatch (cost inside a
dispatch scales with screenshots x turns, so small chunks are cheaper than
big ones), assigned round-robin to workers. [perf] TCs are listed
separately for the perf lane. Also emits the cost estimate the Stage-1 gate
announces. Writes <loop-dir>/briefs/round-<N>-plan.json and prints it.
"""
import json, os, re, subprocess, sys

TC_RE = re.compile(r"^\s*(?:[-*#]+\s*)?(TC-(\d+)\.\d+)\b(.*)$")
TAG_RE = re.compile(r"\[(novice|power|smoke|perf)\]")
PATHS_RE = re.compile(r"^\s*paths\((WF-\d+)\)\s*:\s*(.+?)\s*$")

def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[2] not in ("full", "targeted"):
        print(__doc__, file=sys.stderr); sys.exit(2)
    loop, rnd, pass_type = a[0], int(a[1]), a[2]
    opt = {"--range": None, "--workers": "1", "--max-tcs": "5", "--repo": ".",
           "--turn-budget": "40"}
    flags = {"--lint": False, "--lax": False, "--allow-wide": False}
    i = 3
    while i < len(a):
        if a[i] in opt and i + 1 < len(a):
            opt[a[i]] = a[i + 1]; i += 2
        elif a[i] in flags:
            flags[a[i]] = True; i += 1
        else:
            i += 1
    workers, max_tcs = int(opt["--workers"]), int(opt["--max-tcs"])
    turn_budget = int(opt["--turn-budget"])

    tcs = []
    for line in open(os.path.join(loop, "TESTCASES.md"), encoding="utf-8"):
        m = TC_RE.match(line)
        if m:
            tags = set(TAG_RE.findall(m.group(3)))
            tcs.append({"tc": m.group(1), "wf": f"WF-{m.group(2)}",
                        "personas": sorted(tags & {"novice", "power"}) or ["unspecified"],
                        "smoke": "smoke" in tags, "perf": "perf" in tags})
    seen = set(); tcs = [t for t in tcs if not (t["tc"] in seen or seen.add(t["tc"]))]
    if not tcs:
        print("plan_round: no 'TC-n.m [persona]' lines found in TESTCASES.md", file=sys.stderr)
        sys.exit(1)

    wf_paths = {}
    wf_file = os.path.join(loop, "WORKFLOWS.md")
    if os.path.exists(wf_file):
        for line in open(wf_file, encoding="utf-8"):
            m = PATHS_RE.match(line)
            if m:
                wf_paths[m.group(1)] = [p.strip() for p in m.group(2).split(",") if p.strip()]

    # Contract lint — three silent failures were measured in the field: a
    # pre-format TESTCASES.md matched the id regex by luck and ran with no
    # persona/smoke data at all; nothing warned.
    problems = []
    untagged = [t["tc"] for t in tcs if t["personas"] == ["unspecified"]]
    if untagged:
        problems.append(f"{len(untagged)} test case(s) missing [novice]/[power] tags: "
                        + ", ".join(untagged[:6]) + ("…" if len(untagged) > 6 else ""))
    unmapped_all = sorted({t["wf"] for t in tcs} - set(wf_paths))
    if pass_type == "targeted" and unmapped_all:
        problems.append("workflows without a paths() line (targeting is blind to them): "
                        + ", ".join(unmapped_all))
    if not any(t["smoke"] for t in tcs):
        problems.append("no [smoke]-tagged test cases — targeted passes lose their regression floor")
    if flags["--lint"]:
        print(json.dumps({"ok": not problems, "problems": problems, "tcs": len(tcs),
                          "workflows": len({t["wf"] for t in tcs}),
                          "smoke": sum(1 for t in tcs if t["smoke"]),
                          "perf": sum(1 for t in tcs if t["perf"])}, indent=2))
        sys.exit(0 if not problems else 1)
    if problems and not flags["--lax"]:
        for pr in problems:
            print("plan_round: " + pr, file=sys.stderr)
        print("plan_round: fix TESTCASES.md / WORKFLOWS.md (see the skill's contracts) "
              "or pass --lax", file=sys.stderr)
        sys.exit(1)

    ledger = json.load(open(os.path.join(loop, "ledger.json")))
    finding_tcs, finding_wfs = set(), set()
    for f in ledger.get("findings", []):
        if f.get("current_status") not in ("open", "partial"): continue
        if f.get("routing", "auto") != "auto": continue
        if "FIX REJECTED" in (f.get("note") or ""): continue
        # A finding re-runs its own test case; only a finding with no
        # test_case widens to its whole workflow.
        if f.get("test_case"):
            finding_tcs.add(f["test_case"])
        else:
            reg = str(f.get("region", ""))
            if reg.startswith("WF-"):
                finding_wfs.add(reg.split(":")[0])

    changed = []
    if opt["--range"]:
        d = subprocess.run(["git", "-C", opt["--repo"], "diff", "--name-only", opt["--range"]],
                           capture_output=True, text=True)
        changed = [l.strip() for l in d.stdout.splitlines() if l.strip()]
    touched_wfs = {wf for wf, paths in wf_paths.items()
                   if any(c.startswith(p) for c in changed for p in paths)}

    if pass_type == "full":
        selected = tcs
        why = "full pass"
        degenerated = False
    else:
        selected = [t for t in tcs if t["smoke"] or t["tc"] in finding_tcs
                    or t["wf"] in finding_wfs or t["wf"] in touched_wfs]
        why = (f"targeted: {len(changed)} changed files touch {sorted(touched_wfs)}; "
               f"open findings reference {sorted(finding_tcs | finding_wfs)}; smoke set included")
        # Degenerate-targeting guard: one broad commit touching most workflows
        # turns "targeted" into a full pass in disguise (measured: 57/57
        # selected, ~1.5M wasted). Fall back to findings + smoke.
        degenerated = False
        if not flags["--allow-wide"] and tcs and len(selected) > 0.6 * len(tcs):
            selected = [t for t in tcs if t["smoke"] or t["tc"] in finding_tcs
                        or t["wf"] in finding_wfs]
            degenerated = True
            why += (f"; DEGENERATED: diff touched >60% of test cases — reduced to "
                    f"findings+smoke ({len(selected)}). Prefer per-workflow commits; "
                    f"--allow-wide overrides.")

    by_wf = {}
    for t in selected:
        by_wf.setdefault(t["wf"], []).append(t)
    chunks, k = [], 0
    for wf in sorted(by_wf, key=lambda w: int(w.split("-")[1])):
        group = [t for t in by_wf[wf] if not t["perf"]] or by_wf[wf]
        for j in range(0, len(group), max_tcs):
            part = group[j:j + max_tcs]
            slug = f"{wf.lower()}-{j // max_tcs + 1}"
            worker = f"qa-worker-{k % workers + 1}" if workers > 1 else "main"
            chunks.append({
                "slug": slug, "worker": worker, "lane": "functional",
                "turn_budget": turn_budget,
                "tcs": [t["tc"] for t in part],
                "personas": sorted({p for t in part for p in t["personas"]}),
                "region_filter": [wf],
                "evidence_dir": f"{loop}/evidence/round-{rnd}/{slug}/",
                "fragment": f"{loop}/fragments/round-{rnd}-{slug}.json",
                "results": f"{loop}/fragments/round-{rnd}-{slug}.results.json",
            })
            k += 1
    perf = [t["tc"] for t in selected if t["perf"]]
    n = len(selected)
    plan = {
        "round": rnd, "pass_type": pass_type, "why": why, "degenerated": degenerated,
        "selected": n, "total": len(tcs), "workers": workers, "max_tcs": max_tcs,
        "chunks": chunks,
        "perf_lane": {"tcs": perf, "fragment": f"{loop}/fragments/round-{rnd}-perf.json",
                      "results": f"{loop}/fragments/round-{rnd}-perf.results.json",
                      "note": "add perf candidates flagged by the functional lane"},
        "estimate": {"minutes": [n * 2, n * 4], "tokens": [n * 15000, n * 25000],
                     "basis": "2-4 min and 15-25K tokens per test case (field-calibrated)"},
        "unmapped_workflows": sorted({t["wf"] for t in tcs} - set(wf_paths)) if pass_type == "targeted" else [],
    }
    os.makedirs(os.path.join(loop, "briefs"), exist_ok=True)
    with open(os.path.join(loop, "briefs", f"round-{rnd}-plan.json"), "w") as fh:
        json.dump(plan, fh, indent=2); fh.write("\n")
    print(json.dumps(plan, indent=2))

if __name__ == "__main__":
    main()
