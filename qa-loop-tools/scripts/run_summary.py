#!/usr/bin/env python3
"""The objective half of a field report: <loop-dir>/feedback/run-summary.json.

Usage: run_summary.py <loop-dir> [--print] [--stop-note "<how it ended>"]

render_report.py calls this at report time, so every finished loop leaves a
machine-readable record of what ran and how it went — before anyone decides
to write feedback. `/<plugin>:feedback` reads it; a field report embeds it.

What it records, and why each part exists:
- plugin + version, read from THIS script's own plugin.json — the code that
  actually ran, not what a report author remembers — beside the matching
  entry in ~/.claude/plugins/installed_plugins.json (measured: one whole
  feedback cycle went to "0.4.0 features are absent" reports from a stale
  install). A mismatch means a symlinked or --plugin-dir install; it is
  recorded, not judged.
- platform probes; a failed probe is "unknown", never absent.
- settings, rounds, the stop condition and the verdict row per round.
- finding COUNTS by severity and status, fix-review rejections, proposals.
  Never claims, ids, regions or evidence: this file leaves the host repo.
- unattended defaults taken, hygiene violations, anomalies, per-dispatch
  wall-clock, reported usage, panel tallies and lane telemetry.

Every path is folded to ~ and nothing here reads source code.
"""
import datetime, glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import field_log   # noqa: E402  (shared telemetry helpers)

SCHEMA = 1
OPENISH = ("open", "partial")
SEVS = ("blocker", "major", "minor")

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default

def load_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""

def tilde(p):
    home = os.path.expanduser("~")
    p = str(p)
    return "~" + p[len(home):] if home and p.startswith(home) else p

def probe(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or r.stderr).strip()
        return " ".join(out.split())[:120] if r.returncode == 0 and out else "unknown"
    except Exception:
        return "unknown"

def plugin_identity():
    root = os.path.dirname(HERE)
    pj = load_json(os.path.join(root, ".claude-plugin", "plugin.json"), {}) or {}
    name, version = pj.get("name") or "unknown", pj.get("version") or "unknown"
    out = {"name": name, "version": version, "running_from": tilde(root),
           "installed": None, "install_matches_running": None}
    reg = load_json(os.path.expanduser("~/.claude/plugins/installed_plugins.json"), {}) or {}
    entries = []
    for key, val in (reg.get("plugins") or {}).items():
        if key.split("@")[0] == name and isinstance(val, list):
            for e in val:
                if isinstance(e, dict):
                    entries.append((key, e))
    if entries:
        real_root = os.path.realpath(root)
        key, e = next(((k, e) for k, e in entries
                       if os.path.realpath(e.get("installPath") or "") == real_root),
                      entries[0])
        ipath = e.get("installPath") or ""
        out["installed"] = {"key": key, "version": e.get("version") or "unknown",
                            "path": tilde(ipath), "last_updated": e.get("lastUpdated"),
                            "git_commit": (e.get("gitCommitSha") or "")[:12] or None,
                            "symlink": os.path.islink(ipath.rstrip("/")) if ipath else False}
        out["install_matches_running"] = (
            e.get("version") == version and os.path.realpath(ipath) == real_root
            and not out["installed"]["symlink"])
    return out

def platform_info(plugin_name):
    info = {"macos": probe(["sw_vers", "-productVersion"]),
            "arch": probe(["uname", "-m"]),
            "claude": probe(["claude", "--version"]),
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "git": probe(["git", "--version"])}
    if plugin_name.startswith("qa-"):
        info["xcode"] = probe(["xcodebuild", "-version"])
    return info

