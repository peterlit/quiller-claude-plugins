#!/usr/bin/env python3
"""Compute per-round convergence metrics and the stop decision for the review loop.

Usage: metrics.py <path-to-ledger.json> <round-number>
Appends a row to <ledger-dir>/rounds.md and prints a JSON verdict on stdout.
"""
import json, sys, os

OPENISH = {"open", "partial"}

def die(msg):
    print(f"metrics: {msg}", file=sys.stderr)
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

SEV_RANK = {"blocker": 3, "major": 2, "minor": 1}

def max_open_severity(findings, r):
    return max([SEV_RANK.get(f.get("severity"), 0) for f in findings
                if status_at(f, r) in OPENISH], default=0)

def promotions(findings, r):
    up = down = 0
    for f in findings:
        for e in f.get("severity_history", []) or []:
            if e.get("round") == r:
                if SEV_RANK.get(e.get("to"), 0) > SEV_RANK.get(e.get("from"), 0):
                    up += 1
                else:
                    down += 1
    return up, down

def converging_series(findings, r):
    """Every open finding is a regression the loop itself introduced, the
    worst open severity is non-increasing over three rounds, and nothing
    reopened: that is residue shrinking by construction, not churn."""
    open_now = [f for f in findings if status_at(f, r) in OPENISH]
    if not open_now or not all(f.get("introduced_by_fix") for f in open_now):
        return False
    if not (max_open_severity(findings, r) <= max_open_severity(findings, r - 1)
            <= max_open_severity(findings, r - 2)):
        return False
    return net_for(findings, r)[2] == 0 and net_for(findings, r - 1)[2] == 0

def main():
    if len(sys.argv) < 3:
        die("usage: metrics.py <ledger.json> <round>")
    path = sys.argv[1]
    try:
        N = int(sys.argv[2])
    except ValueError:
        die(f"round must be an integer, got '{sys.argv[2]}'")
    with open(path) as fh:
        ledger = json.load(fh)
    findings = ledger.get("findings", [])
    validate(findings)
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
        if a & b & c:
            # Healthy-churn exception: a region that keeps yielding NEW,
            # net-positive, non-reopening findings is convergent residue
            # (each fix exposing a smaller issue), not oscillation. Judged
            # on the last two rounds — round 1 is the seed and always net-
            # negative. Reopens or non-positive net still count as thrashing.
            healthy = all(
                net_for(findings, r)[3] > 0 and net_for(findings, r)[2] == 0
                for r in (N, N - 1))
            region_thrash = not (healthy or converging_series(findings, N))
    any_reopened_twice = any(reopen_count(f) >= 2 for f in findings)
    promoted, demoted = promotions(findings, N)
    usage = ledger.get("usage") or {}
    round_tokens = sum((usage.get(str(N)) or {}).values())
    cumulative_tokens = sum(sum(v.values()) for k, v in usage.items() if k.isdigit() and int(k) <= N)
    budget = ledger.get("token_budget")
    over_budget = bool(budget) and cumulative_tokens >= int(budget)

    # decision, in priority order
    if blockers_open == 0 and majors_open == 0 and not new_blocker_major:
        decision, reason = "converged", "no open blockers or majors; none newly introduced"
    elif over_budget:
        decision, reason = "budget", f"cumulative {cumulative_tokens} tokens >= token_budget {budget}; stop, closeout, report"
    elif any_reopened_twice or (net_prev is not None and net <= 0 and net_prev <= 0) or region_thrash:
        if blockers_open == 0 and closed > 0:
            decision, reason = "thrashing_soft", "thrashing signals but with mitigating progress (0 open blockers, positive closes) — confirm with the human before aborting"
        else:
            decision, reason = "thrashing", "oscillation or non-positive net over two rounds or a churning region"
    elif disp_prev is not None and disp_now == disp_prev and len(disp_now) > 0:
        decision, reason = "stalemate", "identical disputed set for two consecutive rounds"
    elif (net_prev is not None and net <= 1 and net_prev <= 1
          and blockers_open == 0 and not new_blocker_major):
        # "Diminishing" must mean "nothing left to find" — net <= 1 includes
        # deeply negative rounds, so a round that spawned new majors (often
        # introduced_by_fix regressions) must never wind down to BACKLOG.
        decision, reason = "diminishing", "net <= 1 for two rounds, no open blockers, no new blockers/majors"
    elif N >= max_rounds:
        decision, reason = "backstop", "hit max_rounds"
    else:
        decision, reason = "continue", "progress continuing"

    verdict = {
        "round": N, "blockers_open": blockers_open, "majors_open": majors_open,
        "minors_open": minors_open, "closed": closed, "new": new,
        "reopened": reopened, "promoted": promoted, "demoted": demoted,
        "net": net, "tokens": round_tokens, "cumulative_tokens": cumulative_tokens,
        "decision": decision, "reason": reason,
    }

    rounds_md = os.path.join(os.path.dirname(os.path.abspath(path)), "rounds.md")
    header = "| Round | Blockers | Majors | Minors | Closed | New | Reopened | Promoted | Net | Tokens | Decision |\n"
    sep = "|-------|----------|--------|--------|--------|-----|----------|----------|-----|--------|----------|\n"
    if not os.path.exists(rounds_md):
        with open(rounds_md, "w") as fh:
            fh.write(header + sep)
    else:
        # Idempotent per round: metrics may legitimately run several times
        # for one round (functional lane, perf lane, post-fix-review) —
        # replace the round's row instead of stacking three of them.
        with open(rounds_md) as fh:
            lines = [l for l in fh if not l.startswith(f"| {N} |")]
        with open(rounds_md, "w") as fh:
            fh.writelines(lines)
    with open(rounds_md, "a") as fh:
        fh.write(f"| {N} | {blockers_open} | {majors_open} | {minors_open} | "
                 f"{closed} | {new} | {reopened} | {promoted} | {net:+d} | {round_tokens} | {decision} |\n")

    with open(os.path.join(os.path.dirname(os.path.abspath(path)),
                           "verdict.json"), "w") as fh:
        json.dump(verdict, fh, indent=2)
        fh.write("\n")
    print(json.dumps(verdict, indent=2))

if __name__ == "__main__":
    main()
