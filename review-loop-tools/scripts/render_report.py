#!/usr/bin/env python3
"""Render the deterministic sections of a loop's REPORT.md from its state files.

Usage: render_report.py <loop-dir> [--out <path>]
Reads ledger.json, rounds.md, verdict.json, coverage.json (qa), and any
fragments/round-*-closeout.json. Writes <loop-dir>/REPORT.md (or --out).

Everything mechanical is rendered here — stop condition, trend table, open
findings by severity, disputes, proposals, fix-review rejections, severity
promotions, persona matrix, coverage gaps, closeout, resolutions. The one
section that needs judgment, WATCH LIST, is emitted as candidate stubs with a
"look here because:" slot the orchestrator fills in. Works for both loops.
"""
import glob, json, os, sys

OPENISH = ("open", "partial")
SEV_ORDER = ("blocker", "major", "minor")

def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh) if path.endswith(".json") else fh.read()

def finding_line(f):
    bits = [f"**{f.get('id')}** — {f.get('severity', '?')}, {f.get('current_status')}"]
    if f.get("region"):
        bits.append(f"region `{f['region']}`")
    if f.get("fix_risk"):
        bits.append(f"fix_risk `{f['fix_risk']}`")
    if f.get("introduced_by_fix"):
        bits.append("introduced_by_fix")
    out = ["- " + "; ".join(bits)]
    if f.get("claim"):
        out.append(f"  - {f['claim']}")
    ev = f.get("evidence")
    if isinstance(ev, list) and ev:
        out.append("  - evidence: " + ", ".join(f"`{e}`" for e in ev))
    elif isinstance(ev, dict):
        shots = ev.get("screenshots") or []
        if shots:
            out.append("  - evidence: " + ", ".join(f"`{s}`" for s in shots))
        if ev.get("measurements"):
            out.append(f"  - measurements: `{json.dumps(ev['measurements'])}`")
    if f.get("constraints"):
        out.append("  - constraints: " + "; ".join(f["constraints"]))
    if f.get("note"):
        out.append(f"  - note: {f['note']}")
    return out

