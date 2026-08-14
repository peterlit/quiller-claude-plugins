#!/usr/bin/env python3
"""Compute per-round convergence metrics and the stop decision for the qa loop.

Usage: qa_metrics.py <path-to-ledger.json> <round-number> [full|targeted]
Appends a row to <ledger-dir>/rounds.md and prints a JSON verdict on stdout.

Proposal-routed findings (routing == "proposal") are excluded from all metrics:
they are human decisions and must not block or distort convergence.
"""
import json, sys, os

OPENISH = {"open", "partial"}

def status_at(f, r):
    """Status of finding f at the end of round r, or None if not yet seen."""
    if f.get("first_seen_round", 1) > r:
        return None
    best = None
    for e in f.get("status_history", []):
        if e.get("round", 0) <= r:
            best = e.get("status")
    return best if best is not None else f.get("current_status")

def regions_new_or_reopened(findings, r):
    out = set()
    for f in findings:
        if f.get("first_seen_round") == r:
            out.add(f.get("region", f.get("id")))
        elif status_at(f, r - 1) == "fixed" and status_at(f, r) in OPENISH:
            out.add(f.get("region", f.get("id")))
    return out

def reopen_count(f):
    n, prev = 0, None
    for e in sorted(f.get("status_history", []), key=lambda x: x.get("round", 0)):
        s = e.get("status")
        if prev == "fixed" and s in OPENISH:
            n += 1
        prev = s
    return n

def net_for(findings, r):
    closed = sum(1 for f in findings
                 if status_at(f, r - 1) in OPENISH and status_at(f, r) == "fixed")
    new = sum(1 for f in findings if f.get("first_seen_round") == r)
    reopened = sum(1 for f in findings
                   if status_at(f, r - 1) == "fixed" and status_at(f, r) in OPENISH)
    return closed, new, reopened, closed - new

def open_count(findings, r, severity):
    return sum(1 for f in findings
               if f.get("severity") == severity and status_at(f, r) in OPENISH)

def disputed_set(findings, r):
    return frozenset(f["id"] for f in findings if status_at(f, r) == "disputed")

def main():
    path, N = sys.argv[1], int(sys.argv[2])
    pass_type = sys.argv[3] if len(sys.argv) > 3 else "full"
    with open(path) as fh:
        ledger = json.load(fh)
    all_findings = ledger.get("findings", [])
    findings = [f for f in all_findings if f.get("routing", "auto") != "proposal"]
    proposals_open = sum(1 for f in all_findings
                         if f.get("routing") == "proposal"
                         and status_at(f, N) in OPENISH)
    max_rounds = ledger.get("max_rounds", 5)

    closed, new, reopened, net = net_for(findings, N)
    blockers_open = open_count(findings, N, "blocker")
    majors_open = open_count(findings, N, "major")
    minors_open = open_count(findings, N, "minor")
    new_blocker_major = any(
        f.get("first_seen_round") == N and f.get("severity") in ("blocker", "major")
        for f in findings)

    # multi-round signals
    net_prev = net_for(findings, N - 1)[3] if N >= 2 else None
    disp_now = disputed_set(findings, N)
    disp_prev = disputed_set(findings, N - 1) if N >= 2 else None
    region_thrash = False
    if N >= 3:
        a = regions_new_or_reopened(findings, N)
        b = regions_new_or_reopened(findings, N - 1)
        c = regions_new_or_reopened(findings, N - 2)
        region_thrash = bool(a & b & c)
    any_reopened_twice = any(reopen_count(f) >= 2 for f in findings)

    # decision, in priority order
    if blockers_open == 0 and majors_open == 0 and not new_blocker_major:
        if pass_type == "full":
            decision, reason = "converged", "no open blockers or majors; none newly introduced; confirmed on a full pass"
        else:
            decision, reason = "full_pass_required", "convergence signals on a targeted pass; confirm with a full pass"
    elif any_reopened_twice or (net_prev is not None and net <= 0 and net_prev <= 0) or region_thrash:
        decision, reason = "thrashing", "oscillation or non-positive net over two rounds or a churning region"
    elif disp_prev is not None and disp_now == disp_prev and len(disp_now) > 0:
        decision, reason = "stalemate", "identical disputed set for two consecutive rounds"
    elif net_prev is not None and net <= 1 and net_prev <= 1 and blockers_open == 0:
        decision, reason = "diminishing", "net <= 1 for two rounds and no open blockers"
    elif N >= max_rounds:
        decision, reason = "backstop", "hit max_rounds"
    else:
        decision, reason = "continue", "progress continuing"

    verdict = {
        "round": N, "pass_type": pass_type, "blockers_open": blockers_open,
        "majors_open": majors_open, "minors_open": minors_open,
        "proposals_open": proposals_open, "closed": closed, "new": new,
        "reopened": reopened, "net": net, "decision": decision, "reason": reason,
    }

    rounds_md = os.path.join(os.path.dirname(os.path.abspath(path)), "rounds.md")
    header = "| Round | Pass | Blockers | Majors | Minors | Proposals | Closed | New | Reopened | Net | Decision |\n"
    sep = "|-------|------|----------|--------|--------|-----------|--------|-----|----------|-----|----------|\n"
    if not os.path.exists(rounds_md):
        with open(rounds_md, "w") as fh:
            fh.write(header + sep)
    with open(rounds_md, "a") as fh:
        fh.write(f"| {N} | {pass_type} | {blockers_open} | {majors_open} | "
                 f"{minors_open} | {proposals_open} | {closed} | {new} | "
                 f"{reopened} | {net:+d} | {decision} |\n")

    print(json.dumps(verdict, indent=2))

if __name__ == "__main__":
    main()
