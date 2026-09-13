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

# Workflow ids may carry a letter suffix (WF-9b): the chunker once parsed
# only WF-\d+, so WF-9b's test cases appeared in `selected` but landed in NO
# chunk, lint passed, and the blocker living there needed a hand-built
# manual chunk in all three rounds to be found at all.
TC_RE = re.compile(r"^\s*(?:[-*#]+\s*)?(TC-(\d+[a-z]?)\.\d+)\b(.*)$")
TAG_RE = re.compile(r"\[(novice|power|smoke|perf)\]")
PATHS_RE = re.compile(r"^\s*paths\((WF-\d+[a-z]?)\)\s*:\s*(.+?)\s*$")
WF_KEY_RE = re.compile(r"^WF-(\d+)([a-z]?)$")

def wf_key(wf):
    """Sort key for WF-<n>[letter] — int() alone crashes on 'WF-9b'."""
    m = WF_KEY_RE.match(wf)
    return (int(m.group(1)), m.group(2)) if m else (10**9, wf)

def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[2] not in ("full", "targeted"):
        print(__doc__, file=sys.stderr); sys.exit(2)
    loop, rnd, pass_type = a[0], int(a[1]), a[2]
    opt = {"--range": None, "--workers": "1", "--max-tcs": "5", "--repo": ".",
           "--turn-budget": "40"}
    flags = {"--lint": False, "--lax": False, "--allow-wide": False,
             "--summary": False}
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
    finding_tcs, finding_wfs, misc_regions = set(), set(), set()
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
            else:
                # Screen-name regions (Main, DailyView) used to be dropped
                # here silently: those findings only ever reached the
                # implementer, and no tester chunk verified them (measured:
                # two were resolved by hand from a writer's green run). They
                # get a catch-all findings-misc chunk below.
                misc_regions.add(reg or str(f.get("id", "?")))

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

    # Worker AFFINITY: every piece of one workflow goes to the same worker —
    # sibling chunks of one workflow on different workers filed the same
    # finding under different ids (measured: three duplicate pairs in one
    # round). Heaviest workflows placed first onto the least-loaded worker.
    wf_order = sorted(by_wf, key=wf_key)
    slots = max(workers, 1)
    load = [0] * slots
    wf_slot = {}
    for wf in sorted(wf_order, key=lambda w: -len(by_wf[w])):
        s = load.index(min(load))
        wf_slot[wf] = s
        load[s] += len([t for t in by_wf[wf] if not t["perf"]] or by_wf[wf])

    # Pieces first, chunk dicts later (so tiny-piece coalescing can rename).
    pieces = []   # {"wfs": [wf...], "tcs": [tc-dict...], "slot": int}
    for wf in wf_order:
        group = [t for t in by_wf[wf] if not t["perf"]] or by_wf[wf]
        for j in range(0, len(group), max_tcs):
            pieces.append({"wfs": [wf], "tcs": group[j:j + max_tcs],
                           "slot": wf_slot[wf]})
    # Tiny-chunk COALESCING: seven of 23 chunks in one measured full pass
    # carried 1-2 cases, and each dispatch pays ~40-60K of fixed cost
    # (notes, README, WORKFLOWS reads). A piece under 3 TCs merges into the
    # same-worker piece that stays smallest after the merge — which may
    # exceed max_tcs by the tiny remainder; that beats paying a dispatch.
    MIN_TCS = 3
    changed_any = True
    while changed_any:
        changed_any = False
        for p in sorted(pieces, key=lambda x: len(x["tcs"])):
            if len(p["tcs"]) >= MIN_TCS or len(pieces) == 1:
                continue
            mates = [q for q in pieces if q is not p and q["slot"] == p["slot"]]
            if not mates:
                continue
            tgt = min(mates, key=lambda q: len(q["tcs"]))
            tgt["wfs"] = sorted(set(tgt["wfs"]) | set(p["wfs"]), key=wf_key)
            tgt["tcs"] += p["tcs"]
            pieces.remove(p)
            changed_any = True
            break

    chunks = []
    slug_seq = {}
    for p in pieces:
        base = "+".join(w.lower() for w in p["wfs"])
        slug_seq[base] = slug_seq.get(base, 0) + 1
        slug = f"{base}-{slug_seq[base]}"
        worker = f"qa-worker-{p['slot'] + 1}" if workers > 1 else "main"
        chunks.append({
            "slug": slug, "worker": worker, "lane": "functional",
            "turn_budget": turn_budget,
            "tcs": [t["tc"] for t in p["tcs"]],
            "personas": sorted({pp for t in p["tcs"] for pp in t["personas"]}),
            "region_filter": list(p["wfs"]),
            "evidence_dir": f"{loop}/evidence/round-{rnd}/{slug}/",
            "fragment": f"{loop}/fragments/round-{rnd}-{slug}.json",
            "results": f"{loop}/fragments/round-{rnd}-{slug}.results.json",
        })
    # Catch-all chunk for open findings whose region is a screen name, not a
    # WF id — they have no test case to select, but a tester must still
    # verify them (they were previously unreachable by any chunk).
    if misc_regions:
        slug = "findings-misc"
        light = load.index(min(load)) if workers > 1 else 0
        chunks.append({
            "slug": slug,
            "worker": f"qa-worker-{light + 1}" if workers > 1 else "main",
            "lane": "functional", "turn_budget": turn_budget, "tcs": [],
            "personas": ["power"], "region_filter": sorted(misc_regions),
            "note": ("open findings with non-WF regions (screen names): "
                     "verify each finding directly against its claim and "
                     "evidence; extract them with merge_ledger.py open "
                     "--region <name>"),
            "evidence_dir": f"{loop}/evidence/round-{rnd}/{slug}/",
            "fragment": f"{loop}/fragments/round-{rnd}-{slug}.json",
            "results": f"{loop}/fragments/round-{rnd}-{slug}.results.json",
        })

    # Perf lane GATING: a perf lane that re-runs clean [perf] cases every
    # round buys nothing (measured: TC-4.1 ran four times, all clean, ~90K
    # per round). Run it only when it can say something new.
    perf_all = [t["tc"] for t in selected if t["perf"]]
    perf_tc_ids = {t["tc"] for t in tcs if t["perf"]}
    perf_wfs = {t["wf"] for t in tcs if t["perf"]}
    perf_reason = None
    if perf_all:
        if pass_type == "full":
            perf_reason = "full pass"
        elif finding_tcs & perf_tc_ids or finding_wfs & perf_wfs:
            perf_reason = "an open finding references a [perf] case or workflow"
        elif touched_wfs & perf_wfs:
            perf_reason = "the diff touches a [perf]-tagged workflow"
    perf = perf_all if perf_reason else []
    perf_note = (f"run: {perf_reason}; add perf candidates flagged by the functional lane"
                 if perf_reason else
                 ("skipped: no perf-relevant change or finding this round "
                  "(functional-lane perf candidates still get a lane — re-plan or "
                  "dispatch ad hoc)" if perf_all else "no [perf] cases selected"))

    # Completeness check — HARD error, not advisory: WF-9b's cases once sat
    # in `selected` while no chunk contained them and lint passed; the
    # blocker living there was nearly never found. Every selected TC must
    # land in exactly one functional chunk (or be a gated-off perf case).
    placed = {}
    for c in chunks:
        for tc in c["tcs"]:
            placed[tc] = placed.get(tc, 0) + 1
    orphans = [t["tc"] for t in selected
               if placed.get(t["tc"], 0) == 0 and t["tc"] not in perf_tc_ids]
    doubled = sorted(tc for tc, n in placed.items() if n > 1)
    if orphans or doubled:
        if orphans:
            print("plan_round: INTERNAL ERROR — selected test case(s) in NO "
                  "chunk: " + ", ".join(sorted(orphans)), file=sys.stderr)
        if doubled:
            print("plan_round: INTERNAL ERROR — test case(s) in MULTIPLE "
                  "chunks: " + ", ".join(doubled), file=sys.stderr)
        print("plan_round: chunker bug — do NOT dispatch this plan",
              file=sys.stderr)
        sys.exit(1)

    n = len(selected)
    plan = {
        "round": rnd, "pass_type": pass_type, "why": why, "degenerated": degenerated,
        "selected": n, "total": len(tcs), "workers": workers, "max_tcs": max_tcs,
        "chunks": chunks,
        "perf_lane": {"tcs": perf, "fragment": f"{loop}/fragments/round-{rnd}-perf.json",
                      "results": f"{loop}/fragments/round-{rnd}-perf.results.json",
                      "note": perf_note},
        "estimate": {"minutes": [n * 2, n * 4], "tokens": [n * 15000, n * 25000],
                     "basis": "2-4 min and 15-25K tokens per test case (field-calibrated)"},
        "unmapped_workflows": sorted({t["wf"] for t in tcs} - set(wf_paths)) if pass_type == "targeted" else [],
    }
    os.makedirs(os.path.join(loop, "briefs"), exist_ok=True)
    with open(os.path.join(loop, "briefs", f"round-{rnd}-plan.json"), "w") as fh:
        json.dump(plan, fh, indent=2); fh.write("\n")
    if flags["--summary"]:
        # Human-readable digest — both field orchestrators re-parsed the
        # plan JSON by hand to see the same thing.
        L = [f"round {rnd} {pass_type}: {n}/{len(tcs)} selected"
             + (" (DEGENERATED)" if degenerated else "")
             + f", {len(chunks)} chunks, workers={workers}"]
        for c in chunks:
            L.append(f"  {c['slug']:<24} {c['worker']:<14} "
                     f"{len(c['tcs'])} tc  [{','.join(c['personas'])}]  "
                     f"regions {','.join(c['region_filter'])}")
        L.append(f"  perf lane: {', '.join(perf) if perf else '—'} ({perf_note})")
        L.append(f"  estimate: {n*2}-{n*4} min, {n*15}K-{n*25}K tokens")
        if plan["unmapped_workflows"]:
            L.append("  unmapped workflows: " + ", ".join(plan["unmapped_workflows"]))
        print("\n".join(L))
    else:
        print(json.dumps(plan, indent=2))

if __name__ == "__main__":
    main()
