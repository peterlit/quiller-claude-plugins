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
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

PASS = 0
def ok(cond, label):
    global PASS
    if not cond:
        print(f"FAIL: {label}", file=sys.stderr)
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
        # :waiting: is never stamped or counted.
        open(os.path.join(loop, ".phase"), "w").write("round-2-review:waiting:panel\n")
        r = hook("dispatch_stamp.sh", [".review-loop", "2"], agent_payload, td)
        ok(phase(loop) == "round-2-review:waiting:panel" and not os.path.exists(cnt),
           ":waiting: marker is left alone by the stamp")

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
