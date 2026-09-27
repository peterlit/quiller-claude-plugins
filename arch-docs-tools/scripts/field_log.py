#!/usr/bin/env python3
"""Field telemetry for the feedback bundle: anomalies and dispatch timing.

Usage:
  field_log.py anomaly <loop-dir> <code> "<one line>" [--source NAME] [--once] [--dedupe]
  field_log.py dispatch-start <loop-dir>      (PreToolUse Agent payload on stdin)
  field_log.py dispatch-end <loop-dir>        (SubagentStop payload on stdin)
  field_log.py codes                          (print the anomaly vocabulary)

Appends to <loop-dir>/feedback/anomalies.jsonl and
<loop-dir>/feedback/dispatches.jsonl. Both are CONCLUSIONS (small, allowlisted,
committed): they are the evidence a field report cites, captured at the moment
a script decides something instead of reconstructed from memory eight hours
later (measured: every field memo spent a section re-deriving what a script
had already printed and the orchestrator had already scrolled past).

Contract: this module NEVER fails its caller and NEVER creates a loop
directory. Every error is swallowed; the CLI always exits 0. A hook or a
verb that records telemetry must behave exactly as it did before it recorded.
Set FIELD_LOG_OFF=1 to silence it (archive's pre-scan does).

--once    skip if this CODE is already recorded in the loop (a condition,
          not an event: "jq is missing" is true once, not per Bash call)
--dedupe  skip if this exact (code, detail) pair is already recorded
"""
import datetime, fcntl, json, os, re, sys, time

# The first vocabulary — each code is a place a shipped script already
# decides something and used to only print it. Orchestrators add their own
# observations under "workaround" (or any kebab-case code) via
# `merge_ledger.py anomaly`.
CODES = {
    "workaround": "the orchestrator worked around the plugin (hand-built a chunk, abandoned a verb)",
    "lane-skipped": "a panel lane was skipped (no consent, disabled, unknown type)",
    "lane-error": "a panel lane failed (auth, quota, launch, no-json, other)",
    "lane-timeout": "a panel lane hit its timeout",
    "lane-cached": "a panel lane's existing candidates were reused, not re-run",
    "lane-capped": "a panel lane was capped on the final pass (0 kept of >=5 at seed)",
    "lane-disabled-by-precision": "a panel lane was disabled by its cross-loop kept rate",
    "dispatch-count-mismatch": "the live-dispatch counter was non-zero when a round closed",
    "session-gate-blocked": "the first dispatch was blocked: oversized session transcript",
    "read-guard-denied": "the read guard denied a command",
    "commit-guard-denied": "the commit guard denied a staging command",
    "commit-guard-no-jq": "commit_guard ran without jq and could not read the command",
    "archive-duplicates": "sync-conflict duplicate names appeared during archive",
    "archive-late-duplicates": "sync-conflict duplicate names appeared after the settle pass",
    "hygiene-violation": "hygiene_check reported tracked scratch, a duplicate name, or an oversized file",
    "mutate-baseline-red": "mutate.py refused: a test_cmd is red on the unmutated tree",
    "mutate-dirty-refused": "mutate.py refused: uncommitted changes to the manifest's files",
    "mutate-allow-dirty": "mutate.py ran with --allow-dirty over uncommitted changes",
    "mutate-stale-refused": "mutate.py refused: a newer version of the plugin is installed beside it",
    "notes-over-ceiling": "HARNESS_NOTES.md is still over its byte ceiling after rotation",
    "plan-lint-problem": "plan_round's contract lint reported a problem",
    "plan-degenerated": "a targeted pass degenerated to findings+smoke",
    "plan-unchunked": "plan_round hard-errored: a selected test case landed in no chunk",
    "grant-probe-failed": "a worker failed the Stage-0 real-tap grant probe",
    "driver-ping-failed": "the shipped driver did not answer ping on a worker",
    "usage-repeat-notification": "a dispatch's completion was notified more than once",
    "model-fallback": "a pinned agent ran on another model after three transport failures",
}

def off():
    return os.environ.get("FIELD_LOG_OFF", "").strip().lower() in ("1", "true", "yes")

def scrub(text):
    """One line, bounded, with the home directory folded to ~ — these rows
    travel into a report that leaves the host repo."""
    s = " ".join(str(text).split())
    home = os.path.expanduser("~")
    if home and home != "/":
        s = s.replace(home, "~")
    return s[:400]

def feedback_dir(loop, create=True):
    if not loop or not os.path.isdir(loop):
        return None          # never conjure a loop dir from a hook
    d = os.path.join(loop, "feedback")
    if create:
        os.makedirs(d, exist_ok=True)
    return d if os.path.isdir(d) else None

