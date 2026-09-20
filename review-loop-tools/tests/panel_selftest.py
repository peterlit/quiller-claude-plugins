#!/usr/bin/env python3
"""Self-test for the round-1 panel fixes. Runs entirely in a temp dir —
never touches a live .review-loop/. Exits nonzero on the first failure.

Covers: lane-failure softness, destination-based consent gates (codex,
remote OLLAMA_HOST, cmd), exact-host loopback classification (no '127.'
prefix spoof; scheme-less OLLAMA_HOST), cmd consent bound to the exact
command string, the enabled flag, the fragments/panel/ namespace,
string-aware extract_json, the oversized-backtick fence, the loud num_ctx
clamp, smoke_lane threading the configured model, consent embedded in the
git-tracked panel.json being IGNORED, bare `probe --smoke` reading
.review-loop/panel.json from the cwd, probe surviving a MALFORMED
panel.json with an "unreadable" row instead of a traceback, panel-tally
shape AND JSON-parse validation, render_report tolerance of a poisoned
panel row, the subagent guard's flat-vs-panel-subdir behavior, and the
three CONTROLS.md copies staying byte-identical (HANDOFF.md cp-sync).

Round-1 panel-hardening additions: loopback ollama traffic bypasses
HTTP(S)_PROXY
(open_url); run() survives a malformed panel.json/consent file
(fail-closed, no traceback); cmd-lane timeout kills the whole process
GROUP; codex/gemini run jailed in an empty scratch cwd; codex never reads
a stale .last-message.txt; lane names from panel.json are sanitized before
path splice; sanitize() normalizes severity case and skips (not crashes
on) unhashable severities; the .stat read tolerates invalid UTF-8;
ollama_need is byte-aware and run_ollama re-checks prompt_eval_count;
normalize_url strips trailing slashes; render_report tolerates a
bare-string 'sources'. (Severity handling later tightened: unhashable —
like every other out-of-vocabulary severity — now clamps to minor rather
than skipping the row.)

Round-2 additions: the codex lane end to end through a RELATIVE loop dir
(a stub `codex` on PATH — the jail cwd must not swallow the
--output-last-message file); run()/probe() survive a panel.json that is
valid JSON but not an object; run_ollama
refuses a prompt over the model's trained context (/api/show) before
paying for generate, gives clamp-proof advice, and preserves the response
on the truncation raise; punctuation-differing lane names no longer
collide on one output base; codex/gemini env is scrubbed (no CLAUDE_*,
pwd vars point at the jail).

Round-3 additions: a non-dict lane ELEMENT ({"lanes": ["codex"]}) skips
with a note instead of crashing the map (and safe()'s handler no longer
assumes lane shape);
run_ollama warns on stderr when /api/show yields no trained context (the
clamp guard must never go inert silently).

Round-4 additions: consent is MACHINE-LOCAL (XDG_CONFIG_HOME — this
selftest points it at its own tempdir, a SIBLING of the fixture tree,
keeping every check hermetic): an
in-repo panel-consent.json authorizes NOTHING whether tracked, untracked,
or outside any checkout, and earns the migration hint naming the real
path; the bundled-archive attack (export shipping panel.json cmd lane +
matching consent) fails closed end to end both UNDER an unrelated git
checkout and with no .git anywhere; consent_path is stable across
relative/absolute spellings of the loop dir; the consent-path verb prints
the machine-local file.

Post-closeout additions: an ABSOLUTE XDG_CONFIG_HOME that resolves INSIDE
the reviewed repo (repo-shipped env: .envrc, devcontainer, a Makefile
export) is rejected — the bundled-archive attack armed with an in-checkout
.config consent store fails closed end to end, a symlink alias of an
in-repo base is caught (realpath both sides), and an out-of-repo absolute
base is still honored. The ~/.config FALLBACK gets the same containment
check (HOME arrives by the same repo-shipped-env vector): a HOME inside
the checkout leaves no trustworthy base — consent_path returns None,
load_consent fails closed, the HOME-armed bundle attack fails end to end,
and the consent-path verb refuses with a fix hint. remote_lanes_approved
grants only as JSON true — a truthy non-boolean ('yes') gates lanes
closed and warns. Missing/blank severity clamps to minor (see above).
"""
import contextlib, hashlib, io, json, os, re, shlex, shutil, subprocess, sys
import tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import panel_review as pr                                    # noqa: E402
import render_report as rr                                   # noqa: E402

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
            # A merge-mangled panel can hold a bare string element — it must
            # skip with a note, not AttributeError the whole lane map.
            "straylane",
        ],
            # Consent fields written INTO the git-tracked panel.json — the
            # withdrawn design. They must authorize NOTHING: a committed
            # consent would arm egress and shell on every clone. The cmd
            # list even holds the exact approved strings/digests, so any
            # panel.json fallback in load_consent flips the checks below.
            "consent": {"remote_lanes_approved": True,
                        "cmd_lanes_approved": True},
            "remote_lanes_approved": True,
            "cmd_lanes_approved": [
                hashlib.sha256(good_cmd.encode()).hexdigest(),
                "exit 3", "echo pulled-in-cmd"]}, fh)
    return loop, good_cmd

def run_panel(root, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    # --force: the fixture reruns the same round; without it every lane
    # after the first run would report `cached` (the 0.14 rerun guard).
    r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
            "run", ".review-loop", "0", "--force"], cwd=root, env=env)
    ok(r.returncode == 0, "panel run exits 0 despite bad lanes")
    return {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}

def write_consent(loop, data):
    """Write MACHINE-LOCAL consent for a tempdir loop — the only way the
    selftest may grant consent (in-repo files must authorize nothing)."""
    p = pr.consent_path(loop)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump(data, fh)
    return p

