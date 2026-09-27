#!/usr/bin/env python3
"""Self-test for the loop hooks. Runs the real hook scripts against a
tempdir loop directory with fake hook payloads on stdin — never a live
loop. Exits nonzero on the first failure.

Covers (all 0.14.0 field fixes, each measured in a real run):
- dispatch_stamp / subagent_guard keep a LIVE-DISPATCH COUNT: two overlapping
  dispatches need two SubagentStops before ":dispatched" is stripped (the
  single-bit marker let the first return unmark the second, and the Stop
  hook then blocked ordinary turns); a missing count file (pre-0.14 state)
  strips on the first return; the count never goes negative.
- read_guard matches command POSITIONS: a heredoc or quoted string that
  merely contains `xcodebuild test` is allowed; a real unfiltered run is
  still denied; a filtered run passes.
- commit_guard arms only while a loop is LIVE (round*/seed*/awaiting-human):
  `git add -A` passes when .phase says done, is blocked during a round.
- session_guard stands down once briefs/.session-ok exists.

0.16.0 field fixes (the 2026-09-20 weatherapp report, each replayed from
the run's own transcript):
- the COUNT is the source of truth: a dispatch under ":waiting:" is counted,
  a same-batch phase write cannot strand it, the Stop hook allows a wait
  while the count is above zero, and the marker is still stripped at zero.
- set-round / next-round reset a count left above zero.
- set-usage after next-round corrects rounds.md and verdict.json and says
  over_budget; briefs carry this release's script paths.
- a closeout fragment must carry `suites` — only during the closeout review.
- hygiene reports tracked files missing from disk; --restore moves back an
  unambiguous duplicate and nothing else.
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

PASS = 0
def ok(cond, label, detail=""):
    global PASS
    if not cond:
        print(f"FAIL: {label}\n{detail}", file=sys.stderr)
        sys.exit(1)
    PASS += 1
    print(f"ok: {label}")

def hook(name, args, payload, cwd):
    return subprocess.run(["bash", os.path.join(SCRIPTS, name)] + args,
                          input=json.dumps(payload), capture_output=True,
                          text=True, cwd=cwd)

def phase(loop):
    with open(os.path.join(loop, ".phase")) as fh:
        return fh.read().strip()

def main():
    td = tempfile.mkdtemp(prefix="hooks-selftest-")
    try:
        subprocess.run(["git", "init", "-q"], cwd=td, check=True)
        loop = os.path.join(td, ".review-loop")
        os.makedirs(os.path.join(loop, "briefs"))
        # An oversized-transcript check needs a transcript path; give a tiny one.
        tp = os.path.join(td, "transcript.jsonl")
        open(tp, "w").write("{}\n")
        agent_payload = {"tool_name": "Agent", "transcript_path": tp}

        # ---------- dispatch counter ----------
        open(os.path.join(loop, ".phase"), "w").write("round-1-review\n")
        r = hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        ok(r.returncode == 0 and phase(loop) == "round-1-review:dispatched",
           "first dispatch stamps :dispatched")
        cnt = os.path.join(loop, "briefs", ".dispatched")
        ok(open(cnt).read().strip() == "1", "first dispatch writes count 1")
        r = hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        ok(r.returncode == 0 and open(cnt).read().strip() == "2"
           and phase(loop) == "round-1-review:dispatched",
           "second overlapping dispatch counts to 2, marker unchanged")
        r = hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(r.returncode == 0 and phase(loop) == "round-1-review:dispatched"
           and open(cnt).read().strip() == "1",
           "first return decrements to 1 and KEEPS :dispatched (other agent live)")
        r = hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(r.returncode == 0 and phase(loop) == "round-1-review"
           and open(cnt).read().strip() == "0",
           "second return reaches 0 and strips :dispatched")
        r = hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(open(cnt).read().strip() == "0" and phase(loop) == "round-1-review",
           "a stray extra return never goes negative")
        # Pre-0.14 state: marker present, no count file -> strip on first return.
        open(os.path.join(loop, ".phase"), "w").write("round-2-implementing:dispatched\n")
        os.remove(cnt)
        r = hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(phase(loop) == "round-2-implementing",
           "missing count file (pre-0.14) strips on the first return")
        # :waiting: is never re-stamped — but the dispatch IS counted.
        open(os.path.join(loop, ".phase"), "w").write("round-2-review:waiting:panel\n")
        r = hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        ok(phase(loop) == "round-2-review:waiting:panel",
           ":waiting: marker is left alone by the stamp")
        ok(open(cnt).read().strip() == "1",
           "a dispatch made under :waiting: is counted")

        # ---------- the reported sequence, replayed ----------
        def stop_hook():
            return hook("loop_guard.sh", [".review-loop"], {"stop_hook_active": False}, td).returncode
        def count():
            return open(cnt).read().strip()
        open(cnt, "w").write("0\n")
        open(os.path.join(loop, ".phase"), "w").write("round-2-review:waiting:panel-final\n")
        hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)   # implementer
        open(os.path.join(loop, ".phase"), "w").write("round-2-implementing")   # same-batch write
        ok(count() == "1" and phase(loop) == "round-2-implementing",
           "a same-batch phase write erases the suffix but not the count")
        ok(stop_hook() == 0, "Stop hook allows the wait: count 1, no suffix")
        hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)   # verifier
        ok(count() == "2" and phase(loop) == "round-2-implementing:dispatched",
           "a dispatch on a bare phase adds to the count (never resets it to 1)")
        hook("subagent_guard.sh", [".review-loop"], {}, td)                   # verifier returns
        ok(count() == "1" and phase(loop) == "round-2-implementing:dispatched"
           and stop_hook() == 0,
           "first return keeps the mark: the implementer is still running")
        hook("subagent_guard.sh", [".review-loop"], {}, td)                   # implementer returns
        ok(count() == "0" and phase(loop) == "round-2-implementing",
           "last return strips the mark")
        ok(stop_hook() == 2, "Stop hook blocks again once nothing is running")
        # The other order: hook first, then the write.
        open(os.path.join(loop, ".phase"), "w").write("round-2-review\n")
        hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        open(os.path.join(loop, ".phase"), "w").write("round-2-implementing")
        ok(count() == "1" and stop_hook() == 0, "hook-first order: count survives the write")
        hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(count() == "0" and phase(loop) == "round-2-implementing" and stop_hook() == 2,
           "a return decrements on a bare phase too (the count used to strand)")
        # A return under :waiting: decrements and leaves the marker alone.
        open(os.path.join(loop, ".phase"), "w").write("round-2-review:waiting:panel\n")
        hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        hook("subagent_guard.sh", [".review-loop"], {}, td)
        ok(count() == "0" and phase(loop) == "round-2-review:waiting:panel",
           "a return under :waiting: decrements and never touches the marker")
        # done / awaiting-human: nothing is counted.
        open(os.path.join(loop, ".phase"), "w").write("done\n")
        hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        ok(count() == "0", "no count outside a live phase")

        # ---------- round boundary resets a stale count ----------
        def ml(*a):
            return subprocess.run([sys.executable, os.path.join(SCRIPTS, "merge_ledger.py")] + list(a),
                                  capture_output=True, text=True, cwd=td,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        with open(os.path.join(loop, "ledger.json"), "w") as fh:
            json.dump({"round": 1, "round_start_sha": None, "max_rounds": 5,
                       "token_budget": 250, "findings": [
                {"id": "a:one", "claim": "c", "severity": "major", "current_status": "open",
                 "first_seen_round": 0, "status_history": [{"round": 0, "status": "open"}]},
                {"id": "a:two", "claim": "c", "severity": "major", "current_status": "open",
                 "first_seen_round": 0, "status_history": [{"round": 0, "status": "open"}]}]}, fh)
        open(cnt, "w").write("2\n")
        r = ml("set-round", ".review-loop/ledger.json", "1")
        an = os.path.join(loop, "feedback", "anomalies.jsonl")
        ok(r.returncode == 0 and count() == "0" and os.path.exists(an)
           and "dispatch-count-mismatch" in open(an).read(),
           "set-round resets a count left above zero and records it", r.stderr)

        # ---------- late usage ----------
        subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q",
                        "--allow-empty", "-m", "i"], cwd=td, check=True)
        os.makedirs(os.path.join(loop, "fragments"), exist_ok=True)
        with open(os.path.join(loop, "fragments", "round-1.json"), "w") as fh:
            json.dump({"findings": [{"id": "a:one", "current_status": "fixed"}]}, fh)
        r = ml("next-round", ".review-loop", "1", "--fragment",
               ".review-loop/fragments/round-1.json", "--usage", "implementer=100")
        ok(r.returncode == 0 and json.loads(r.stdout)["decision"] == "continue",
           "next-round closes the round on the early figure", r.stderr)
        brief = json.load(open(os.path.join(loop, "briefs", "round-2-brief.json")))
        ok(os.path.isabs(brief["tools"]["mutate"])
           and os.path.samefile(brief["tools"]["mutate"], os.path.join(SCRIPTS, "mutate.py"))
           and len(brief["findings"]) == 1,
           "the brief names THIS release's mutate.py")
        r = ml("set-usage", ".review-loop/ledger.json", "1", "reviewer", "200")
        out = json.loads(r.stdout)
        row = [l for l in open(os.path.join(loop, "rounds.md")).read().splitlines()
               if l.startswith("| 1 |")][0]
        v = json.load(open(os.path.join(loop, "verdict.json")))
        ok(out["over_budget"] is True and out["rounds_md_updated"] and out["verdict_updated"],
           "a late figure that crosses the budget says so at once", r.stdout)
        ok([c.strip() for c in row.strip("|").split("|")][9] == "300"
           and v["tokens"] == 300 and v["cumulative_tokens"] == 300
           and v["decision"] == "continue" and row.rstrip().endswith("| continue |"),
           "rounds.md and verdict.json carry the settled figure; the decision is untouched",
           row)
        r = ml("add-usage", ".review-loop/ledger.json", "1", "reviewer", "50")
        row = [l for l in open(os.path.join(loop, "rounds.md")).read().splitlines()
               if l.startswith("| 1 |")][0]
        ok("| 350 |" in row and open(os.path.join(loop, "rounds.md")).read().endswith("\n"),
           "add-usage keeps the row in step; the table stays well-formed")
        qa_table = ("| Round | Pass | Blockers | Majors | Minors | Proposals | Closed | New | "
                    "Reopened | Promoted | Net | Tokens | Decision |\n" + "|---" * 13 + "|\n"
                    "| 1 | full | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | +1 | 100 | continue |\n")
        open(os.path.join(loop, "rounds.md"), "w").write(qa_table)
        ml("set-usage", ".review-loop/ledger.json", "1", "reviewer", "200")
        ok("| +1 | 300 | continue |" in open(os.path.join(loop, "rounds.md")).read(),
           "the Tokens cell is found by column NAME (the qa table has two more columns)")

        # ---------- closeout suites ----------
        frag = os.path.join(loop, "fragments", "round-2-closeout.json")
        def closeout(data, ph="round-2-closeout-review"):
            open(os.path.join(loop, ".phase"), "w").write(ph + "\n")
            with open(frag, "w") as fh:
                json.dump(data, fh)
            os.utime(frag, (1, 1))          # past the mid-write grace period
            return hook("subagent_guard.sh", [".review-loop"], {}, td)
        r = closeout({"findings": []})
        ok(r.returncode == 2 and "suites" in r.stderr,
           "a closeout fragment without suites is refused", r.stderr)
        ok(closeout({"findings": [], "suites": {}}).returncode == 2,
           "empty suites without a note is refused")
        ok(closeout({"findings": [], "suites": {}, "suites_note": "fold-in only"}).returncode == 0,
           "empty suites with a note passes")
        ok(closeout({"findings": [], "suites": {"unit": {"executed": 297, "failed": 0}}}).returncode == 2,
           "a suite missing a count is refused")
        full = {"findings": [], "suites": {"unit": {"executed": 297, "failed": 0, "skipped": 0},
                                           "ui": {"executed": 29, "failed": 0, "skipped": 14}}}
        ok(closeout(full).returncode == 0, "complete suites pass")
        ok(closeout({"findings": []}, ph="round-3-review").returncode == 0,
           "an old closeout fragment never blocks an ordinary review")
        closeout(full)
        open(os.path.join(loop, ".phase"), "w").write("done\n")
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "render_report.py"), ".review-loop"],
                       capture_output=True, text=True, cwd=td,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", FIELD_LOG_OFF="1"))
        rep = open(os.path.join(loop, "REPORT.md")).read()
        ok("| ui | 29 | 0 | 14 |" in rep, "the report's Closeout table renders the counts")
        with open(frag, "w") as fh:
            json.dump({"findings": []}, fh)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "render_report.py"), ".review-loop"],
                       capture_output=True, text=True, cwd=td,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", FIELD_LOG_OFF="1"))
        ok("Suite counts were not reported" in open(os.path.join(loop, "REPORT.md")).read(),
           "a closeout without suites says so instead of showing nothing")
        os.remove(frag)

        # ---------- hygiene: missing tracked files, --restore ----------
        arch = os.path.join(loop, "archive", "20260920-190516-bd73178")
        os.makedirs(arch)
        with open(os.path.join(loop, ".gitignore"), "w") as fh:
            fh.write("# Managed by review-loop-tools\n*\n!*/\n!.gitignore\n!REPORT.md\n"
                     "!ledger.json\n!rounds.md\n!verdict.json\n")
        for n in ("ledger.json", "rounds.md", "verdict.json", "REPORT.md"):
            open(os.path.join(arch, n), "w").write(n)
        rel = ".review-loop/archive/20260920-190516-bd73178"
        subprocess.run(["git", "add", ".review-loop/.gitignore"] + [f"{rel}/{n}" for n in
                       ("ledger.json", "rounds.md", "verdict.json", "REPORT.md")], cwd=td, check=True)
        subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q",
                        "-m", "archive"], cwd=td, check=True)
        def hyg(*a):
            return subprocess.run(["bash", os.path.join(SCRIPTS, "hygiene_check.sh"), ".review-loop"]
                                  + list(a), capture_output=True, text=True, cwd=td,
                                  env=dict(os.environ, FIELD_LOG_OFF="1")).stdout
        os.rename(os.path.join(arch, "ledger.json"), os.path.join(arch, "ledger 2.json"))
        os.rename(os.path.join(arch, "verdict.json"), os.path.join(arch, "verdict (conflicted copy).json"))
        shutil.copy(os.path.join(arch, "REPORT.md"), os.path.join(arch, "REPORT 2.md"))
        os.rename(os.path.join(arch, "REPORT.md"), os.path.join(arch, "REPORT 3.md"))
        out = hyg()
        ok("duplicate name: " + rel + "/ledger 2.json" in out and "MISSING" in out,
           "hygiene scans archive/ for duplicates whose plain name is missing")
        ok("tracked file missing: " + rel + "/verdict.json" in out and "conflicted copy" in out
           and "tracked file missing: " + rel + "/ledger.json" not in out,
           "a tracked file that vanished under another name is reported, once")
        ok(os.path.exists(os.path.join(arch, "ledger 2.json")), "without --restore nothing moves")
        out = hyg("--restore")
        ok(os.path.exists(os.path.join(arch, "ledger.json"))
           and not os.path.exists(os.path.join(arch, "ledger 2.json")) and "restored:" in out,
           "--restore moves back the one unambiguous duplicate")
        ok(os.path.exists(os.path.join(arch, "REPORT 2.md")) and os.path.exists(os.path.join(arch, "REPORT 3.md"))
           and not os.path.exists(os.path.join(arch, "REPORT.md")),
           "two duplicates of one name are left for a human")
        ok(os.path.exists(os.path.join(arch, "verdict (conflicted copy).json"))
           and not os.path.exists(os.path.join(arch, "verdict.json")),
           "--restore never guesses at a differently named twin")
        open(os.path.join(loop, ".phase"), "w").write("round-1-review\n")

        # ---------- read_guard ----------
        open(os.path.join(loop, ".phase"), "w").write("round-1-review\n")
        def bash_payload(cmd):
            return {"tool_name": "Bash", "tool_input": {"command": cmd}}
        heredoc = ("cat > .review-loop/briefs/closeout-changes.json <<'EOF'\n"
                   "{\"verify_cmd\": \"xcodebuild test -scheme App -only-testing:AppTests\"}\n"
                   "EOF")
        r = hook("read_guard.sh", [".review-loop"], bash_payload(heredoc), td)
        ok(r.returncode == 0, "heredoc containing an xcodebuild test string is ALLOWED")
        quoted = "python3 -c 'print(\"xcodebuild test -scheme App\")'"
        r = hook("read_guard.sh", [".review-loop"], bash_payload(quoted), td)
        ok(r.returncode == 0, "single-quoted string containing xcodebuild test is ALLOWED")
        r = hook("read_guard.sh", [".review-loop"],
                 bash_payload("xcodebuild test -scheme App -destination x"), td)
        ok(r.returncode != 0 and "full test output" in r.stderr,
           "a real unfiltered xcodebuild test is still DENIED")
        r = hook("read_guard.sh", [".review-loop"],
                 bash_payload("cd app && xcodebuild test -scheme App 2>&1 | grep -E 'error:|passed'"), td)
        ok(r.returncode == 0, "filtered xcodebuild test after && is allowed")
        r = hook("read_guard.sh", [".review-loop"],
                 bash_payload("cd app; swift test"), td)
        ok(r.returncode != 0, "unfiltered swift test after ; is denied")

        # ---------- commit_guard ----------
        def cg(cmd):
            return hook("commit_guard.sh", [".review-loop"], bash_payload(cmd), td)
        open(os.path.join(loop, ".phase"), "w").write("done\n")
        ok(cg("git add -A && git commit -m x").returncode == 0,
           "git add -A passes when .phase is done (no loop live)")
        open(os.path.join(loop, ".phase"), "w").write("round-1-implementing\n")
        r = cg("git add -A && git commit -m x")
        ok(r.returncode != 0 and "loop is live" in r.stderr,
           "git add -A blocked during a round, message says live")
        open(os.path.join(loop, ".phase"), "w").write("awaiting-human\n")
        ok(cg("git add .").returncode != 0, "git add . blocked at awaiting-human")
        ok(cg("git add src/a.swift && git commit -m x").returncode == 0,
           "explicit-path add always passes")

        # ---------- session_guard ----------
        # dispatch_stamp created briefs/.session-ok above (tiny transcript
        # passes the gate and records the go-ahead); start from none.
        os.remove(os.path.join(loop, "briefs", ".session-ok"))
        prompt = {"prompt": "run the review-loop now", "transcript_path": tp}
        r = hook("session_guard.sh", ["2", ".review-loop"], prompt, td)
        ok(r.returncode == 0 and "loop session check" in r.stdout,
           "session_guard reports size when no .session-ok exists")
        open(os.path.join(loop, "briefs", ".session-ok"), "w").close()
        r = hook("session_guard.sh", ["2", ".review-loop"], prompt, td)
        ok(r.returncode == 0 and r.stdout.strip() == "",
           "session_guard stands down once briefs/.session-ok exists")

        print(f"\nALL {PASS} CHECKS PASSED")
    finally:
        shutil.rmtree(td, ignore_errors=True)

if __name__ == "__main__":
    main()