def loop_phase(loop):
    try:
        with open(os.path.join(loop, ".phase"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""

def loop_round(loop):
    try:
        with open(os.path.join(loop, "ledger.json"), encoding="utf-8") as fh:
            r = json.load(fh).get("round")
        return r if isinstance(r, int) and not isinstance(r, bool) else None
    except (OSError, ValueError, AttributeError):
        return None

def read_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue      # a torn line must not hide the rest
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        pass
    return rows

def append_row(path, row):
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)     # parallel testers return together
        fh.write(json.dumps(row, sort_keys=True) + "\n")

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def norm_code(code):
    c = re.sub(r"[^a-z0-9]+", "-", str(code).strip().lower()).strip("-")
    return c or "workaround"

def anomaly(loop, code, detail, source="", once=False, dedupe=False):
    """Record one anomaly. Returns the row written, or None when skipped."""
    if off():
        return None
    try:
        d = feedback_dir(loop)
        if not d:
            return None
        path = os.path.join(d, "anomalies.jsonl")
        code, detail = norm_code(code), scrub(detail)
        if once or dedupe:
            for r in read_rows(path):
                if r.get("code") == code and (once or r.get("detail") == detail):
                    return None
        row = {"ts": now_iso(), "code": code, "detail": detail,
               "source": scrub(source)[:64], "phase": loop_phase(loop)}
        rnd = loop_round(loop)
        if rnd is not None:
            row["round"] = rnd
        append_row(path, row)
        return row
    except Exception:
        return None

def _payload():
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def base_phase(phase):
    return re.sub(r":(dispatched|waiting:.*)$", "", phase or "")

def live(phase):
    return bool(re.match(r"(round|seed)", phase or ""))

def dispatch(loop, event, payload):
    """Record a dispatch start/end. Wall-clock per dispatch used to be
    hand-timed by one field agent and absent from the other's reports; the
    hooks already fire at both ends, so the record costs no tokens."""
    if off():
        return None
    try:
        phase = loop_phase(loop)
        if not live(phase):
            return None
        d = feedback_dir(loop)
        if not d:
            return None
        row = {"event": event, "ts": round(time.time(), 3), "iso": now_iso(),
               "phase": base_phase(phase)}
        rnd = loop_round(loop)
        if rnd is not None:
            row["round"] = rnd
        if event == "start":
            ti = payload.get("tool_input")
            ti = ti if isinstance(ti, dict) else {}
            row["agent"] = scrub(ti.get("subagent_type") or "")[:80]
            row["label"] = scrub(ti.get("description") or "")[:120]
            if payload.get("tool_use_id"):
                row["tool_use_id"] = str(payload["tool_use_id"])[:80]
            tp = payload.get("transcript_path") or ""
            if tp and os.path.exists(tp):
                # Session size AT the dispatch: cost is turns x context, and
                # this is the context the orchestrator paid for the turn.
                row["session_mb"] = round(os.path.getsize(tp) / 1048576, 2)
        else:
            row["agent"] = scrub(payload.get("agent_type") or "")[:80]
            if payload.get("agent_id"):
                row["agent_id"] = str(payload["agent_id"])[:80]
        append_row(os.path.join(d, "dispatches.jsonl"), row)
        return row
    except Exception:
        return None

def short_agent(name):
    """`review-loop-tools:implementer` and `implementer` are one agent."""
    return (name or "").split(":")[-1].strip().lower()

def pair_dispatches(rows):
    """Pair start/end events into dispatches. An end matches the OLDEST
    unmatched start of the same agent type, else the oldest unmatched start
    (older harnesses do not name the agent on SubagentStop). Returns
    (dispatches, unmatched_starts, unmatched_ends)."""
    open_starts, done, stray = [], [], 0
    for r in sorted(rows, key=lambda r: r.get("ts") or 0):
        if r.get("event") == "start":
            open_starts.append(r)
        elif r.get("event") == "end":
            want = short_agent(r.get("agent"))
            pick = None
            if want:
                pick = next((s for s in open_starts
                             if short_agent(s.get("agent")) == want), None)
            if pick is None and open_starts:
                # Only fall back to an unnamed/mismatched start when the end
                # carries no agent name, or no start carries one.
                if not want or not any(short_agent(s.get("agent")) for s in open_starts):
                    pick = open_starts[0]
            if pick is None:
                stray += 1
                continue
            open_starts.remove(pick)
            done.append({"phase": pick.get("phase"), "round": pick.get("round"),
                         "agent": short_agent(pick.get("agent")) or want or "unknown",
                         "label": pick.get("label", ""),
                         "start": pick.get("iso"), "end": r.get("iso"),
                         "wall_s": round(max(0.0, (r.get("ts") or 0) - (pick.get("ts") or 0)), 1),
                         "session_mb": pick.get("session_mb")})
    return done, open_starts, stray

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return
    verb, rest = args[0], args[1:]
    if verb == "codes":
        for k in sorted(CODES):
            print(f"{k}\t{CODES[k]}")
        return
    if verb == "anomaly":
        flags = {a for a in rest if a in ("--once", "--dedupe")}
        source = ""
        pos, it = [], iter([a for a in rest if a not in flags])
        for a in it:
            if a == "--source":
                source = next(it, "")
            else:
                pos.append(a)
        if len(pos) < 3:
            print("usage: field_log.py anomaly <loop-dir> <code> \"<one line>\" "
                  "[--source NAME] [--once] [--dedupe]", file=sys.stderr)
            return
        row = anomaly(pos[0], pos[1], " ".join(pos[2:]), source=source,
                      once="--once" in flags, dedupe="--dedupe" in flags)
        print(json.dumps({"recorded": bool(row), "code": norm_code(pos[1])}))
        return
    if verb in ("dispatch-start", "dispatch-end") and rest:
        dispatch(rest[0], "start" if verb == "dispatch-start" else "end", _payload())
        return
    print(__doc__, file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