def main():
    if len(sys.argv) < 2:
        print("usage: render_report.py <loop-dir> [--out <path>]", file=sys.stderr)
        sys.exit(2)
    loop = sys.argv[1]
    out_path = os.path.join(loop, "REPORT.md")
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
    ledger = load(os.path.join(loop, "ledger.json"))
    if ledger is None:
        print(f"render_report: no ledger.json in {loop}", file=sys.stderr)
        sys.exit(1)
    findings = ledger.get("findings", [])
    verdict = load(os.path.join(loop, "verdict.json"), {})
    rounds_md = load(os.path.join(loop, "rounds.md"), "")
    coverage = load(os.path.join(loop, "coverage.json"))
    L = []

    L.append(f"# Loop report — {os.path.basename(os.path.abspath(loop))}\n")
    if verdict:
        L.append(f"**Stop condition:** `{verdict.get('decision')}` after round "
                 f"{verdict.get('round')} — {verdict.get('reason')}\n")
    else:
        L.append("**Stop condition:** unknown (no verdict.json — metrics never ran?)\n")
    counts = {}
    for f in findings:
        counts[f.get("current_status")] = counts.get(f.get("current_status"), 0) + 1
    L.append("**Findings by status:** " + ", ".join(
        f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + "\n")

    L.append("## Trend\n")
    L.append(rounds_md.strip() + "\n" if rounds_md else "_no rounds.md_\n")

    L.append("## Open findings by severity\n")
    auto_open = [f for f in findings if f.get("current_status") in OPENISH
                 and f.get("routing", "auto") != "proposal"]
    if not auto_open:
        L.append("_none_\n")
    for sev in SEV_ORDER:
        group = [f for f in auto_open if f.get("severity") == sev]
        if group:
            L.append(f"### {sev} ({len(group)})\n")
            for f in group:
                L += finding_line(f)
            L.append("")

    disputed = [f for f in findings if f.get("current_status") == "disputed"]
    L.append("## Disputed (agree-to-disagree)\n")
    if disputed:
        for f in disputed:
            L += finding_line(f)
        L.append("")
    else:
        L.append("_none_\n")

    proposals = [f for f in findings if f.get("routing") == "proposal"
                 and f.get("current_status") in OPENISH]
    if any(f.get("routing") for f in findings):
        L.append("## UX proposals (human decisions — flip routing to \"auto\" to accept)\n")
        if proposals:
            for f in proposals:
                L += finding_line(f)
            L.append("")
        else:
            L.append("_none_\n")

    rejected = [f for f in findings if "FIX REJECTED" in (f.get("note") or "")]
    L.append("## Fix review rejections\n")
    if rejected:
        for f in rejected:
            L += finding_line(f)
        L.append("")
    else:
        L.append("_none_\n")

    promos = [(f.get("id"), e) for f in findings
              for e in (f.get("severity_history") or [])]
    L.append("## Severity changes\n")
    if promos:
        for fid, e in promos:
            arrow = "promoted" if e.get("to") in SEV_ORDER and e.get("from") in SEV_ORDER \
                and SEV_ORDER.index(e["to"]) < SEV_ORDER.index(e["from"]) else "demoted"
            L.append(f"- round {e.get('round')}: **{fid}** {arrow} {e.get('from')} → {e.get('to')}")
        L.append("")
    else:
        L.append("_none_\n")

    if coverage:
        rounds = coverage.get("rounds", {})
        if rounds:
            last = str(max(int(k) for k in rounds))
            rows = rounds[last]
            L.append(f"## Persona matrix (round {last})\n")
            personas = sorted({p for tc in rows.values() for p in tc})
            wfs = {}
            for tc, per in rows.items():
                wf = "WF-" + tc.split("-", 1)[1].split(".")[0] if "-" in tc else tc
                for p, rec in per.items():
                    wfs.setdefault(wf, {}).setdefault(p, []).append(rec.get("status"))
            L.append("| Workflow | " + " | ".join(personas) + " |")
            L.append("|---|" + "---|" * len(personas))
            for wf in sorted(wfs, key=lambda w: int(w.split("-")[1]) if w.split("-")[-1].isdigit() else 0):
                cells = []
                for p in personas:
                    st = wfs[wf].get(p)
                    if not st:
                        cells.append("—")
                    else:
                        c = {k: st.count(k) for k in ("passed", "failed", "blocked", "skipped") if st.count(k)}
                        cells.append(" ".join(f"{v}{ {'passed':'✓','failed':'✗','blocked':'⊘','skipped':'…'}[k] }" for k, v in c.items()))
                L.append(f"| {wf} | " + " | ".join(cells) + " |")
            L.append("")
            L.append("## Coverage gaps\n")
            gaps = [(tc, p, rec) for tc, per in rows.items() for p, rec in per.items()
                    if rec.get("status") in ("blocked", "skipped")]
            if gaps:
                for tc, p, rec in sorted(gaps):
                    L.append(f"- {tc} ({p}): {rec.get('status')} — {rec.get('reason') or 'no reason given'}")
                L.append("")
            else:
                L.append("_none_\n")

    closeout_frags = sorted(glob.glob(os.path.join(loop, "fragments", "round-*-closeout.json")))
    L.append("## Closeout\n")
    if closeout_frags:
        ids = set()
        for cf in closeout_frags:
            try:
                ids |= {x.get("id") for x in (load(cf) or {}).get("findings", [])}
            except Exception:
                pass
        for f in findings:
            if f.get("id") in ids:
                L += finding_line(f)
        L.append("")
    else:
        L.append("_no closeout cycle ran_\n")

    resolved = [f for f in findings if f.get("current_status") == "wontfix"]
    L.append("## Wontfix / resolved\n")
    if resolved:
        for f in resolved:
            L.append(f"- **{f.get('id')}** — {f.get('note') or ''}")
        L.append("")
    else:
        L.append("_none_\n")

    L.append("## WATCH LIST\n")
    L.append("_The part a human should actually read. Candidates below are "
             "mechanical; the orchestrator fills each \"look here because\"._\n")
    cands = []
    for f in findings:
        why = []
        if f.get("fix_risk"):
            why.append(f"fix_risk {f['fix_risk']}")
        if f.get("introduced_by_fix"):
            why.append("introduced by a fix")
        if "FIX REJECTED" in (f.get("note") or ""):
            why.append("a fix was rejected")
        if f.get("routing") == "proposal":
            why.append("proposal awaiting decision")
        if why:
            cands.append((f.get("id"), ", ".join(why)))
    for fid, why in cands:
        L.append(f"- **{fid}** ({why}) — look here because: <!-- orchestrator fills -->")
    L.append("- <!-- plus the 3-5 most invasive diffs across all rounds, with commits -->")
    L.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(json.dumps({"report": out_path, "findings": len(findings),
                      "watch_candidates": len(cands)}))

if __name__ == "__main__":
    main()