def main():
    td = tempfile.mkdtemp(prefix="panel-selftest-")
    # Consent is machine-local under XDG_CONFIG_HOME — point it at its OWN
    # tempdir so every consent the selftest writes or refuses is hermetic
    # (never the developer's real ~/.config store). A SIBLING of td, never
    # inside it: consent_path rejects an XDG base under the reviewed repo
    # root (dirname of the loop dir), and td IS that root for the main
    # fixture loop — an in-td base would silently fall back to ~/.config.
    xdg_td = tempfile.mkdtemp(prefix="panel-selftest-xdg-")
    os.environ["XDG_CONFIG_HOME"] = xdg_td
    try:
        loop, good_cmd = make_loop(td)

        # --- no panel-consent.json, but panel.json ITSELF carries consent
        # fields (including the exact approved cmd digests): every
        # egress/shell-capable lane must still be skipped — tracked consent
        # never authorizes. OLLAMA_HOST here is scheme-less AND a '127.'
        # prefix spoof: it must parse (normalized scheme) and still gate as
        # remote (exact host).
        ok(pr.load_consent(loop) == {},
           "load_consent never reads consent embedded in tracked panel.json")
        lanes = run_panel(td, {"OLLAMA_HOST": "127.0.0.1.evil.com:11434"})
        ok(lanes["badcmd"]["status"] == "skipped", "cmd lane gated without cmd consent")
        ok(lanes["codexlane"]["status"] == "skipped", "codex gated without remote consent")
        ok(lanes["good"]["status"] == "skipped"
           and lanes["tampered"]["status"] == "skipped",
           "consent carried in git-tracked panel.json authorizes NOTHING")
        ok(lanes["local"]["status"] == "skipped"
           and "127.0.0.1.evil.com" in lanes["local"]["note"],
           "'127.' prefix-spoof OLLAMA_HOST gated as remote, endpoint named")
        ok(lanes["off"]["status"] == "skipped", "enabled:false honored")
        ok(lanes["straylane"]["status"] == "skipped"
           and "not an object" in lanes["straylane"]["note"],
           "non-dict lane element skips with a note, map survives")

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

        # --- consent present (machine-local), BOUND to the exact command
        # string ---
        write_consent(loop, {"remote_lanes_approved": False,
                             "cmd_lanes_approved": [
                                 hashlib.sha256(good_cmd.encode()).hexdigest(),
                                 "exit 3"]})
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

        # --- bare `probe --smoke` (the skill's documented invocation, no
        # panel.json path) reads .review-loop/panel.json from the cwd and
        # smokes the CONFIGURED model, not the CLI default ---
        proot = os.path.join(td, "proberoot")
        os.makedirs(os.path.join(proot, ".review-loop"))
        with open(os.path.join(proot, ".review-loop", "panel.json"), "w") as fh:
            json.dump({"lanes": [{"name": "codex", "type": "codex",
                                  "model": "o4-max"}]}, fh)
        seen.clear()
        real_run, real_which = pr.subprocess.run, pr.shutil.which
        real_open = pr.open_url
        cwd, buf = os.getcwd(), io.StringIO()

        def _no_daemon(*a, **kw):
            raise OSError("selftest: no ollama daemon")
        try:
            pr.RUNNERS["codex"] = fake_runner
            pr.shutil.which = lambda n: "/fake/codex" if n == "codex" else None
            pr.subprocess.run = lambda *a, **kw: type(
                "R", (), {"returncode": 0, "stdout": "logged in", "stderr": ""})()
            pr.open_url = _no_daemon
            os.chdir(proot)
            with contextlib.redirect_stdout(buf):
                pr.probe(["--smoke"])
        finally:
            os.chdir(cwd)
            pr.RUNNERS["codex"] = real
            pr.subprocess.run, pr.shutil.which = real_run, real_which
            pr.open_url = real_open
        probe_out = json.loads(buf.getvalue())
        ok(seen.get("model") == "o4-max"
           and probe_out["codex"]["smoke"] == "ok"
           and probe_out["codex"].get("configured") is True,
           "bare probe --smoke picks up .review-loop/panel.json from cwd "
           "and threads the configured model into the smoke")

        # --- probe survives a malformed panel.json (no traceback) ---
        broot = os.path.join(td, "probe-bad")
        os.makedirs(os.path.join(broot, ".review-loop"))
        with open(os.path.join(broot, ".review-loop", "panel.json"), "w") as fh:
            fh.write('{"lanes": [ broken')
        cwd, buf = os.getcwd(), io.StringIO()
        real_which = pr.shutil.which
        real_open = pr.open_url
        try:
            pr.shutil.which = lambda n: None
            pr.open_url = _no_daemon
            os.chdir(broot)
            with contextlib.redirect_stdout(buf):
                pr.probe([])
        finally:
            os.chdir(cwd)
            pr.shutil.which, pr.open_url = real_which, real_open
        probe_out = json.loads(buf.getvalue())
        ok(probe_out.get("panel", "").startswith("unreadable"),
           "probe reports malformed panel.json instead of crashing")

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

        # ================= round-1 panel hardening =======================

        # --- normalize_url strips trailing slashes (no //api/generate) ---
        ok(pr.normalize_url("http://h:11434/") == "http://h:11434"
           and pr.normalize_url("h:11434/") == "http://h:11434",
           "normalize_url strips trailing slash, scheme-less form included")

        # --- sanitize: severity normalized; unhashable clamps, not crashes ---
        s = pr.sanitize({"findings": [
            {"claim": "caps", "evidence": ["a:1"], "severity": "Major"},
            {"claim": "bad", "evidence": ["a:1"], "severity": ["major"]},
            {"claim": "low", "evidence": ["a:1"], "severity": "minor"}]}, "l")
        ok(s["filed"] == 3
           and sorted(f["severity"] for f in s["findings"])
           == ["major", "minor", "minor"],
           "sanitize normalizes 'Major', clamps (not crashes on) unhashable "
           "severity to minor")

        # --- lane name from panel.json cannot traverse out of panel/ ---
        sn = pr.safe_lane_name("../../../tmp/x")
        ok("/" not in sn and "." not in sn and pr.safe_lane_name(None) == "lane",
           "safe_lane_name strips separators and dots")
        res = pr.run_lane({"name": "../../oops", "type": "cmd", "cmd": "echo hi"},
                          loop, "0", td, {"cmd_lanes_approved": ["echo hi"]})
        raws = os.listdir(os.path.join(loop, "fragments", "panel"))
        ok(res["status"] == "error"          # echo output is not candidates JSON
           and any("oops" in n and ".." not in n for n in raws),
           "traversal lane name is sanitized into fragments/panel/, not outside")

        # --- an IN-REPO consent file authorizes NOTHING, tracked or not:
        # git tracked-ness is no trust boundary (a bundle unpacked inside
        # any checkout reads as 'untracked'), so the file is ignored with a
        # migration hint naming the machine-local path ---
        groot = os.path.join(td, "gitroot")
        gloop = os.path.join(groot, ".review-loop")
        os.makedirs(gloop)
        with open(os.path.join(gloop, "panel-consent.json"), "w") as fh:
            json.dump({"remote_lanes_approved": True,
                       "cmd_lanes_approved": ["echo pwned"]}, fh)
        sh(["git", "init", "-q", groot])
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ok(pr.load_consent(gloop) == {},
               "UNTRACKED in-repo consent inside a checkout is IGNORED")
        ok("IGNORED" in buf.getvalue()
           and pr.consent_path(gloop) in buf.getvalue(),
           "in-repo consent hint names the machine-local path")
        sh(["git", "-C", groot, "add", "-f", ".review-loop/panel-consent.json"])
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ok(pr.load_consent(gloop) == {},
               "force-added (git-TRACKED) panel-consent.json is ignored too")
        # ...while MACHINE-LOCAL consent for the same loop IS honored, and
        # is keyed by the resolved loop path (relative spelling = same file).
        write_consent(gloop, {"remote_lanes_approved": True})
        with contextlib.redirect_stderr(io.StringIO()):
            ok(pr.load_consent(gloop).get("remote_lanes_approved") is True,
               "machine-local consent is honored (in-repo file still inert)")
        cwd = os.getcwd()
        try:
            os.chdir(groot)
            ok(pr.consent_path(".review-loop") == pr.consent_path(gloop),
               "consent_path stable across relative/absolute loop spellings")
        finally:
            os.chdir(cwd)
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "consent-path", gloop])
        ok(r.stdout.strip() == pr.consent_path(gloop),
           "consent-path verb prints the machine-local consent file")
        ok(pr.consent_path(gloop) != pr.consent_path(loop),
           "different loop dirs (same basename) get DIFFERENT consent files "
           "— consent given to one repo never bleeds into another")

        # --- non-object consent (valid JSON, wrong shape) fails CLOSED ---
        with open(pr.consent_path(loop), "w") as fh:
            fh.write('["remote_lanes_approved"]')
        ok(pr.load_consent(loop) == {},
           "valid-JSON non-object consent file = NO consent")

        # --- malformed consent fails CLOSED; run() survives it ---
        with open(pr.consent_path(loop), "w") as fh:
            fh.write("{broken")
        lanes = run_panel(td, {"OLLAMA_HOST": "http://gpu.example:11434"})
        ok(lanes["good"]["status"] == "skipped"
           and lanes["codexlane"]["status"] == "skipped",
           "unreadable machine-local consent = NO consent (fail closed, no crash)")

        # --- malformed panel.json at RUN time: status line, exit 0 ---
        mroot = os.path.join(td, "badpanel")
        os.makedirs(os.path.join(mroot, ".review-loop", "briefs"))
        with open(os.path.join(mroot, ".review-loop", "panel.json"), "w") as fh:
            fh.write('{"lanes": [ broken')
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"], cwd=mroot)
        ok(r.returncode == 0 and "Traceback" not in r.stderr
           and json.loads(r.stdout).get("status") == "panel-unreadable",
           "run() reports malformed panel.json instead of a traceback")

        # --- open_url: loopback bypasses proxies; remote uses urlopen ---
        class Sentinel(Exception):
            pass
        def _sentinel(*a, **kw):
            raise Sentinel("proxy-honoring urlopen used")
        real_urlopen = pr.urllib.request.urlopen
        old_proxy = os.environ.get("HTTP_PROXY")
        os.environ["HTTP_PROXY"] = "http://203.0.113.1:9"    # TEST-NET-3
        try:
            pr.urllib.request.urlopen = _sentinel
            try:
                pr.open_url("http://127.0.0.1:1/api/tags", 1)
                ok(False, "open_url loopback: connection unexpectedly succeeded")
            except Sentinel:
                ok(False, "loopback open_url must NOT use proxy-honoring urlopen")
            except OSError:
                ok(True, "loopback open_url bypasses proxies (direct, not urlopen)")
            try:
                pr.open_url("http://gpu.example:1/x", 1)
                ok(False, "remote open_url should reach the urlopen stub")
            except Sentinel:
                ok(True, "non-loopback open_url still uses urlopen (consent-gated)")
        finally:
            pr.urllib.request.urlopen = real_urlopen
            if old_proxy is None:
                os.environ.pop("HTTP_PROXY", None)
            else:
                os.environ["HTTP_PROXY"] = old_proxy

        # --- cmd-lane timeout kills the whole process GROUP ---
        pidfile = os.path.join(td, "childpid")
        cmd = f"sleep 30 & echo $! > {shlex.quote(pidfile)}; wait"
        try:
            pr.run_cmd({"cmd": cmd}, "", td, 1)
            ok(False, "run_cmd should have timed out")
        except subprocess.TimeoutExpired:
            child = int(open(pidfile).read().strip())
            dead = False
            for _ in range(20):
                try:
                    os.kill(child, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    dead = True
                    break
            ok(dead, "cmd-lane timeout kills the shell's children (process group)")

        # --- codex/gemini jailed in an empty scratch cwd; no stale reads ---
        cap = {}
        def fake_sub_run(cmd, **kw):
            cap["cwd"] = kw.get("cwd")
            cap["ls"] = os.listdir(kw.get("cwd"))
            cap["env"] = kw.get("env")
            return subprocess.CompletedProcess(cmd, 0, "fresh-stdout", "")
        stale = os.path.join(td, "lane.last-message.txt")
        with open(stale, "w") as fh:
            fh.write("STALE output from a prior interrupted run")
        real_sub = pr.subprocess.run
        try:
            pr.subprocess.run = fake_sub_run
            raw, _ = pr.run_codex({"_out_base": os.path.join(td, "lane")},
                                  "p", td, 5)
            ok(cap["cwd"] != td and cap["ls"] == []
               and "panel-lane-" in cap["cwd"],
               "codex runs jailed in an empty scratch cwd, not the repo")
            ok(raw == "fresh-stdout" and not os.path.exists(stale),
               "stale codex .last-message.txt is deleted, never read as current")
            cap.clear()
            raw, _ = pr.run_gemini({}, "p", td, 5)
            ok(cap["cwd"] != td and cap["ls"] == []
               and cap["env"].get("GEMINI_CLI_TRUST_WORKSPACE") == "true",
               "gemini's trusted workspace is the empty jail, not the repo")
        finally:
            pr.subprocess.run = real_sub

        # --- ollama sizing: byte-aware estimate + server-side recheck ---
        ok(pr.ollama_need("汉" * 1000) > pr.ollama_need("x" * 1000),
           "ollama_need sizes byte-dense Unicode above equal-length ASCII")
        try:
            # char-based estimate (~16.6k) would have slipped past 17000;
            # the byte-aware one (~41.6k) must refuse before any network.
            pr.run_ollama({"num_ctx_max": 17000}, "汉" * 40000, td, 5)
            ok(False, "Unicode-dense prompt should exceed num_ctx_max loudly")
        except ValueError:
            ok(True, "byte-aware estimate trips the loud pre-check")
        class FakeResp:
            def __init__(self, payload): self._p = payload
            def read(self): return json.dumps(self._p).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        real_open_url = pr.open_url
        try:
            pr.open_url = lambda req, t: FakeResp(
                {"response": "ok", "prompt_eval_count": 999999})
            try:
                pr.run_ollama({"num_ctx_max": 65536}, "x" * 1000, td, 5)
                ok(False, "run_ollama should refuse a context-filling response")
            except ValueError:
                ok(True, "prompt_eval_count at num_ctx fails loudly (real truncation)")
            pr.open_url = lambda req, t: FakeResp(
                {"response": "fine", "prompt_eval_count": 300})
            raw, _ = pr.run_ollama({"num_ctx_max": 65536}, "x" * 1000, td, 5)
            ok(raw == "fine", "normal prompt_eval_count passes through")
        finally:
            pr.open_url = real_open_url

        # --- .stat with invalid UTF-8 must not abort prompt-building ---
        with open(os.path.join(loop, "briefs", "round-7.stat"), "wb") as fh:
            fh.write(b"weird-\xff-name.md | 2 +-\n")
        shutil.copy(os.path.join(loop, "briefs", "round-0.diff"),
                    os.path.join(loop, "briefs", "round-7.diff"))
        p7, _ = pr.build_prompt(loop, "7", 1000)
        ok("weird-" in p7, "invalid UTF-8 in .stat tolerated (errors=replace)")

        # --- render_report: bare-string 'sources' renders as one tag ---
        line = rr.finding_line({"id": "x", "severity": "major",
                                "current_status": "open",
                                "source": "panel:ollama",
                                "sources": "panel:ollama"})[0]
        ok("via panel:ollama" in line and "p+a+n" not in line,
           "bare-string 'sources' renders as one lane tag, not characters")

        # ================= round-2 panel hardening =======================

        # --- codex lane END TO END through a RELATIVE loop dir: codex
        # resolves --output-last-message against its jail cwd, so a
        # relative _out_base vanishes with the jail (round-1 blocker) ---
        croot = os.path.join(td, "codexroot")
        cloop = os.path.join(croot, ".review-loop")
        os.makedirs(os.path.join(cloop, "briefs"))
        with open(os.path.join(cloop, "briefs", "round-0.stat"), "w") as fh:
            fh.write("a.md | 1 +\n")
        with open(os.path.join(cloop, "briefs", "round-0.diff"), "w") as fh:
            fh.write("diff --git a/a.md b/a.md\n+x\n")
        with open(os.path.join(cloop, "panel.json"), "w") as fh:
            json.dump({"lanes": [{"name": "codex", "type": "codex"}]}, fh)
        write_consent(cloop, {"remote_lanes_approved": True})
        bindir = os.path.join(td, "bin")
        os.makedirs(bindir, exist_ok=True)
        stub = os.path.join(bindir, "codex")
        with open(stub, "w") as fh:
            fh.write(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "# Like real codex: the output path resolves against OUR cwd.\n"
                "out = sys.argv[sys.argv.index('--output-last-message') + 1]\n"
                "sys.stdin.read()\n"
                "with open(out, 'w') as fh:\n"
                "    fh.write('{\"findings\":[{\"claim\":\"stub\",'\n"
                "             '\"evidence\":[\"a.md:1\"],\"severity\":\"minor\",'\n"
                "             '\"confidence\":0.4}]}')\n"
                "print('codex exec event-log noise, not JSON')\n")
        os.chmod(stub, 0o755)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"], cwd=croot, env=env)
        lanes = {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}
        ok(r.returncode == 0 and lanes["codex"]["status"] == "ok"
           and os.path.exists(os.path.join(cloop, "fragments", "panel",
                                           "round-0-codex.candidates.json")),
           "relative loop dir: codex output file survives the jail teardown")

        # --- panel.json that is VALID JSON but not an object ---
        lroot = os.path.join(td, "listpanel")
        os.makedirs(os.path.join(lroot, ".review-loop", "briefs"))
        with open(os.path.join(lroot, ".review-loop", "panel.json"), "w") as fh:
            fh.write('[{"lanes": []}]')
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"], cwd=lroot)
        ok(r.returncode == 0 and "Traceback" not in r.stderr
           and json.loads(r.stdout).get("status") == "panel-unreadable",
           "run() reports non-object panel.json instead of AttributeError")
        ok(pr.panel_lane_for([{"lanes": [1]}], "codex") is None
           and pr.panel_lane_for({"lanes": "oops"}, "codex") is None,
           "panel_lane_for tolerates non-dict panel and non-list lanes")
        nroot = os.path.join(td, "probe-list")
        os.makedirs(os.path.join(nroot, ".review-loop"))
        with open(os.path.join(nroot, ".review-loop", "panel.json"), "w") as fh:
            fh.write('["not", "an", "object"]')
        cwd, buf = os.getcwd(), io.StringIO()
        real_which, real_open = pr.shutil.which, pr.open_url
        try:
            pr.shutil.which = lambda n: None
            pr.open_url = _no_daemon
            os.chdir(nroot)
            with contextlib.redirect_stdout(buf):
                pr.probe([])
        finally:
            os.chdir(cwd)
            pr.shutil.which, pr.open_url = real_which, real_open
        ok(json.loads(buf.getvalue()).get("panel", "").startswith("unreadable"),
           "probe reports non-object panel.json instead of crashing")

        # --- the bundled-archive attack END TO END: an export ships
        # panel.json (cmd lane) + panel-consent.json approving that exact
        # string. Machine-local consent means git is irrelevant: the lane
        # must be SKIPPED and the command never executed, both UNDER an
        # unrelated checkout (git calls the attacker's file 'untracked' —
        # that proves nothing) and with no .git anywhere (ZIP/`git archive`/
        # cp -r strip .git while keeping the consent file). ---
        def make_bundle(root, marker):
            bloop = os.path.join(root, ".review-loop")
            os.makedirs(os.path.join(bloop, "briefs"))
            with open(os.path.join(bloop, "briefs", "round-0.stat"), "w") as fh:
                fh.write("a.md | 1 +\n")
            with open(os.path.join(bloop, "briefs", "round-0.diff"), "w") as fh:
                fh.write("diff --git a/a.md b/a.md\n+x\n")
            evil = "touch " + shlex.quote(marker)
            with open(os.path.join(bloop, "panel.json"), "w") as fh:
                json.dump({"lanes": [
                    {"name": "evil", "type": "cmd", "cmd": evil}]}, fh)
            with open(os.path.join(bloop, "panel-consent.json"), "w") as fh:
                json.dump({"remote_lanes_approved": True,
                           "cmd_lanes_approved": [evil]}, fh)
        vroot = os.path.join(td, "victimrepo")
        os.makedirs(vroot)
        sh(["git", "init", "-q", vroot])
        marker1 = os.path.join(td, "pwned-under-checkout")
        make_bundle(os.path.join(vroot, "downloaded-bundle"), marker1)
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"],
               cwd=os.path.join(vroot, "downloaded-bundle"))
        lanes = {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}
        ok(r.returncode == 0 and lanes["evil"]["status"] == "skipped"
           and not os.path.exists(marker1),
           "bundled consent unpacked UNDER an unrelated checkout fails "
           "closed (cmd never executed)")
        ok("IGNORED" in r.stderr,
           "bundle-under-checkout run prints the in-repo-consent hint")
        marker2 = os.path.join(td, "pwned-no-git")
        make_bundle(os.path.join(td, "loose-bundle"), marker2)
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"],
               cwd=os.path.join(td, "loose-bundle"))
        lanes = {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}
        ok(r.returncode == 0 and lanes["evil"]["status"] == "skipped"
           and not os.path.exists(marker2),
           "bundled consent with no .git anywhere fails closed "
           "(cmd never executed)")

        # --- safe()'s except handler must not assume lane shape: when
        # run_lane raises ON a non-dict lane element, the wrapper whose job
        # is 'one lane never aborts the map' must not be the crash site ---
        real_run_lane = pr.run_lane
        try:
            def _boom(*a, **kw):
                raise RuntimeError("boom")
            pr.run_lane = _boom
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                pr.run([loop, "0"])   # panel.json includes the "straylane" str
            res = json.loads(buf.getvalue())
            ok(all(r["status"] == "error" for r in res["lanes"])
               and any(r["lane"] == "straylane" for r in res["lanes"]),
               "safe() handler reports a raising non-dict lane, map survives")
        finally:
            pr.run_lane = real_run_lane

        # --- ollama: trained-context clamp refused BEFORE generate ---
        calls = []
        def fake_ollama(req, t):
            url = req.full_url if hasattr(req, "full_url") else req
            calls.append(url)
            if url.endswith("/api/show"):
                return FakeResp({"model_info": {"qwen3.context_length": 8192}})
            return FakeResp({"response": "r", "prompt_eval_count": 100})
        real_open_url = pr.open_url
        try:
            pr.open_url = fake_ollama
            try:
                # need ~35k: passes num_ctx_max, exceeds the 8k trained ctx.
                pr.run_ollama({"num_ctx_max": 65536}, "x" * 100000, td, 5)
                ok(False, "run_ollama should refuse a prompt over trained ctx")
            except ValueError as e:
                ok("trained context" in str(e)
                   and not any(u.endswith("/api/generate") for u in calls),
                   "need above /api/show trained context refused BEFORE generate")
            obase = os.path.join(td, "olane")
            pr.open_url = lambda req, t: FakeResp(
                {"model_info": {}, "response": "paid-for",
                 "prompt_eval_count": 999999})
            # model_info without *.context_length -> model_ctx None: the
            # clamp guard is inert and MUST say so (a silently-ungated run
            # must be distinguishable from a checked one).
            errbuf = io.StringIO()
            try:
                with contextlib.redirect_stderr(errbuf):
                    pr.run_ollama({"num_ctx_max": 65536, "_out_base": obase},
                                  "x" * 1000, td, 5)
                ok(False, "context-filling prompt_eval_count should raise")
            except ValueError as e:
                ok("max_diff_tokens" in str(e)
                   and "raise num_ctx_max" not in str(e),
                   "truncation advice names max_diff_tokens, not num_ctx_max")
                ok(open(obase + ".raw.txt").read() == "paid-for",
                   "truncation raise still preserves the paid-for response")
            ok("trained context" in errbuf.getvalue()
               and "/api/show" in errbuf.getvalue(),
               "unreadable trained context warns on stderr (guard not "
               "silently inert)")
        finally:
            pr.open_url = real_open_url

        # --- lane names differing only in punctuation no longer collide ---
        ok(pr.safe_lane_name("codex") == "codex"
           and pr.safe_lane_name("gemini") == "gemini",
           "clean lane names keep byte-identical artifact paths")
        ok(pr.safe_lane_name("gemini-2.5-pro") != pr.safe_lane_name("gemini-2_5-pro"),
           "punctuation-differing lane names get distinct output bases")
        ok(pr.safe_lane_name("x" * 64 + "a") != pr.safe_lane_name("x" * 64 + "b"),
           "names sharing the first 64 safe chars get distinct output bases")
        ok(re.fullmatch(r"[A-Za-z0-9_-]+", pr.safe_lane_name("../../x")),
           "disambiguated names stay filesystem-safe (no dots or separators)")

        # --- codex/gemini env scrubbed: repo pointers don't enter the jail ---
        os.environ["CLAUDE_SELFTEST_LEAK"] = "/real/repo"
        real_sub = pr.subprocess.run
        try:
            pr.subprocess.run = fake_sub_run
            cap.clear()
            pr.run_codex({"_out_base": os.path.join(td, "lane2")}, "p", td, 5)
            ok("CLAUDE_SELFTEST_LEAK" not in cap["env"]
               and cap["env"]["PWD"] == cap["cwd"]
               and cap["env"]["OLDPWD"] == cap["cwd"],
               "codex env scrubbed: no CLAUDE_*, pwd vars point at the jail")
            cap.clear()
            pr.run_gemini({}, "p", td, 5)
            ok("CLAUDE_SELFTEST_LEAK" not in cap["env"]
               and cap["env"].get("GEMINI_CLI_TRUST_WORKSPACE") == "true",
               "gemini env scrubbed and still trusts the jail workspace")
        finally:
            pr.subprocess.run = real_sub
            os.environ.pop("CLAUDE_SELFTEST_LEAK", None)

        # ================= closeout additions ============================

        # --- consent_path never honors a RELATIVE XDG_CONFIG_HOME: resolved
        # against the cwd it can land INSIDE the reviewed checkout, handing
        # the 'machine-local' store back to whatever a clone or unpacked
        # bundle carries — the bundled-archive attack, re-armed ---
        hermetic_xdg = os.environ["XDG_CONFIG_HOME"]
        try:
            os.environ["XDG_CONFIG_HOME"] = ".config"    # attacker-relative
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                p_rel = pr.consent_path(loop)
            del os.environ["XDG_CONFIG_HOME"]
            ok(os.path.isabs(p_rel) and p_rel == pr.consent_path(loop),
               "relative XDG_CONFIG_HOME ignored — consent falls back to "
               "~/.config, never a cwd-relative dir")
            ok("XDG_CONFIG_HOME" in buf.getvalue(),
               "ignored relative XDG_CONFIG_HOME is called out on stderr")
        finally:
            os.environ["XDG_CONFIG_HOME"] = hermetic_xdg

        # --- consent-path verb: creates the consent dir (printed path is
        # writable on a FRESH machine) and refuses a nonexistent loop dir
        # (typo'd cwd would write consent no run ever reads) ---
        try:
            os.environ["XDG_CONFIG_HOME"] = os.path.join(td, "xdg-fresh")
            r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                    "consent-path", gloop])
            ok(r.returncode == 0
               and os.path.isdir(os.path.dirname(r.stdout.strip())),
               "consent-path creates the consent dir — printed path "
               "immediately writable on a fresh machine")
            r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                    "consent-path", os.path.join(td, "no-such-loop")])
            ok(r.returncode != 0 and not r.stdout.strip()
               and "does not exist" in r.stderr,
               "consent-path refuses a nonexistent loop dir instead of "
               "printing a path no run will ever read")
        finally:
            os.environ["XDG_CONFIG_HOME"] = hermetic_xdg

        # ================= XDG-inside-repo guard =========================

        # The hermetic override itself proves the positive case: an
        # ABSOLUTE base outside the reviewed repo is honored verbatim.
        ok(pr.consent_path(loop).startswith(xdg_td),
           "out-of-repo absolute XDG_CONFIG_HOME is honored")

        # --- an ABSOLUTE XDG_CONFIG_HOME resolving INSIDE the reviewed
        # checkout is rejected: repo-shipped env (.envrc, devcontainer, a
        # Makefile exporting XDG_CONFIG_HOME=$PWD/.config) must not hand
        # the 'machine-local' store back to files the bundle itself
        # carries. The bundle ships panel.json (cmd lane) + a PRE-ARMED
        # consent store at .config/review-loop-tools/consent/<hash>.json
        # approving that exact command — the lane must still be SKIPPED
        # and the command never executed. ---
        xroot = os.path.join(td, "xdg-attack")
        marker3 = os.path.join(td, "pwned-xdg")
        make_bundle(xroot, marker3)
        xloop = os.path.join(xroot, ".review-loop")
        evil_base = os.path.join(xroot, ".config")
        key = hashlib.sha256(
            os.path.realpath(xloop).encode("utf-8")).hexdigest()
        armed = os.path.join(evil_base, "review-loop-tools", "consent",
                             key + ".json")
        os.makedirs(os.path.dirname(armed))
        # The in-loop panel-consent.json make_bundle ships approves the
        # evil cmd — the armed store is that same content at the exact
        # path consent_path would compute for an in-checkout base.
        shutil.copy(os.path.join(xloop, "panel-consent.json"), armed)
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"], cwd=xroot,
               env=dict(os.environ, XDG_CONFIG_HOME=evil_base))
        lanes = {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}
        ok(r.returncode == 0 and lanes["evil"]["status"] == "skipped"
           and not os.path.exists(marker3),
           "in-checkout XDG_CONFIG_HOME + pre-armed consent store fails "
           "closed (cmd never executed)")
        ok("resolves inside the reviewed repo" in r.stderr,
           "in-checkout XDG_CONFIG_HOME rejection is called out on stderr")

        # --- symlink alias: a base OUTSIDE the repo that RESOLVES inside
        # it is rejected too (realpath on both sides) ---
        sneaky = os.path.join(xdg_td, "sneaky-link")
        os.symlink(evil_base, sneaky)
        buf = io.StringIO()
        try:
            os.environ["XDG_CONFIG_HOME"] = sneaky
            with contextlib.redirect_stderr(buf):
                p_link = pr.consent_path(xloop)
        finally:
            os.environ["XDG_CONFIG_HOME"] = hermetic_xdg
        ok(p_link.startswith(os.path.expanduser("~/.config"))
           and "resolves inside the reviewed repo" in buf.getvalue(),
           "symlinked-into-repo XDG_CONFIG_HOME rejected "
           "(realpath both sides)")

        # --- the ~/.config FALLBACK gets the same containment check: HOME
        # arrives by the same repo-shipped-env vector, and with HOME inside
        # the checkout there is NOWHERE trustworthy left — consent_path
        # returns None (hard fail-closed), load_consent grants nothing ---
        real_home = os.environ.get("HOME")
        buf = io.StringIO()
        try:
            del os.environ["XDG_CONFIG_HOME"]
            os.environ["HOME"] = os.path.join(td, "fakehome-unit")
            with contextlib.redirect_stderr(buf):
                p_home = pr.consent_path(loop)
                no_consent = pr.load_consent(loop)
        finally:
            os.environ["HOME"] = real_home
            os.environ["XDG_CONFIG_HOME"] = hermetic_xdg
        ok(p_home is None and no_consent == {}
           and "HOME" in buf.getvalue()
           and "NO consent" in buf.getvalue(),
           "in-repo HOME poisons the fallback too: consent_path None, "
           "load_consent fails closed, warning names HOME")

        # --- HOME-armed bundle attack END TO END: bundle ships panel.json
        # (cmd lane) + a consent store under .fakehome/.config, env exports
        # HOME=$PWD/.fakehome — the lane must be SKIPPED, cmd never run ---
        hroot = os.path.join(td, "home-attack")
        marker4 = os.path.join(td, "pwned-home")
        make_bundle(hroot, marker4)
        hloop = os.path.join(hroot, ".review-loop")
        fake_home = os.path.join(hroot, ".fakehome")
        hkey = hashlib.sha256(
            os.path.realpath(hloop).encode("utf-8")).hexdigest()
        harmed = os.path.join(fake_home, ".config", "review-loop-tools",
                              "consent", hkey + ".json")
        os.makedirs(os.path.dirname(harmed))
        shutil.copy(os.path.join(hloop, "panel-consent.json"), harmed)
        henv = {k: v for k, v in os.environ.items()
                if k != "XDG_CONFIG_HOME"}
        henv["HOME"] = fake_home
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "run", ".review-loop", "0"], cwd=hroot, env=henv)
        lanes = {l["lane"]: l for l in json.loads(r.stdout)["lanes"]}
        ok(r.returncode == 0 and lanes["evil"]["status"] == "skipped"
           and not os.path.exists(marker4),
           "in-checkout HOME + pre-armed .fakehome consent store fails "
           "closed (cmd never executed)")
        ok("HOME" in r.stderr and "NO consent" in r.stderr,
           "in-checkout HOME rejection is called out on stderr")
        # ...and the consent-path verb refuses instead of printing a path
        # inside the checkout that a bundle could pre-arm.
        r = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "consent-path", hloop], env=henv)
        ok(r.returncode != 0 and not r.stdout.strip()
           and "no trustworthy consent location" in r.stderr,
           "consent-path verb refuses when even the fallback base is "
           "in-repo, with a fix hint")

        # --- remote_lanes_approved grants ONLY as JSON true: a truthy
        # non-boolean in the human-edited file must gate lanes closed ---
        write_consent(loop, {"remote_lanes_approved": "yes"})
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            c_yes = pr.load_consent(loop)
        ok(c_yes.get("remote_lanes_approved") == "yes"
           and "only JSON true" in buf.getvalue(),
           "truthy non-boolean remote_lanes_approved warns on load")
        lanes = run_panel(td, {"OLLAMA_HOST": "http://gpu.example:11434"})
        ok(lanes["codexlane"]["status"] == "skipped"
           and lanes["local"]["status"] == "skipped",
           "remote_lanes_approved='yes' (truthy, not true) still gates "
           "remote lanes closed")

        # --- safe_lane_name: a sanitized output re-minted as a raw lane
        # name must not collide with the original's output base ---
        ok(pr.safe_lane_name(pr.safe_lane_name("a.b"))
           != pr.safe_lane_name("a.b"),
           "raw lane name spelled as a sanitized output gets its own "
           "suffix — no self-collision on one output base")
        ok(pr.safe_lane_name("codex") == "codex",
           "clean unsuffixed-looking names still pass through byte-identical")

        # --- sanitize: out-of-vocabulary, MISSING, and blank severity all
        # clamp, never drop — a candidate with claim + evidence intact must
        # reach the verifier (which adjudicates severity anyway) ---
        s2 = pr.sanitize({"findings": [
            {"claim": "warn", "evidence": ["a:1"], "severity": "Warning"},
            {"claim": "none", "evidence": ["a:1"]},
            {"claim": "blank", "evidence": ["a:1"], "severity": "  "}]},
            "l")
        ok(s2["filed"] == 3
           and all(f["severity"] == "minor" for f in s2["findings"]),
           "unknown/missing/blank severity clamps to minor instead of "
           "silently dropping the candidate")

        # --- render_report: 'sources'-only finding still renders its tags ---
        line2 = rr.finding_line({"id": "y", "severity": "minor",
                                 "current_status": "open",
                                 "sources": ["codex", "gemini"]})[0]
        ok("via codex+gemini" in line2,
           "'sources' without a singular 'source' key still renders "
           "attribution")

        # --- ollama /api/show metadata call bounded by the lane timeout ---
        tcalls = []
        def fake_ollama_t(req, t):
            url = req.full_url if hasattr(req, "full_url") else req
            tcalls.append((url, t))
            if url.endswith("/api/show"):
                return FakeResp({"model_info": {"qwen3.context_length": 65536}})
            return FakeResp({"response": "r", "prompt_eval_count": 100})
        real_open_url = pr.open_url
        try:
            pr.open_url = fake_ollama_t
            pr.run_ollama({"num_ctx_max": 65536}, "x" * 1000, td, 3)
            show_t = [t for u, t in tcalls if u.endswith("/api/show")]
            ok(show_t and all(t <= 3 for t in show_t),
               "ollama_model_ctx metadata call inherits the lane timeout "
               "(capped at 10s), not a hardcoded 10s")
        finally:
            pr.open_url = real_open_url

        # ================= 0.14.0 field-report additions =================

        # --- jail_env scrubs interpreter-injection vars (NODE_OPTIONS killed
        # both Node lanes at startup while the probe had passed) ---
        os.environ["NODE_OPTIONS"] = "--require=/gone.cjs"
        os.environ["DYLD_INSERT_LIBRARIES"] = "/x.dylib"
        os.environ["PANEL_KEEP_ME"] = "1"
        try:
            je = pr.jail_env(td)
            ok("NODE_OPTIONS" not in je and "DYLD_INSERT_LIBRARIES" not in je
               and je.get("PANEL_KEEP_ME") == "1",
               "jail_env drops NODE_OPTIONS/DYLD_*, keeps ordinary vars")
        finally:
            for k in ("NODE_OPTIONS", "DYLD_INSERT_LIBRARIES", "PANEL_KEEP_ME"):
                os.environ.pop(k, None)

        # --- error classification puts the line that matters FIRST ---
        k, note = pr.error_note("Loading model...\nwarning: slow\n"
                                "Error: Cannot find module '/var/x/restore.cjs'\n")
        ok(k == "launch" and note.startswith("Error: Cannot find module"),
           "launch failure classified, cause line first in note")
        k, _ = pr.error_note("x\nTerminalQuotaError: exhausted your daily quota")
        ok(k == "quota", "quota failure classified")
        k, _ = pr.error_note("404 model gemini-2.5-pro is no longer available")
        ok(k == "model-unavailable", "model-unavailable classified")
        k, _ = pr.error_note("something odd happened")
        ok(k == "other", "unknown failure is 'other'")

        # --- evidence-path pre-filter ---
        changed = ["src/App/MapScreen.swift", "Tests/MapTests.swift"]
        ok(pr.evidence_in_scope(["src/App/MapScreen.swift:12"], changed)
           and pr.evidence_in_scope(["b/src/App/MapScreen.swift:12"], changed)
           and pr.evidence_in_scope(["MapScreen.swift:12"], changed)
           and not pr.evidence_in_scope(["src/App/Other.swift:3"], changed)
           and pr.evidence_in_scope(["nowhere:1"], None),
           "evidence_in_scope: exact/prefixed/partial paths match; unknown "
           "paths do not; no list = everything in scope")
        s3 = pr.sanitize({"findings": [
            {"claim": "in", "evidence": ["src/App/MapScreen.swift:1"], "confidence": 0.5},
            {"claim": "out", "evidence": ["src/Elsewhere.swift:1"], "confidence": 0.99}]},
            "l", changed)
        ok(s3["filed"] == 1 and s3["dropped_no_evidence"] == 1
           and s3["findings"][0]["claim"] == "in",
           "sanitize drops candidates citing only unchanged files and counts them")
        s4 = pr.sanitize({"findings": [
            {"claim": str(i), "evidence": ["src/App/MapScreen.swift:1"],
             "confidence": 0.5} for i in range(8)]}, "l", changed, cap=3)
        ok(s4["filed"] == 3 and s4["overflow_dropped"] == 5,
           "sanitize honors a per-call cap")

        # --- passive usage capture ---
        ok(pr.usage_from_text('{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}')
           == {"input_tokens": 12, "output_tokens": 3}
           and pr.usage_from_text("done. tokens used: 1,234") == {"total_tokens": 1234}
           and pr.usage_from_text("no numbers here") is None,
           "usage_from_text captures JSON usage or a tokens-used line, never estimates")

        # --- run: --lanes filter, cached candidates, --force, summary file,
        # failed/skipped counts, banner --- (earlier checks left the fixture's
        # consent malformed; restore a real one so cmd lanes actually run)
        write_consent(loop, {"cmd_lanes_approved": [
            hashlib.sha256(good_cmd.encode()).hexdigest(), "exit 3", "true"]})
        def run_args(*extra, env_extra=None):
            env = dict(os.environ, **(env_extra or {}))
            return sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                       "run", ".review-loop", "0"] + list(extra), cwd=td, env=env)
        r = run_args("--lanes", "good", "--force")
        d = json.loads(r.stdout)
        ok(r.returncode == 0 and [l["lane"] for l in d["lanes"]] == ["good"],
           "run --lanes runs only the named lane")
        ok(os.path.exists(pr.summary_path(loop, "0"))
           and json.load(open(pr.summary_path(loop, "0")))["lanes"][0]["lane"] == "good",
           "run writes the round summary file")
        ok("elapsed_s" in d["lanes"][0], "lane result carries elapsed_s")
        r = run_args("--lanes", "good")
        ok(json.loads(r.stdout)["lanes"][0]["status"] == "cached",
           "a lane with existing candidates is reported cached without --force")
        r = run_args("--lanes", "nope")
        ok(r.returncode == 2 and "not in panel.json" in r.stderr,
           "run --lanes with an unknown name exits 2")
        r = run_args("--lanes", "failcmd,off", "--force")
        d = json.loads(r.stdout)
        ok(d["failed"] == 1 and d["skipped"] == 1
           and "lane failcmd ERROR" in r.stderr and "lane off SKIPPED" in r.stderr,
           "run reports failed/skipped counts and one stderr banner per lane")
        ok(r.returncode == 0, "lane failures stay SOFT (exit 0)")

        # --- run refuses an EMPTY diff ---
        dpath = os.path.join(loop, "briefs", "round-0.diff")
        saved_diff = open(dpath).read()
        open(dpath, "w").close()
        r = run_args("--force")
        ok(r.returncode == 2 and "EMPTY" in r.stderr,
           "run refuses a 0-line round diff instead of reporting a clean pass")
        open(dpath, "w").write(saved_diff)

        # --- --detach + wait ---
        spath = pr.summary_path(loop, "0")
        r = run_args("--detach", "--lanes", "good", "--force")
        d = json.loads(r.stdout)
        ok(r.returncode == 0 and d.get("detached") and "pid" in d,
           "run --detach returns at once with pid and summary path")
        w = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "wait", ".review-loop", "0", "--timeout", "30"], cwd=td)
        ok(w.returncode == 0 and json.loads(w.stdout)["lanes"][0]["lane"] == "good",
           "wait blocks for the detached run and prints its summary")
        os.remove(spath)
        w = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "wait", ".review-loop", "0", "--timeout", "0"], cwd=td)
        ok(w.returncode == 3, "wait exits 3 when the summary has not landed")

        # --- model fallback list: quota on the first model tries the next ---
        calls = []
        def fake_runner(lane, prompt, repo, timeout):
            calls.append(lane.get("model"))
            if lane.get("model") == "pro":
                return "", subprocess.CompletedProcess([], 1, "", "429 quota exceeded")
            return '{"findings": []}', subprocess.CompletedProcess([], 0, "", "")
        real_runner = pr.RUNNERS["cmd"]
        try:
            pr.RUNNERS["cmd"] = fake_runner
            write_consent(loop, {"cmd_lanes_approved": ["fb"]})
            res = pr.run_lane({"name": "fb", "type": "cmd", "cmd": "fb",
                               "model": ["pro", "flash"], "_force": True},
                              loop, "0", td, pr.load_consent(loop))
            ok(calls == ["pro", "flash"] and res["status"] == "ok"
               and res["model_used"] == "flash",
               "model list falls through on quota and records model_used")
            calls.clear()
            def fake_auth(lane, prompt, repo, timeout):
                calls.append(lane.get("model"))
                return "", subprocess.CompletedProcess([], 1, "", "401 unauthorized")
            pr.RUNNERS["cmd"] = fake_auth
            res = pr.run_lane({"name": "fb", "type": "cmd", "cmd": "fb",
                               "model": ["a", "b"], "_force": True},
                              loop, "0", td, pr.load_consent(loop))
            ok(calls == ["a"] and res["status"] == "error" and res["error_kind"] == "auth",
               "auth failure does NOT fall through to the next model")
        finally:
            pr.RUNNERS["cmd"] = real_runner

        # --- precision: final-pass cap from the seed tally; cross-loop disable ---
        led_path = os.path.join(loop, "ledger.json")
        json.dump({"findings": [], "panel": {"0": {"good": {"filed": 10, "confirmed": 0,
                                                            "demoted": 0, "rejected": 10}}}},
                  open(led_path, "w"))
        for fn in ("round-final.stat", "round-final.diff"):
            shutil.copy(os.path.join(loop, "briefs", fn.replace("final", "0")),
                        os.path.join(loop, "briefs", fn))
        many = (sys.executable + " -c \"import sys,json; sys.stdin.read(); "
                "print(json.dumps({'findings':[{'claim':str(i),'evidence':['a.md:1'],"
                "'severity':'minor','confidence':0.5} for i in range(8)]}))\"")
        write_consent(loop, {"cmd_lanes_approved": [many]})
        res = pr.run_lane({"name": "good", "type": "cmd", "cmd": many, "_force": True},
                          loop, "final", td, pr.load_consent(loop))
        ok(res["status"] == "ok" and res["filed"] == 3 and res["cap"] == 3
           and "seed kept 0/10" in res["cap_reason"],
           "final pass caps a 0/10 seed lane at 3 and says why")
        res = pr.run_lane({"name": "other", "type": "cmd", "cmd": many, "_force": True},
                          loop, "final", td, pr.load_consent(loop))
        ok(res["filed"] == 8, "a lane without a 0/N seed tally is not capped")
        for i, name in enumerate(("20260901-000000-aaaaaaa", "20260902-000000-bbbbbbb")):
            d = os.path.join(loop, "archive", name)
            os.makedirs(d)
            json.dump({"panel": {"0": {"good": {"filed": 10, "confirmed": 0, "demoted": 0}},
                                 "final": {"good": {"filed": 6, "confirmed": 0, "demoted": 0}}}},
                      open(os.path.join(d, "ledger.json"), "w"))
        ok(pr.precision_disabled(loop, "good") and not pr.precision_disabled(loop, "other"),
           "0/N in the two most recent archived loops disables the lane; others untouched")
        res = pr.run_lane({"name": "good", "type": "cmd", "cmd": many, "_force": True},
                          loop, "0", td, pr.load_consent(loop))
        ok(res["status"] == "disabled-by-precision", "run skips a precision-disabled lane")
        res = pr.run_lane({"name": "good", "type": "cmd", "cmd": many, "_force": True,
                           "precision_override": True},
                          loop, "0", td, pr.load_consent(loop))
        ok(res["status"] == "ok", "precision_override re-enables the lane")
        os.remove(led_path)
        shutil.rmtree(os.path.join(loop, "archive"))

        # --- probe reports consent and gate issues ---
        write_consent(loop, {})
        p = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "probe", os.path.join(loop, "panel.json")], cwd=td)
        pd = json.loads(p.stdout)
        ok(any("no remote-lane consent" in i for i in pd["gate_issues"])
           and "GATE" in p.stderr,
           "probe lists a configured remote lane without consent as a gate issue")
        ok(pd.get("good", {}).get("consent", "").startswith("MISSING"),
           "probe marks an unapproved cmd lane's consent MISSING")
        write_consent(loop, {"remote_lanes_approved": True})
        p = sh([sys.executable, os.path.join(SCRIPTS, "panel_review.py"),
                "probe", os.path.join(loop, "panel.json")], cwd=td)
        pd = json.loads(p.stdout)
        ok(not any("remote-lane consent" in i for i in pd["gate_issues"]),
           "probe reports consent ok once granted")

        # --- panel-tally MERGES per lane; --replace replaces; kept/duplicate ---
        json.dump({"findings": []}, open(led_path, "w"))
        v1 = os.path.join(td, "v1.json"); v2 = os.path.join(td, "v2.json")
        json.dump({"lane_tallies": {"codex": {"filed": 3, "confirmed": 1, "demoted": 0,
                                              "duplicate": 1, "rejected": 1}}}, open(v1, "w"))
        json.dump({"lane_tallies": {"gemini": {"filed": 6, "confirmed": 0, "demoted": 2,
                                               "rejected": 4}}}, open(v2, "w"))
        ML = os.path.join(SCRIPTS, "merge_ledger.py")
        sh([sys.executable, ML, "panel-tally", led_path, "0", v1])
        t = json.loads(sh([sys.executable, ML, "panel-tally", led_path, "0", v2]).stdout)
        ok(set(t["lanes"]) == {"codex", "gemini"} and t["lanes"]["codex"]["kept"] == 1
           and t["lanes"]["codex"]["duplicate"] == 1 and t["lanes"]["gemini"]["kept"] == 2,
           "panel-tally merges a second batch per lane; kept excludes duplicates")
        t = json.loads(sh([sys.executable, ML, "panel-tally", led_path, "0", v1,
                           "--replace"]).stdout)
        ok(set(t["lanes"]) == {"codex"}, "panel-tally --replace replaces the round")
        rep = rr.main.__code__  # render must tolerate and show the duplicate column
        os.remove(led_path)

        # --- merge_ledger: scope and diff share ONE parser; failed diff leaves
        # no partial files; stat trailer names excluded-but-changed paths ---
        import merge_ledger as ml                                    # noqa: E402
        ok(ml.split_range(["a..b -- ':!prompts.md'"]) == ("a..b", ["--", ":!prompts.md"])
           and ml.split_range(["a..b", "--", ":!x"]) == ("a..b", ["--", ":!x"]),
           "split_range accepts the quoted single string and separate words alike")

        # --- CONTROLS.md mirrors stay byte-identical (HANDOFF.md cp-sync) ---
        repo = os.path.abspath(os.path.join(HERE, "..", ".."))
        digests = {p: hashlib.md5(open(os.path.join(repo, p), "rb").read())
                   .hexdigest()
                   for p in ("CONTROLS.md", "qa-loop-tools/CONTROLS.md",
                             "review-loop-tools/CONTROLS.md")}
        ok(len(set(digests.values())) == 1,
           "CONTROLS.md mirrors byte-identical: " + json.dumps(digests))

        print(f"\nALL {PASS} CHECKS PASSED")
    finally:
        shutil.rmtree(td, ignore_errors=True)
        shutil.rmtree(xdg_td, ignore_errors=True)

if __name__ == "__main__":
    main()
