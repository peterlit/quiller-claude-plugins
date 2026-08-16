#!/usr/bin/env python3
"""Compute per-round convergence metrics and the stop decision for the qa loop.

Usage: qa_metrics.py <path-to-ledger.json> <round-number> [full|targeted]
Appends a row to <ledger-dir>/rounds.md and prints a JSON verdict on stdout.

Proposal-routed findings (routing == "proposal") are excluded from all metrics:
they are human decisions and must not block or distort convergence.

On a full pass, coverage is verified against <ledger-dir>/coverage.json and the
TC ids found in <ledger-dir>/TESTCASES.md: a "converged" verdict degrades to
"full_pass_required" if any test case was not run (or no manifest was written).
"blocked" counts as accounted-for but is reported for the COVERAGE GAPS section.
"""
import json, os, re, sys

OPENISH = {"open", "partial"}

def die(msg):
    print(f"qa_metrics: {msg}", file=sys.stderr)
    sys.exit(1)

def validate(findings):
    for f in findings:
        fid = f.get("id", "<missing id>")
        fsr = f.get("first_seen_round", 1)
        if not isinstance(fsr, int):
            die(f"finding {fid}: first_seen_round must be an integer, got {fsr!r}")
        for e in f.get("status_history", []):
            r = e.get("round")
            if not isinstance(r, int):
                die(f"finding {fid}: status_history round must be an integer, "
                    f"got {r!r} — annotations belong in 'note', not 'round'")

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
        elif status_at(f, r - 1) == "fixed" and status_at(f, r) == "open":
            out.add(f.get("region", f.get("id")))
    return out

def reopen_count(f):
    # fixed -> open is a reopen; fixed -> partial is verification finding a
    # remaining edge case (refinement), and must not feed the oscillation
    # detector.
    n, prev = 0, None
    for e in sorted(f.get("status_history", []), key=lambda x: x.get("round", 0)):
        s = e.get("status")
        if prev == "fixed" and s == "open":
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

def check_coverage(base_dir, N):
    """Returns (coverage-dict-or-None, missing, manifest_exists)."""
    tc_path = os.path.join(base_dir, "TESTCASES.md")
    cov_path = os.path.join(base_dir, "coverage.json")
    if not os.path.exists(tc_path):
        return None, [], True
    with open(tc_path) as fh:
        tc_ids = sorted(set(re.findall(r"\bTC-\d+(?:\.\d+)?\b", fh.read())))
    round_cov = {}
    manifest_exists = os.path.exists(cov_path)
    if manifest_exists:
        with open(cov_path) as fh:
            round_cov = json.load(fh).get("rounds", {}).get(str(N), {})
    missing = [t for t in tc_ids if t not in round_cov]
    # Rows are keyed (tc, persona); a TC counts covered with >= 1 persona
    # record, and blocked entries are reported per persona.
    blocked = []
    for t in sorted(round_cov):
        for p, rec in sorted(round_cov[t].items()):
            if isinstance(rec, dict) and rec.get("status") == "blocked":
                blocked.append(f"{t}({p})")
    coverage = {"ran": len(tc_ids) - len(missing), "total": len(tc_ids),
                "missing": missing, "blocked": blocked}
    return coverage, missing, manifest_exists

def main():
    if len(sys.argv) < 3:
        die("usage: qa_metrics.py <ledger.json> <round> [full|targeted]")
    path = sys.argv[1]
    try:
        N = int(sys.argv[2])
    except ValueError:
        die(f"round must be an integer, got '{sys.argv[2]}'")
    pass_type = sys.argv[3] if len(sys.argv) > 3 else "full"
    if pass_type not in ("full", "targeted"):
        die(f"pass type must be 'full' or 'targeted', got '{pass_type}'")
    with open(path) as fh:
        ledger = json.load(fh)
    all_findings = ledger.get("findings", [])
    validate(all_findings)
    findings = [f for f in all_findings if f.get("routing", "auto") != "proposal"]
    proposals_open = sum(1 for f in all_findings
                         if f.get("routing") == "proposal"
                         and status_at(f, N) in OPENISH)
    max_rounds = ledger.get("max_rounds", 5)
    implemented = set(ledger.get("implemented_rounds", []))

    def post_impl(r):
        # Round r's net is only a convergence signal if an implementer
        # actually acted before r's test pass (i.e. at the end of round r-1).
        # Discovery rounds are inherently net-negative and cannot oscillate.
        return (r - 1) in implemented

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
        if a & b & c:
            # Healthy-churn exception: a region that keeps yielding NEW,
            # net-positive, non-reopening findings is convergent residue
            # (each fix exposing a smaller issue), not oscillation. Judged
            # on the last two rounds — round 1 is the seed and always net-
            # negative. Reopens or non-positive net still count as thrashing.
            healthy = all(
                net_for(findings, r)[3] > 0 and net_for(findings, r)[2] == 0
                for r in (N, N - 1))
            region_thrash = not healthy
    any_reopened_twice = any(reopen_count(f) >= 2 for f in findings)

    # decision, in priority order
    if blockers_open == 0 and majors_open == 0 and not new_blocker_major:
        if pass_type == "full":
            decision, reason = "converged", "no open blockers or majors; none newly introduced; confirmed on a full pass"
        else:
            decision, reason = "full_pass_required", "convergence signals on a targeted pass; confirm with a full pass"
    elif any_reopened_twice or (net_prev is not None and net <= 0 and net_prev <= 0
                                and post_impl(N) and post_impl(N - 1)) or region_thrash:
        if blockers_open == 0 and closed > 0:
            decision, reason = "thrashing_soft", "thrashing signals but with mitigating progress (0 open blockers, positive closes) — confirm with the human before aborting"
        else:
            decision, reason = "thrashing", "oscillation or non-positive net over two post-implementation rounds or a churning region"
    elif disp_prev is not None and disp_now == disp_prev and len(disp_now) > 0:
        decision, reason = "stalemate", "identical disputed set for two consecutive rounds"
    elif (net_prev is not None and net <= 1 and net_prev <= 1 and blockers_open == 0
          and not new_blocker_major and post_impl(N) and post_impl(N - 1)):
        # "Diminishing" must mean "nothing left to find" — net <= 1 includes
        # deeply negative rounds, so a round that spawned new majors (often
        # introduced_by_fix regressions) must never wind down to BACKLOG.
        decision, reason = "diminishing", "net <= 1 for two post-implementation rounds, no open blockers, no new blockers/majors"
    elif N >= max_rounds:
        decision, reason = "backstop", "hit max_rounds"
    else:
        decision, reason = "continue", "progress continuing"

    # coverage gate: a full pass must account for every test case
    coverage = None
    if pass_type == "full":
        base_dir = os.path.dirname(os.path.abspath(path))
        coverage, missing, manifest_exists = check_coverage(base_dir, N)
        if decision == "converged" and coverage is not None:
            if not manifest_exists:
                decision = "full_pass_required"
                reason = "full pass claimed but no coverage manifest (coverage.json) was written"
            elif missing:
                decision = "full_pass_required"
                reason = (f"full pass claimed but {len(missing)} test case(s) "
                          f"unrun: {', '.join(missing[:5])}"
                          + ("…" if len(missing) > 5 else ""))

    verdict = {
        "round": N, "pass_type": pass_type, "blockers_open": blockers_open,
        "majors_open": majors_open, "minors_open": minors_open,
        "proposals_open": proposals_open, "closed": closed, "new": new,
        "reopened": reopened, "net": net, "decision": decision, "reason": reason,
    }
    if coverage is not None:
        verdict["coverage"] = coverage

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
