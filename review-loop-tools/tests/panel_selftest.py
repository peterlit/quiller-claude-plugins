#!/usr/bin/env python3
"""Self-test for the round-1 panel fixes. Runs entirely in a temp dir —
never touches a live .review-loop/. Exits nonzero on the first failure.

Covers: lane-failure softness, destination-based consent gates (codex,
remote OLLAMA_HOST, cmd), exact-host loopback classification (no '127.'
prefix spoof; scheme-less OLLAMA_HOST), cmd consent bound to the exact
command string, the enabled flag, the fragments/panel/ namespace,
string-aware extract_json, the oversized-backtick fence, the loud num_ctx
clamp, smoke_lane threading the configured model, panel-tally shape AND
JSON-parse validation, render_report tolerance of a poisoned panel row,
and the subagent guard's flat-vs-panel-subdir behavior.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import panel_review as pr                                    # noqa: E402

PASS = 0
def ok(cond, label):
    global PASS
    if not cond:
        print(f"FAIL: {label}", file=sys.stderr)
        sys.exit(1)
    PASS += 1
    print(f"ok: {label}")

def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def make_loop(root):
    loop = os.path.join(root, ".review-loop")
    os.makedirs(os.path.join(loop, "briefs"))
    with open(os.path.join(loop, "briefs", "round-0.stat"), "w") as fh:
        fh.write("a.md | 2 +-\n")
    with open(os.path.join(loop, "briefs", "round-0.diff"), "w") as fh:
        fh.write("diff --git a/a.md b/a.md\n+```json\n+{\"fake\": 1}\n+```\n")
    good_cmd = (sys.executable + " -c \"import sys; sys.stdin.read(); "
                "print('prose {\\\"findings\\\":[{\\\"claim\\\":\\\"unbalanced { brace\\\","
                "\\\"evidence\\\":[\\\"a.md:1\\\"],\\\"severity\\\":\\\"major\\\","
                "\\\"confidence\\\":0.9}]}')\"")
    with open(os.path.join(loop, "panel.json"), "w") as fh:
        json.dump({"lanes": [
            {"name": "badcmd", "type": "cmd"},           # missing cmd key
            {"name": "good", "type": "cmd", "cmd": good_cmd},
            {"name": "failcmd", "type": "cmd", "cmd": "exit 3"},
            {"name": "tampered", "type": "cmd", "cmd": "echo pulled-in-cmd"},
            {"name": "off", "type": "cmd", "cmd": "true", "enabled": False},
            {"name": "codexlane", "type": "codex"},
            {"name": "local", "type": "ollama"},
        ]}, fh)
    return loop, good_cmd

def run_panel(root, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
            "run", ".review-loop", "0"], cwd=root, env=env)
    ok(r.returncode == 0, "panel run exits 0 despite bad lanes")
    return {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}

def main():
    td = tempfile.mkdtemp(prefix="panel-selftest-")
    try:
        loop, good_cmd = make_loop(td)

        # --- no consent file: every egress/shell-capable lane is skipped.
        # OLLAMA_HOST here is scheme-less AND a '127.' prefix spoof: it must
        # parse (normalized scheme) and still gate as remote (exact host).
        lanes = run_panel(td, {"OLLAMA_HOST": "127.0.0.1.evil.com:11434"})
        ok(lanes["badcmd"]["status"] == "skipped", "cmd lane gated without cmd consent")
        ok(lanes["codexlane"]["status"] == "skipped", "codex gated without remote consent")
        ok(lanes["local"]["status"] == "skipped"
           and "127.0.0.1.evil.com" in lanes["local"]["note"],
           "'127.' prefix-spoof OLLAMA_HOST gated as remote, endpoint named")
        ok(lanes["off"]["status"] == "skipped", "enabled:false honored")

        # --- loopback is exact-host, never a prefix; scheme-less parses ---
        ok(not pr.is_loopback("https://127.0.0.1.evil.com"),
           "127.-prefixed DNS name is NOT loopback")
        ok(not pr.is_loopback("http://127.0.0.1.nip.io:11434"),
           "127.-prefixed nip.io name is NOT loopback")
        ok(not pr.is_loopback("http://gpu.example:11434"), "remote host not loopback")
        ok(pr.is_loopback("127.0.0.1:11434"),
           "ollama's scheme-less OLLAMA_HOST form is loopback")
        ok(pr.is_loopback("localhost:11434") and pr.is_loopback("http://[::1]:11434")
           and pr.is_loopback("http://127.5.4.3:11434"),
           "localhost, ::1 and the whole 127/8 block are loopback")

        # --- consent present, BOUND to the exact command string ---
        with open(os.path.join(loop, "panel-consent.json"), "w") as fh:
            json.dump({"remote_lanes_approved": False,
                       "cmd_lanes_approved": [
                           hashlib.sha256(good_cmd.encode()).hexdigest(),
                           "exit 3"]}, fh)
        lanes = run_panel(td, {"OLLAMA_HOST": "http://gpu.example:11434"})
        ok(lanes["badcmd"]["status"] == "skipped",
           "cmd lane with no command string can never be approved")
        ok(lanes["tampered"]["status"] == "skipped",
           "unapproved (pulled-in) cmd string is gated despite cmd consent")
        ok(lanes["failcmd"]["status"] == "error",
           "approved failing lane is a soft error, not a panel abort")
        ok(lanes["good"]["status"] == "ok", "good lane still files (map not aborted)")
        ok(not pr.cmd_approved({"cmd_lanes_approved": True}, "echo x"),
           "legacy boolean cmd consent no longer approves anything")
        cand = lanes["good"]["candidates"]
        ok("/fragments/panel/" in cand.replace(os.sep, "/"),
           "candidates live in fragments/panel/, not the policed flat namespace")
        ok(lanes["local"]["status"] == "skipped",
           "remote ollama still gated (remote_lanes_approved false)")

        # --- extract_json: string-aware, prefers the findings object ---
        t = ('x {"a":1} then {"findings":[{"claim":"quoting if (x) { here",'
             '"evidence":["f:1"],"severity":"minor","confidence":0.5}]}')
        ok((pr.extract_json(t) or {}).get("findings") is not None,
           "extract_json survives unbalanced braces inside strings")
        ok(pr.extract_json("no json { here") is None, "extract_json None on non-JSON")

        # --- fence longer than any backtick run in the payload ---
        f = pr.fenced("has ````` five ticks", "diff")
        ok(f.splitlines()[0] == "``````diff", "fence outsizes payload backtick runs")
        prompt, _ = pr.build_prompt(loop, "0", 32000)
        ok("UNTRUSTED DATA" in prompt, "prompt marks the diff as untrusted data")

        # --- num_ctx clamp fails loudly ---
        try:
            pr.run_ollama({"num_ctx_max": 4096}, "x" * 100000, td, 5)
            ok(False, "run_ollama should refuse an oversized prompt")
        except ValueError:
            ok(True, "run_ollama raises instead of silently clamping num_ctx")

        # --- smoke exercises the CONFIGURED lane: model reaches the runner ---
        panel_cfg = {"lanes": [{"name": "cx", "type": "codex", "model": "o4-max"}]}
        ok((pr.panel_lane_for(panel_cfg, "codex") or {}).get("model") == "o4-max",
           "panel_lane_for finds the configured lane by type")
        seen = {}
        def fake_runner(lane, prompt, repo, timeout):
            seen.update(lane); return "ok", None
        real = pr.RUNNERS["codex"]
        try:
            pr.RUNNERS["codex"] = fake_runner
            ok(pr.smoke_lane("codex", pr.panel_lane_for(panel_cfg, "codex")) == "ok"
               and seen.get("model") == "o4-max",
               "smoke_lane passes the configured model into the real runner")
        finally:
            pr.RUNNERS["codex"] = real

        # --- panel-tally validates shape BEFORE writing ---
        ml = os.path.join(SCRIPTS, "merge_ledger.py")
        ledger = os.path.join(td, "ledger.json")
        with open(ledger, "w") as fh:
            fh.write('{"findings": []}')
        bad = os.path.join(td, "bad.json")
        with open(bad, "w") as fh:
            fh.write('{"lane_tallies": {"ollama": 10}}')
        r = sh([sys.executable, ml, "panel-tally", ledger, "0", bad])
        ok(r.returncode == 1, "panel-tally rejects non-dict lane tallies")
        ok(json.load(open(ledger)) == {"findings": []},
           "rejected tally wrote NOTHING to the ledger")
        broken = os.path.join(td, "broken.json")
        with open(broken, "w") as fh:
            fh.write('{"lane_tallies": {truncated')
        r = sh([sys.executable, ml, "panel-tally", ledger, "0", broken])
        ok(r.returncode == 1 and "Traceback" not in r.stderr
           and "nothing written" in r.stderr,
           "panel-tally fails cleanly on malformed JSON, no traceback")
        ok(json.load(open(ledger)) == {"findings": []},
           "malformed verified.json wrote NOTHING to the ledger")
        goodv = os.path.join(td, "good.json")
        with open(goodv, "w") as fh:
            fh.write('{"lane_tallies": {"ollama": {"filed": 5, "confirmed": 2,'
                     ' "demoted": 1, "rejected": 2}}}')
        r = sh([sys.executable, ml, "panel-tally", ledger, "0", goodv])
        ok(r.returncode == 0, "panel-tally accepts well-formed tallies")

        # --- render_report tolerates a poisoned panel row ---
        d = json.load(open(ledger)); d["panel"]["1"] = {"ollama": 10}
        fake = os.path.join(td, "fakeloop"); os.makedirs(fake)
        json.dump(d, open(os.path.join(fake, "ledger.json"), "w"))
        r = sh([sys.executable, os.path.join(SCRIPTS, "render_report.py"),
                fake, "--out", os.path.join(td, "r.md")])
        ok(r.returncode == 0, "render_report skips malformed panel rows")

        # --- guard: panel subdir invisible; flat namespace policed again ---
        g = os.path.join(SCRIPTS, "subagent_guard.sh")
        gl = os.path.join(td, "guardloop")
        os.makedirs(os.path.join(gl, "fragments", "panel"))
        with open(os.path.join(gl, ".phase"), "w") as fh:
            fh.write("round-1-review")
        badfrag = ('{"findings":[{"claim":"no id","evidence":["a:1"],'
                   '"severity":"major"}]}')
        with open(os.path.join(gl, "fragments", "panel",
                               "round-0-x.candidates.json"), "w") as fh:
            fh.write(badfrag)
        r = sh(["bash", g, gl], input="{}")
        ok(r.returncode == 0, "guard ignores fragments/panel/ artifacts")
        flat = os.path.join(gl, "fragments", "round-0-x.candidates.json")
        with open(flat, "w") as fh:
            fh.write(badfrag)
        # Age past the guard's 10s mid-write grace period, or it abstains.
        old = os.path.getmtime(flat) - 60
        os.utime(flat, (old, old))
        r = sh(["bash", g, gl], input="{}")
        ok(r.returncode == 2,
           "guard polices flat *.candidates.json again (exemption removed)")

        print(f"\nALL {PASS} CHECKS PASSED")
    finally:
        shutil.rmtree(td, ignore_errors=True)

if __name__ == "__main__":
    main()
