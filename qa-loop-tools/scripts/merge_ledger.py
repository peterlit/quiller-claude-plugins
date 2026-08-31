#!/usr/bin/env python3
"""Deterministically merge a round's LEDGER fragment into the loop ledger.

Usage:
  merge_ledger.py <ledger.json> <fragment.json> <round-number>
  merge_ledger.py resolve <ledger.json> <finding-id> <status> <round> [note]
  merge_ledger.py set-round <ledger.json> <round> [sha]
  merge_ledger.py open <ledger.json> [auto|proposal|all|closeout] [--region WF-n]
  merge_ledger.py archive <loop-dir> [name]
  merge_ledger.py scope <ledger.json> <range>
  merge_ledger.py set-usage <ledger.json> <round> <role> <tokens>   (REPLACES)
  merge_ledger.py add-usage <ledger.json> <round> <role> <tokens>   (accumulates)
  merge_ledger.py diff <loop-dir> <round> <range>
  merge_ledger.py next-round <loop-dir> <round> [--fragment F] [--sha S] [--pass full|targeted] [--phase-next NAME] [--brief-severity major|minor]

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
"closeout" selects the closeout-eligible set (auto-routed, introduced_by_fix
or minor); --region WF-n (repeatable) keeps only findings in those regions,
so a tester chunk receives the findings relevant to its workflows, not the
whole ledger. Merges record severity changes in severity_history.

archive: moves a finished loop's state (ledger.json, rounds.md, REPORT.md,
coverage.json, fragments/, briefs/, .phase) into <loop-dir>/archive/<name>/,
so a fresh loop starts clean instead of piling files at one level. Default
name: timestamp plus the ledger's sha.
"""
import json, os, shlex, sys

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
        # Per-round shas let render_report list each round's largest diffs
        # as WATCH LIST candidates even when every finding is fixed.
        ledger.setdefault("round_shas", {})[str(rnd)] = sha
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    if not getattr(set_round, "quiet", False):
        print(json.dumps(out))

def open_findings(args):
    usage = ("usage: merge_ledger.py open <ledger.json> "
             "[auto|proposal|all|closeout] [--region WF-n ...] [--severity major|minor]")
    if len(args) < 1:
        print(usage, file=sys.stderr)
        sys.exit(2)
    path = args[0]
    routing, regions, min_sev = "all", [], "minor"
    rest = list(args[1:])
    while rest:
        a = rest.pop(0)
        if a == "--region":
            if not rest:
                print(usage, file=sys.stderr)
                sys.exit(2)
            regions.append(rest.pop(0))
        elif a == "--severity":
            if not rest:
                print(usage, file=sys.stderr)
                sys.exit(2)
            min_sev = rest.pop(0)
        else:
            routing = a
    rank = {"blocker": 3, "major": 2, "minor": 1}
    if min_sev not in rank:
        print("merge_ledger: --severity must be blocker|major|minor", file=sys.stderr)
        sys.exit(1)
    if routing not in ("auto", "proposal", "all", "closeout"):
        print(f"merge_ledger: filter must be auto|proposal|all|closeout, "
              f"got '{routing}'", file=sys.stderr)
        sys.exit(1)
    with open(path) as fh:
        ledger = json.load(fh)
    sel = []
    for f in ledger.get("findings", []):
        if f.get("current_status") not in ("open", "partial"):
            continue
        r = f.get("routing", "auto")
        if routing == "closeout":
            # Closeout eligibility: auto-routed, and either a regression the
            # loop itself introduced (any severity) or a plain minor.
            if r != "auto":
                continue
            if not (f.get("introduced_by_fix") or f.get("severity") == "minor"):
                continue
        elif routing != "all" and r != routing:
            continue
        if rank.get(f.get("severity"), 1) < rank[min_sev]:
            continue
        if regions:
            reg = str(f.get("region", ""))
            tc = str(f.get("test_case", ""))
            # Boundary match: WF-1 must NOT match WF-10..WF-19 (measured: a
            # prefix match made every chunk brief up to 7x too big).
            if not any(reg == x or reg.startswith(x + ":") or reg.startswith(x + "/")
                       or tc.startswith(x.replace("WF-", "TC-") + ".")
                       for x in regions):
                continue
        sel.append({k: v for k, v in f.items() if k != "status_history"})
    print(json.dumps({"findings": sel}, indent=2))