def parse_rounds(text):
    """rounds.md -> (rows, notes). Rows are the metrics table keyed by the
    lowercased column names; notes are the `> …` lines next-round appends
    (unattended defaults)."""
    rows, notes, cols = [], [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            notes.append(s.lstrip("> ").strip())
            continue
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cols is None:
            cols = [re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in cells]
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        row = {}
        for k, v in zip(cols, cells):
            row[k] = int(v) if re.fullmatch(r"[+-]?\d+", v) else v
        rows.append(row)
    return rows, notes

def finding_counts(findings):
    by_sev, by_status, matrix = {}, {}, {}
    rejections = proposals_open = proposals_total = 0
    introduced = fix_risk = reopened = panel_sourced = 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        sev, st = f.get("severity") or "unknown", f.get("current_status") or "unknown"
        by_sev[sev] = by_sev.get(sev, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        matrix.setdefault(sev, {})
        matrix[sev][st] = matrix[sev].get(st, 0) + 1
        rej = f.get("rejections") or []
        if isinstance(rej, list) and rej:
            rejections += len(rej)
        elif "FIX REJECTED" in (f.get("note") or ""):
            rejections += 1
        if f.get("routing") == "proposal":
            proposals_total += 1
            proposals_open += st in OPENISH
        introduced += bool(f.get("introduced_by_fix"))
        fix_risk += bool(f.get("fix_risk"))
        hist = [e.get("status") for e in (f.get("status_history") or [])
                if isinstance(e, dict)]
        reopened += sum(1 for a, b in zip(hist, hist[1:]) if a == "fixed" and b == "open")
        srcs = f.get("sources") or f.get("source") or []
        srcs = srcs if isinstance(srcs, list) else [srcs]
        panel_sourced += any(str(x).startswith("panel") for x in srcs)
    return {"total": len(findings), "by_severity": by_sev, "by_status": by_status,
            "by_severity_and_status": matrix,
            "open_blockers_majors": sum(
                1 for f in findings if isinstance(f, dict)
                and f.get("current_status") in OPENISH
                and f.get("routing", "auto") != "proposal"
                and f.get("severity") in ("blocker", "major")),
            "fix_review_rejections": rejections,
            "proposals": {"total": proposals_total, "open": proposals_open},
            "introduced_by_fix": introduced, "fix_risk_flagged": fix_risk,
            "reopen_events": reopened, "panel_sourced": panel_sourced}

def stop_info(loop, findings, verdict, stop_note):
    if not verdict:
        return {"decision": "unknown", "headline": "unknown", "round": None,
                "reason": "no verdict.json", "closeout_ran": False, "stop_note": stop_note}
    closeout = bool(glob.glob(os.path.join(loop, "fragments", "round-*-closeout.json")))
    open_bm = sum(1 for f in findings if isinstance(f, dict)
                  and f.get("current_status") in OPENISH
                  and f.get("routing", "auto") != "proposal"
                  and f.get("severity") in ("blocker", "major"))
    decision = verdict.get("decision")
    headline = decision
    # Same relabel render_report applies to the report headline.
    if closeout and open_bm == 0 and decision in ("thrashing_soft", "backstop"):
        headline = "converged-in-closeout"
    return {"decision": decision, "headline": headline, "round": verdict.get("round"),
            "reason": field_log.scrub(verdict.get("reason") or ""),
            "closeout_ran": closeout, "stop_note": field_log.scrub(stop_note or "")}

def settings(loop, ledger, plugin_name):
    keep = ("max_rounds", "token_budget", "parallel_testers", "emit_regression_tests",
            "regression_test_arming", "thrashing_consulted", "implemented_rounds")
    out = {k: ledger[k] for k in keep if k in ledger}
    out["scoped"] = bool(ledger.get("scope"))   # the range itself names host shas/paths
    env = {}
    for k in ("REVIEW_LOOP_UNATTENDED", "QA_LOOP_UNATTENDED", "REVIEW_LOOP_MAX_DIFF",
              "QA_NOTES_CEILING_KB", "REVIEW_LOOP_ARCHIVE_SETTLE_S"):
        if os.environ.get(k):
            env[k] = os.environ[k][:40]
    if os.environ.get("REVIEW_LOOP_TEST_CMD"):
        env["REVIEW_LOOP_TEST_CMD"] = "(set)"     # the command is the host's business
    out["env"] = env
    panel = load_json(os.path.join(loop, "panel.json"))
    if isinstance(panel, dict) and isinstance(panel.get("lanes"), list):
        out["panel_lanes"] = [
            {"name": str(l.get("name"))[:64], "type": l.get("type"),
             "model": l.get("model"), "timeout_s": l.get("timeout_s"),
             "enabled": l.get("enabled", True)}
            for l in panel["lanes"] if isinstance(l, dict)]
        out["panel_rounds"] = panel.get("rounds")
    return out

def panel_runs(loop):
    """Lane telemetry from each panel run summary (fragments are scratch, so
    this is the only place the numbers reach a committed file)."""
    runs = {}
    for p in sorted(glob.glob(os.path.join(loop, "fragments", "panel", "round-*.run.json"))):
        d = load_json(p)
        if not isinstance(d, dict):
            continue
        key = os.path.basename(p)[len("round-"):-len(".run.json")]
        lanes = []
        for r in d.get("lanes") or []:
            if not isinstance(r, dict):
                continue
            row = {k: r[k] for k in ("lane", "status", "error_kind", "elapsed_s", "tokens",
                                     "model_used", "filed", "cap", "cap_reason",
                                     "dropped_no_evidence", "timeout_s") if k in r}
            if r.get("note") and r.get("status") not in ("ok", "cached"):
                row["note"] = field_log.scrub(r["note"])[:200]
            lanes.append(row)
        runs[key] = {"failed": d.get("failed"), "skipped": d.get("skipped"), "lanes": lanes}
    return runs

def coverage_counts(loop):
    cov = load_json(os.path.join(loop, "coverage.json"))
    if not isinstance(cov, dict) or not isinstance(cov.get("rounds"), dict) or not cov["rounds"]:
        return None
    try:
        last = str(max(int(k) for k in cov["rounds"]))
    except ValueError:
        return None
    counts, personas = {}, set()
    for per in cov["rounds"][last].values():
        if not isinstance(per, dict):
            continue
        for persona, rec in per.items():
            personas.add(persona)
            st = (rec or {}).get("status") or "unknown"
            counts[st] = counts.get(st, 0) + 1
    return {"round": int(last), "test_cases": len(cov["rounds"][last]),
            "results": counts, "personas": sorted(personas)}

def closeout_suites(loop):
    suites = {}
    for cf in sorted(glob.glob(os.path.join(loop, "fragments", "round-*-closeout.json"))):
        frag = load_json(cf) or {}
        if isinstance(frag, dict) and isinstance(frag.get("suites"), dict):
            for name, t in frag["suites"].items():
                if isinstance(t, dict):
                    suites[str(name)[:80]] = {k: t.get(k) for k in ("executed", "failed", "skipped")}
    return suites

def loop_root(loop):
    """The loop directory itself, even when `loop` is one of its archives
    (<loop-dir>/archive/<name>) — feedback filed after a loop was archived
    still describes the host repo, not a directory called "archive"."""
    p = os.path.abspath(loop)
    if os.path.basename(os.path.dirname(p)) == "archive":
        return os.path.dirname(os.path.dirname(p))
    return p

def hygiene(loop):
    script = os.path.join(HERE, "hygiene_check.sh")
    if not os.path.exists(script):
        return {"ran": False, "violations": []}
    loop = loop_root(loop)
    repo = os.path.dirname(os.path.abspath(loop))
    try:
        r = subprocess.run(["bash", script, os.path.basename(os.path.abspath(loop))],
                           capture_output=True, text=True, timeout=60, cwd=repo,
                           env=dict(os.environ, FIELD_LOG_OFF="1"))
    except Exception:
        return {"ran": False, "violations": []}
    lines = [field_log.scrub(l) for l in r.stdout.splitlines()
             if l.strip() and not l.rstrip().endswith(": clean")]
    # Counts by KIND only: a duplicate's or a tracked file's name can echo
    # a host file, and this summary leaves the host repo.
    kinds = {}
    for l in lines:
        k = next((name for name in ("scratch tracked", "duplicate name",
                                    "large tracked file", "tracked file missing",
                                    "restored") if name in l), "gitignore")
        kinds[k] = kinds.get(k, 0) + 1
    return {"ran": True, "violation_count": len(lines), "by_kind": kinds}

def git_state(loop):
    loop = loop_root(loop)
    repo = os.path.dirname(os.path.abspath(loop))
    def git(*a):
        try:
            return subprocess.run(["git", "-C", repo] + list(a), capture_output=True,
                                  text=True, timeout=20)
        except Exception:
            return None
    inside = git("rev-parse", "--is-inside-work-tree")
    if not inside or inside.returncode != 0:
        return {"git_repo": False}
    ign = git("check-ignore", "-q", os.path.basename(os.path.abspath(loop)))
    return {"git_repo": True, "loop_dir_ignored": bool(ign and ign.returncode == 0)}

def loop_window(loop, dispatch_rows):
    """(start, end) epoch seconds for the loop — the usage window. Dispatch
    records are exact; without them (a pre-0.15 loop) fall back to the
    oldest scratch file, then the ledger's birth."""
    starts = [r["ts"] for r in dispatch_rows if isinstance(r.get("ts"), (int, float))]
    basis = "dispatches.jsonl"
    if starts:
        # Setup happens before the first dispatch (archive, hygiene, the
        # seed diff, a panel run): the ledger's creation marks it. Trusted
        # only when it is within a day before — a copied or restored ledger
        # carries an unrelated birth time.
        try:
            st = os.stat(os.path.join(loop, "ledger.json"))
            born = getattr(st, "st_birthtime", None)
            if born and 0 < min(starts) - born < 86400:
                starts.append(born)
                basis = "ledger.json creation, then dispatches.jsonl"
        except OSError:
            pass
    if not starts:
        basis = "oldest file in fragments/ and briefs/"
        for sub in ("fragments", "briefs"):
            for root, _d, files in os.walk(os.path.join(loop, sub)):
                for fn in files:
                    try:
                        st = os.stat(os.path.join(root, fn))
                        starts.append(min(getattr(st, "st_birthtime", st.st_mtime),
                                          st.st_mtime))
                    except OSError:
                        pass
    if not starts:
        basis = "ledger.json"
        try:
            st = os.stat(os.path.join(loop, "ledger.json"))
            starts.append(min(getattr(st, "st_birthtime", st.st_mtime), st.st_mtime))
        except OSError:
            return None, None, "unknown"
    ends = [r["ts"] for r in dispatch_rows if isinstance(r.get("ts"), (int, float))]
    for name in ("REPORT.md", "verdict.json", "ledger.json"):
        try:
            ends.append(os.stat(os.path.join(loop, name)).st_mtime)
        except OSError:
            pass
    return min(starts), max(ends) if ends else None, basis

def iso(ts):
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def build(loop, stop_note=""):
    ledger = load_json(os.path.join(loop, "ledger.json"))
    missing = []
    if not isinstance(ledger, dict):
        ledger = {}
        missing.append("ledger.json (no loop state here — counts are empty)")
    findings = [f for f in (ledger.get("findings") or []) if isinstance(f, dict)]
    verdict = load_json(os.path.join(loop, "verdict.json"), {}) or {}
    if not verdict:
        missing.append("verdict.json (metrics never ran, or the loop was aborted)")
    rounds_text = load_text(os.path.join(loop, "rounds.md"))
    if not rounds_text:
        missing.append("rounds.md")
    rounds, notes = parse_rounds(rounds_text)
    plugin = plugin_identity()

    fdir = os.path.join(loop, "feedback")
    drows = field_log.read_rows(os.path.join(fdir, "dispatches.jsonl"))
    arows = field_log.read_rows(os.path.join(fdir, "anomalies.jsonl"))
    if not drows:
        missing.append("feedback/dispatches.jsonl (loop ran on a plugin older than "
                       "this one, or its hooks were inactive) — no wall-clock")
    pairs, unmatched, stray = field_log.pair_dispatches(drows)
    by_agent = {}
    for p in pairs:
        a = by_agent.setdefault(p["agent"], {"dispatches": 0, "wall_s": 0.0})
        a["dispatches"] += 1
        a["wall_s"] = round(a["wall_s"] + p["wall_s"], 1)
    by_code = {}
    for r in arows:
        by_code[r.get("code") or "unknown"] = by_code.get(r.get("code") or "unknown", 0) + 1
    start, end, basis = loop_window(loop, drows)

    usage = ledger.get("usage") if isinstance(ledger.get("usage"), dict) else {}
    usage_total = 0
    by_role = {}
    for rnd in usage.values():
        if isinstance(rnd, dict):
            for role, tok in rnd.items():
                if isinstance(tok, (int, float)) and not isinstance(tok, bool):
                    usage_total += tok
                    by_role[role] = by_role.get(role, 0) + tok

    summary = {
        "schema": SCHEMA,
        "generated_at": field_log.now_iso(),
        "plugin": plugin,
        "host": {"repo": os.path.basename(os.path.dirname(loop_root(loop))),
                 "loop_dir": os.path.basename(loop_root(loop)),
                 "archived_as": (os.path.basename(os.path.abspath(loop))
                                 if loop_root(loop) != os.path.abspath(loop) else None),
                 **git_state(loop)},
        "platform": platform_info(plugin["name"]),
        "settings": settings(loop, ledger, plugin["name"]),
        "window": {"started_at": iso(start), "ended_at": iso(end), "basis": basis,
                   "wall_s": round(end - start, 1) if start and end and end >= start else None},
        "rounds": {"count": len(rounds), "last_round": ledger.get("round"),
                   "table": rounds, "notes": [field_log.scrub(n) for n in notes]},
        "stop": stop_info(loop, findings, verdict, stop_note),
        "findings": finding_counts(findings),
        "unattended_defaults": [field_log.scrub(n) for n in notes
                                if "unattended default" in n.lower()],
        "usage_reported": {"total": usage_total, "token_budget": ledger.get("token_budget"),
                           "by_round": usage, "by_role": by_role,
                           "scale_note": "harness-reported; measured 4-7x (code) to ~11x "
                                         "(simulator) below billed effective"},
        "panel": {"tallies": ledger.get("panel") if isinstance(ledger.get("panel"), dict) else {},
                  "runs": panel_runs(loop)},
        "dispatches": {"count": len(pairs), "unreturned": len(unmatched),
                       "unmatched_returns": stray, "by_agent": by_agent, "rows": pairs},
        "anomalies": {"count": len(arows), "by_code": by_code, "rows": arows},
        "hygiene": hygiene(loop),
        "closeout_suites": closeout_suites(loop),
        "missing": missing,
    }
    cov = coverage_counts(loop)
    if cov:
        summary["coverage"] = cov
    return summary

def write(loop, stop_note=""):
    """Build and write the summary; returns its path."""
    summary = build(loop, stop_note)
    fdir = field_log.feedback_dir(loop)
    if not fdir:
        raise OSError(f"{loop} is not a directory")
    path = os.path.join(fdir, "run-summary.json")
    tmp = path + ".partial"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    loop = args[0]
    note = args[args.index("--stop-note") + 1] \
        if "--stop-note" in args and args.index("--stop-note") + 1 < len(args) else ""
    if not os.path.isdir(loop):
        print(f"run_summary: {loop} is not a directory", file=sys.stderr)
        sys.exit(1)
    if "--print" in args:
        print(json.dumps(build(loop, note), indent=2))
        return
    path = write(loop, note)
    print(json.dumps({"run_summary": path}))

if __name__ == "__main__":
    main()