def set_scope(args):
    """Record the change under review (a sha range) so render_report can
    list the scope diff as the FIRST watch-list candidate."""
    if len(args) < 2:
        print("usage: merge_ledger.py scope <ledger.json> <a..b>", file=sys.stderr)
        sys.exit(2)
    with open(args[0]) as fh:
        ledger = json.load(fh)
    ledger["scope"] = " ".join(shlex.split(" ".join(args[1:])))
    with open(args[0], "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    print(json.dumps({"scope": args[1]}))

def _usage(args, verb, accumulate):
    """set-usage REPLACES a (round, role) figure — the verb is named set, and
    a corrected figure must not inflate the budget feed (measured: a
    re-record read 89% over what was spent, against a live token_budget).
    add-usage ACCUMULATES — for many dispatches sharing one role in a round
    (qa chunk testers). Prefer unique per-dispatch roles (tester-wf2-1) with
    set-usage. Scale: the harness-reported figure is WORKLOAD-DEPENDENT —
    measured ~4x below billed effective for code loops and ~11x for
    simulator loops; the ratio grows with turns per dispatch. Budget on the
    reported scale for your loop type."""
    if len(args) < 4:
        print(f"usage: merge_ledger.py {verb} <ledger.json> <round> <role> <tokens>",
              file=sys.stderr)
        sys.exit(2)
    path, rnd, role = args[0], args[1], args[2]
    try:
        tokens = int(str(args[3]).replace(",", "").replace("_", ""))
        int(rnd)
    except ValueError:
        print("merge_ledger: round and tokens must be integers", file=sys.stderr)
        sys.exit(1)
    with open(path) as fh:
        ledger = json.load(fh)
    bucket = ledger.setdefault("usage", {}).setdefault(str(int(rnd)), {})
    bucket[role] = bucket.get(role, 0) + tokens if accumulate else tokens
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    total = sum(sum(v.values()) for v in ledger["usage"].values())
    if not getattr(set_usage, "quiet", False):
        print(json.dumps({"round": int(rnd), "role": role, "round_tokens": sum(bucket.values()),
                          "cumulative": total, "token_budget": ledger.get("token_budget")}))

def set_usage(args):
    _usage(args, "set-usage", accumulate=False)

def add_usage(args):
    _usage(args, "add-usage", accumulate=True)

def notes_rotate(args):
    """Rotate HARNESS_NOTES.md: chunk/round sections move to the archive,
    general sections stay. Measured: the file regrew 6.9KB -> 22KB in one
    round; at 86KB it cost ~21K tokens per dispatch and misled testers."""
    import datetime
    if len(args) < 1:
        print("usage: merge_ledger.py notes-rotate <loop-dir>", file=sys.stderr)
        sys.exit(2)
    loop = args[0]
    p = os.path.join(loop, "HARNESS_NOTES.md")
    if not os.path.exists(p):
        print(json.dumps({"rotated_sections": 0, "kept_bytes": 0}))
        return
    import re as _re
    with open(p, encoding="utf-8") as fh:
        text = fh.read()
    parts = _re.split(r"(?m)^(?=## )", text)
    keep, drop = [], []
    for i, sec in enumerate(parts):
        head = sec.splitlines()[0] if sec else ""
        if i > 0 and _re.search(r"(?i)\b(round|chunk|wave|dispatch)\b|round-\d", head):
            drop.append(sec)
        else:
            keep.append(sec)
    # Second pass: heading rotation alone could not get under the ceiling in
    # the field (growth was in general sections) — archive the LARGEST
    # remaining sections (preamble kept) until under 10KB.
    CEIL = 10240
    second = []
    if sum(len(k) for k in keep) > CEIL and len(keep) > 1:
        pre, secs = keep[0], keep[1:]
        order = sorted(range(len(secs)), key=lambda i: -len(secs[i]))
        keep_flag = [True] * len(secs)
        cur = len(pre) + sum(len(s) for s in secs)
        for i in order:
            if cur <= CEIL:
                break
            keep_flag[i] = False
            cur -= len(secs[i])
            second.append(secs[i])
        keep = [pre] + [s for f, s in zip(keep_flag, secs) if f]
    if drop or second:
        os.makedirs(os.path.join(loop, "archive"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(loop, "archive", f"harness-notes-{stamp}.md"), "w") as fh:
            fh.write("".join(drop + second))
        with open(p, "w") as fh:
            fh.write("".join(keep))
    size = os.path.getsize(p)
    print(json.dumps({"rotated_sections": len(drop), "ceiling_sections": len(second),
                      "kept_bytes": size, "over_ceiling": size > CEIL}))

def write_diff(args):
    """Materialize the round diff ONCE so subagents read it from disk instead of
    re-pulling it (measured: 21 git diff/show calls, 601K tokens, in one run)."""
    import subprocess
    if len(args) < 3:
        print("usage: merge_ledger.py diff <loop-dir> <round> <range>", file=sys.stderr)
        sys.exit(2)
    loop, rnd, rng = args[0], args[1], args[2]
    extra = list(args[3:])   # pathspecs, e.g. -- :!prompts.md to keep logs out
    base = os.path.basename(os.path.abspath(loop))
    # Nothing in the loop directory is ever under review; without this a
    # closeout diff picks up ledger/archive churn (measured: 444 -> 862 lines).
    if "--" in extra:
        extra.append(f":(exclude){base}")
    else:
        extra += ["--", ".", f":(exclude){base}"]
    repo = os.path.dirname(os.path.abspath(loop))
    os.makedirs(os.path.join(loop, "briefs"), exist_ok=True)
    dpath = os.path.join(loop, "briefs", f"round-{rnd}.diff")
    spath = os.path.join(loop, "briefs", f"round-{rnd}.stat")
    with open(dpath, "w") as fh:
        d = subprocess.run(["git", "-C", repo, "diff", rng] + extra, stdout=fh, stderr=subprocess.PIPE, text=True)
    with open(spath, "w") as fh:
        s = subprocess.run(["git", "-C", repo, "diff", "--stat", rng] + extra, stdout=fh, stderr=subprocess.PIPE, text=True)
    if d.returncode or s.returncode:
        print(f"merge_ledger: git diff failed: {(d.stderr or s.stderr).strip()}", file=sys.stderr)
        sys.exit(1)
    lines = sum(1 for _ in open(dpath))
    print(json.dumps({"diff": dpath, "stat": spath, "range": rng, "diff_lines": lines}))

def next_round(args):
    """One call for the end-of-round plumbing: merge the fragment, run metrics,
    and — if the verdict is continue — advance: set-round N+1, write the
    implementer brief, set the phase marker. Without --fragment it only
    advances (use after the seed). Prints one summary line."""
    import subprocess
    if len(args) < 2:
        print("usage: merge_ledger.py next-round <loop-dir> <round> [--fragment F] [--sha S] "
              "[--pass full|targeted] [--phase-next NAME] [--brief-severity major|minor]",
              file=sys.stderr)
        sys.exit(2)
    loop, rnd = args[0], int(args[1])
    opt = {"--fragment": None, "--sha": None, "--pass": "full",
           "--phase-next": None, "--brief-severity": "major"}
    usages = []
    i = 2
    while i < len(args):
        if args[i] == "--usage" and i + 1 < len(args):
            usages.append(args[i + 1]); i += 2
        elif args[i] in opt and i + 1 < len(args):
            opt[args[i]] = args[i + 1]; i += 2
        else:
            i += 1
    ledger_path = os.path.join(loop, "ledger.json")
    here = os.path.dirname(os.path.abspath(__file__))
    is_qa = os.path.basename(os.path.abspath(loop)) == ".qa-loop" or os.path.exists(os.path.join(here, "qa_metrics.py")) and not os.path.exists(os.path.join(here, "metrics.py"))
    out = {"round": rnd}
    for u in usages:   # role=tokens, applied to THIS round before metrics
        role, _, tok = u.partition("=")
        set_usage.quiet = True
        set_usage([ledger_path, str(rnd), role, tok])
        set_usage.quiet = False
    if usages:
        out["usage_recorded"] = len(usages)
    if opt["--fragment"]:
        m = subprocess.run([sys.executable, os.path.abspath(__file__), ledger_path, opt["--fragment"], str(rnd)],
                           capture_output=True, text=True)
        if m.returncode:
            print(m.stderr.strip(), file=sys.stderr); sys.exit(1)
        out["merged"] = json.loads(m.stdout)
        metrics = os.path.join(here, "qa_metrics.py" if is_qa else "metrics.py")
        cmd = [sys.executable, metrics, ledger_path, str(rnd)] + ([opt["--pass"]] if is_qa else [])
        v = subprocess.run(cmd, capture_output=True, text=True)
        if v.returncode:
            print(v.stderr.strip(), file=sys.stderr); sys.exit(1)
        verdict = json.loads(v.stdout)
        out["decision"], out["reason"] = verdict["decision"], verdict["reason"]
        out["open"] = {k: verdict[k] for k in ("blockers_open", "majors_open", "minors_open") if k in verdict}
        if verdict["decision"] != "continue":
            print(json.dumps(out)); return
    nxt = rnd + 1
    sha = opt["--sha"]
    if not sha:
        r = subprocess.run(["git", "-C", os.path.dirname(os.path.abspath(loop)), "rev-parse", "HEAD"],
                           capture_output=True, text=True)
        sha = r.stdout.strip() if r.returncode == 0 else None
    set_round.quiet = True
    set_round([ledger_path, str(nxt)] + ([sha] if sha else []))
    set_round.quiet = False
    os.makedirs(os.path.join(loop, "briefs"), exist_ok=True)
    brief = os.path.join(loop, "briefs", f"round-{nxt}-brief.json")
    b = subprocess.run([sys.executable, os.path.abspath(__file__), "open", ledger_path, "auto",
                        "--severity", opt["--brief-severity"]], capture_output=True, text=True)
    with open(brief, "w") as fh:
        fh.write(b.stdout)
    phase = opt["--phase-next"] or (f"round-{nxt}-testing" if is_qa else f"round-{nxt}-implementing")
    with open(os.path.join(loop, ".phase"), "w") as fh:
        fh.write(phase + "\n")
    out.update({"next_round": nxt, "sha": sha, "brief": brief,
                "brief_findings": len(json.loads(b.stdout).get("findings", [])), "phase": phase})
    print(json.dumps(out))

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
    # Name the archive by the ARCHIVED loop's own identity — its scope's
    # start sha when set, else its recorded round sha — so finding an old
    # loop doesn't mean opening every directory. (HEAD-at-archive-time named
    # every old loop after the NEW loop's commit.)
    if os.path.exists(ledger_path):
        try:
            import re as _re
            m = _re.match(r"([0-9a-fA-F]{4,40})\.\.", str(led.get("scope") or ""))
            if m:
                sha = m.group(1)[:7]
        except Exception:
            pass
    name = (args[1] if len(args) > 1 else
            datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            + (f"-{sha}" if sha else ""))
    dest = os.path.join(loop_dir, "archive", name)
    moved = []
    for item in ("ledger.json", "rounds.md", "REPORT.md", "coverage.json",
                 "verdict.json", "fragments", "briefs", ".phase"):
        src = os.path.join(loop_dir, item)
        if os.path.exists(src):
            os.makedirs(dest, exist_ok=True)
            shutil.move(src, os.path.join(dest, item))
            moved.append(item)
    # Sweep unknown top-level FILES (legacy REPORT-*.md, stray fragments…)
    # into legacy/ — every loop run pays to `ls` whatever is left here.
    KEEP = {"WORKFLOWS.md", "TESTCASES.md", "HARNESS_NOTES.md", "BACKLOG.md",
            ".gitignore", "archive", "evidence", "tools", "driver", "scratch",
            "notes"}
    for entry in sorted(os.listdir(loop_dir)):
        src = os.path.join(loop_dir, entry)
        if entry in KEEP or not os.path.isfile(src):
            continue
        os.makedirs(os.path.join(dest, "legacy"), exist_ok=True)
        shutil.move(src, os.path.join(dest, "legacy", entry))
        moved.append(f"legacy/{entry}")
    if not moved:
        print(f"merge_ledger: nothing to archive in {loop_dir}",
              file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"archived_to": dest, "moved": moved}))

def main():
    verbs = {"resolve": resolve, "set-round": set_round,
             "open": open_findings, "archive": archive, "scope": set_scope,
             "set-usage": set_usage, "add-usage": add_usage,
             "diff": write_diff, "next-round": next_round,
             "notes-rotate": notes_rotate}
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
            old_sev = f.get("severity")
            for k, v in nf.items():
                if k in ("status_history", "first_seen_round", "evidence",
                         "severity_history"):
                    continue
                f[k] = v
            new_sev = f.get("severity")
            if old_sev and new_sev and old_sev != new_sev:
                f.setdefault("severity_history", []).append(
                    {"round": rnd, "from": old_sev, "to": new_sev})
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
    out = {"round": rnd, "updated": updated, "added": added,
           "total": len(ledger["findings"])}
    # Blocker escalation (scope mode): the skill promises max_rounds 2 -> 5
    # when a blocker appears; enforce it here so the promise is kept by code.
    if (ledger.get("scope") and ledger.get("max_rounds") == 2
            and any(f.get("severity") == "blocker"
                    and f.get("current_status") in ("open", "partial")
                    for f in ledger["findings"])):
        ledger["max_rounds"] = 5
        out["escalated_max_rounds"] = 5
    with open(ledger_path, "w") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    print(json.dumps(out))

if __name__ == "__main__":
    main()
