#!/usr/bin/env python3
"""Self-test for the feedback path: telemetry hooks, the anomaly verb, the
run summary, token measurement, the feedback command, the allowlist, the
drop, archive, and the maintainer's ingest.

Usage: feedback_selftest.py [--plugin review-loop-tools|qa-loop-tools]

Hermetic: everything runs in a tempdir with HOME and XDG_DATA_HOME pointed
inside it (XDG at a SIBLING of the scratch repo), so no real transcript,
plugin registry, drop or loop is read or written. The shared scripts are
byte-identical in both loop plugins; --plugin qa-loop-tools runs the same
checks against the qa copies and the qa skill's allowlist.
Exits nonzero on the first failure.
"""
import datetime, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = "review-loop-tools"
if "--plugin" in sys.argv:
    PLUGIN = sys.argv[sys.argv.index("--plugin") + 1]
ROOT = os.path.join(REPO, PLUGIN)
SCRIPTS = os.path.join(ROOT, "scripts")
IS_QA = PLUGIN.startswith("qa-")
LOOP = ".qa-loop" if IS_QA else ".review-loop"
SKILL = os.path.join(ROOT, "skills", "qa-loop" if IS_QA else "review-loop", "SKILL.md")
SHORT = "qa" if IS_QA else "rl"
SECRET = "ZEBRA-CLAIM-TEXT-MUST-NOT-LEAVE-THE-HOST"

PASS = 0
def ok(cond, label, detail=""):
    global PASS
    if not cond:
        print(f"FAIL: {label}\n{detail}", file=sys.stderr)
        sys.exit(1)
    PASS += 1
    print(f"ok: {label}")

def main():
    td = os.path.realpath(tempfile.mkdtemp(prefix="feedback-selftest-"))
    try:
        run(td)
        print(f"\nALL {PASS} CHECKS PASSED ({PLUGIN})")
    finally:
        shutil.rmtree(td, ignore_errors=True)

def run(td):
    home, repo, xdg = (os.path.join(td, n) for n in ("home", "hostrepo", "xdg"))
    for d in (home, repo, xdg):
        os.makedirs(d)
    env = dict(os.environ, HOME=home, XDG_DATA_HOME=xdg, PYTHONDONTWRITEBYTECODE="1",
               REVIEW_LOOP_ARCHIVE_SETTLE_S="0")
    env.pop("FIELD_LOG_OFF", None)

    def sh(cmd, payload=None, extra=None, cwd=repo):
        return subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                              capture_output=True, text=True, cwd=cwd,
                              env=dict(env, **(extra or {})))
    def py(script, *args, **kw):
        return sh([sys.executable, os.path.join(SCRIPTS, script)] + list(args), **kw)
    def hook(name, args, payload, **kw):
        return sh(["bash", os.path.join(SCRIPTS, name)] + args, payload=payload, **kw)
    def git(*a):
        return sh(["git"] + list(a))
    def rows(name):
        p = os.path.join(repo, LOOP, "feedback", name)
        if not os.path.exists(p):
            return []
        return [json.loads(l) for l in open(p) if l.strip()]
    def write(rel, text):
        p = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    git("init", "-q")
    git("config", "user.email", "selftest@example.invalid")
    git("config", "user.name", "selftest")

    # ---------- the allowlist, taken from the SHIPPED skill text ----------
    skill = open(SKILL, encoding="utf-8").read()
    m = re.search(r"```\n\s*(# Conclusions in git;.*?)```", skill, re.S)
    ok(bool(m), "the skill carries the loop-dir allowlist template")
    allow = "\n".join(l.strip() for l in m.group(1).splitlines()) + "\n"
    version = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]
    stamp = re.search(r"Managed by " + re.escape(PLUGIN) + r" v(\d+\.\d+\.\d+)", allow)
    # The stamp names the release that last CHANGED the template, so it may
    # trail the plugin version — it can never lead it.
    ok(bool(stamp) and tuple(map(int, stamp.group(1).split("."))) <= tuple(map(int, version.split(".")))
       and all(r in allow for r in ("!**/feedback/*.json", "!**/feedback/*.jsonl", "!**/feedback/*.md")),
       "allowlist is stamped by a release no newer than this one and tracks feedback/",
       allow.splitlines()[0])
    write(f"{LOOP}/.gitignore", allow)

    ledger = {"round": 1, "max_rounds": 5, "token_budget": None,
              "usage": {"1": {"implementer": 1000, "reviewer": 2000}},
              "findings": [
                  {"id": "a/x:one", "claim": SECRET, "severity": "major",
                   "current_status": "fixed", "region": "src/Secret.swift",
                   "evidence": ["src/Secret.swift:10"],
                   "status_history": [{"round": 0, "status": "open"},
                                      {"round": 1, "status": "fixed"}]},
                  {"id": "a/x:two", "claim": SECRET, "severity": "minor",
                   "current_status": "open", "fix_risk": "behavior-change",
                   "rejections": [{"round": 1, "reason": SECRET}]}]}
    if IS_QA:
        ledger.update({"build_sha": None, "implemented_rounds": [1], "parallel_testers": 2})
    write(f"{LOOP}/ledger.json", json.dumps(ledger, indent=2))
    write(f"{LOOP}/rounds.md",
          "| Round | Blockers | Majors | Minors | Closed | New | Reopened | Promoted | Net | Tokens | Decision |\n"
          "|-------|----------|--------|--------|--------|-----|----------|----------|-----|--------|----------|\n"
          "| 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | +1 | 3000 | converged |\n"
          "> round 1: REVIEW_LOOP_UNATTENDED set — unattended default taken at `thrashing_soft`: abort\n")
    write(f"{LOOP}/verdict.json", json.dumps(
        {"round": 1, "decision": "converged", "reason": "no open blockers or majors"}))
    tp = write("transcript.jsonl", "{}\n")

    # ---------- dispatch telemetry ----------
    write(f"{LOOP}/.phase", "done\n")
    hook("dispatch_stamp.sh", [LOOP, "2"],
         {"tool_name": "Agent", "transcript_path": tp,
          "tool_input": {"subagent_type": "implementer", "description": "x"}})
    ok(rows("dispatches.jsonl") == [], "no dispatch is recorded while .phase is done")
    write(f"{LOOP}/.phase", "round-1-implementing\n")
    hook("dispatch_stamp.sh", [LOOP, "2"],
         {"tool_name": "Agent", "transcript_path": tp,
          "tool_input": {"subagent_type": "implementer", "description": "x"}},
         extra={"FIELD_LOG_OFF": "1"})
    ok(rows("dispatches.jsonl") == [], "FIELD_LOG_OFF=1 records nothing")
    ok(open(os.path.join(repo, LOOP, ".phase")).read().strip() == "round-1-implementing:dispatched",
       "…and the hook still stamped :dispatched (telemetry never changes behavior)")
    hook("subagent_guard.sh", [LOOP], {}, extra={"FIELD_LOG_OFF": "1"})

    impl = f"{PLUGIN}:{'qa-implementer' if IS_QA else 'implementer'}"
    rev = "ux-tester" if IS_QA else "skeptical-reviewer"
    r = hook("dispatch_stamp.sh", [LOOP, "2"],
             {"tool_name": "Agent", "transcript_path": tp, "tool_use_id": "toolu_1",
              "tool_input": {"subagent_type": impl, "description": "Round 1 implementer"}})
    ok(r.returncode == 0 and len(rows("dispatches.jsonl")) == 1,
       "first dispatch records a start", r.stderr)
    time.sleep(0.05)
    hook("dispatch_stamp.sh", [LOOP, "2"],
         {"tool_name": "Agent", "transcript_path": tp, "tool_use_id": "toolu_2",
          "tool_input": {"subagent_type": rev, "description": f"Round 1 in {home}/secret"}})
    d = rows("dispatches.jsonl")
    ok(len(d) == 2 and d[1]["agent"] == rev and "session_mb" in d[1],
       "overlapping dispatch records a second start with session size")
    ok(home not in json.dumps(d), "the home directory is folded to ~ in dispatch labels")
    time.sleep(0.05)
    hook("subagent_guard.sh", [LOOP], {"agent_type": rev, "agent_id": "a1"})
    time.sleep(0.05)
    hook("subagent_guard.sh", [LOOP], {"agent_type": impl.split(":")[-1], "agent_id": "a2"})
    d = rows("dispatches.jsonl")
    ok([x["event"] for x in d] == ["start", "start", "end", "end"],
       "both returns are recorded")
    sys.path.insert(0, SCRIPTS)
    import field_log
    pairs, unmatched, stray = field_log.pair_dispatches(d)
    ok(len(pairs) == 2 and not unmatched and not stray,
       "two starts and two ends pair into two dispatches")
    by = {p["agent"]: p for p in pairs}
    ok(set(by) == {impl.split(":")[-1], rev}
       and by[rev]["wall_s"] < by[impl.split(":")[-1]]["wall_s"],
       "returns pair by AGENT, not arrival order (the later dispatch returned first)",
       json.dumps(pairs))
    ok(open(os.path.join(repo, LOOP, ".phase")).read().strip() == "round-1-implementing",
       "the live-dispatch counter still strips :dispatched at zero")

    # ---------- anomaly verb ----------
    r = py("merge_ledger.py", "anomaly", LOOP, f"re-ran the gemini lane by hand from {home}/x")
    ok(r.returncode == 0 and json.loads(r.stdout)["recorded"] == "workaround", "anomaly verb records", r.stderr)
    r = py("merge_ledger.py", "anomaly", LOOP, "second notification", "--code", "Usage Repeat Notification")
    ok(json.loads(r.stdout)["recorded"] == "usage-repeat-notification", "codes are normalized to kebab-case")
    a = rows("anomalies.jsonl")
    ok(len(a) == 2 and a[0]["phase"] == "round-1-implementing" and a[0]["round"] == 1
       and "~/x" in a[0]["detail"] and home not in a[0]["detail"],
       "anomaly rows carry phase and round, with the home directory folded")
    r = py("merge_ledger.py", "anomaly", "no-such-loop", "x")
    ok(r.returncode == 1 and not os.path.exists(os.path.join(repo, "no-such-loop")),
       "anomaly on a missing loop dir fails and never creates one")
    r = py("merge_ledger.py", "anomaly", LOOP)
    ok(r.returncode == 2, "anomaly without text is a usage error")
    before = open(os.path.join(repo, LOOP, "ledger.json")).read()
    py("merge_ledger.py", "anomaly", LOOP, "x")
    ok(open(os.path.join(repo, LOOP, "ledger.json")).read() == before,
       "the anomaly verb never touches the ledger")

    # ---------- guards record WHICH rule, never the command ----------
    write(f"{LOOP}/.phase", "round-1-review\n")
    r = hook("read_guard.sh", [LOOP], {"tool_name": "Bash", "tool_input": {
        "command": "xcodebuild test -scheme SecretScheme -destination x"}})
    a = rows("anomalies.jsonl")
    ok(r.returncode != 0 and a[-1]["code"] == "read-guard-denied"
       and a[-1]["detail"] == "unfiltered test run" and "SecretScheme" not in json.dumps(a),
       "read_guard denial recorded by rule name")
    r = hook("commit_guard.sh", [LOOP], {"tool_name": "Bash", "tool_input": {
        "command": "git add -A && git commit -m secret-message"}})
    a = rows("anomalies.jsonl")
    ok(r.returncode != 0 and a[-1]["code"] == "commit-guard-denied"
       and "secret-message" not in json.dumps(a), "commit_guard denial recorded by rule name")
    n = len(a)
    hook("commit_guard.sh", [LOOP], {"tool_name": "Bash", "tool_input": {
        "command": "git add src/a.swift"}})
    ok(len(rows("anomalies.jsonl")) == n, "an allowed command records nothing")

    # ---------- next-round counter check (review only: needs metrics.py) ----------
    write(f"{LOOP}/briefs/.dispatched", "1\n")
    write("f.txt", "x\n")
    git("add", "f.txt")
    git("commit", "-q", "-m", "init")
    r = py("merge_ledger.py", "next-round", LOOP, "1")
    a = rows("anomalies.jsonl")
    ok(r.returncode == 0 and a[-1]["code"] == "dispatch-count-mismatch",
       "next-round records a non-zero live-dispatch counter", r.stderr)
    write(f"{LOOP}/briefs/.dispatched", "0\n")
    led = json.load(open(os.path.join(repo, LOOP, "ledger.json")))
    led["round"] = 1
    write(f"{LOOP}/ledger.json", json.dumps(led, indent=2))

    # ---------- hygiene ----------
    write(f"{LOOP}/fragments/round-1.json", "{}")
    git("add", "-f", f"{LOOP}/fragments/round-1.json")
    sh(["bash", os.path.join(SCRIPTS, "hygiene_check.sh"), LOOP])
    sh(["bash", os.path.join(SCRIPTS, "hygiene_check.sh"), LOOP])
    hy = [x for x in rows("anomalies.jsonl") if x["code"] == "hygiene-violation"]
    ok(len(hy) == 1 and "scratch" in hy[0]["detail"] and "round-1.json" not in hy[0]["detail"],
       "hygiene violation recorded once (deduped), by kind", json.dumps(hy))
    git("rm", "-q", "--cached", f"{LOOP}/fragments/round-1.json")

    # ---------- fake transcripts ----------
    enc = re.sub(r"[^A-Za-z0-9]", "-", repo)
    proj = os.path.join(home, ".claude", "projects", enc)
    os.makedirs(os.path.join(proj, "sess", "subagents"))
    now = datetime.datetime.now(datetime.timezone.utc)
    def rec(rid, delta_s, **u):
        return json.dumps({"timestamp": (now + datetime.timedelta(seconds=delta_s)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"), "requestId": rid, "message": {"usage": u}}) + "\n"
    U = dict(input_tokens=100, cache_read_input_tokens=1000,
             cache_creation_input_tokens=10, output_tokens=20)      # effective 320
    with open(os.path.join(proj, "sess.jsonl"), "w") as fh:
        fh.write(rec("r1", 1, **U) + rec("r1", 1, **U) + rec("r2", 2, **U))
        fh.write(rec("old", -90000, **U))                  # outside the window
    with open(os.path.join(proj, "sess", "subagents", "agent-a1.jsonl"), "w") as fh:
        fh.write(json.dumps({"isSidechain": True}) + "\n" + rec("s1", 3, **U))
    with open(os.path.join(proj, "sess", "subagents", "agent-a1.meta.json"), "w") as fh:
        json.dump({"agentType": f"{PLUGIN}:{rev}", "description": "Round 1 reviewer"}, fh)
    r = py("loop_usage.py", "--repo", repo, "--since", str(time.time() - 3600))
    u = json.loads(r.stdout)
    ok(u["effective_total"] == 960 and u["effective_subagents"] == 320
       and u["effective_orchestrator"] == 640,
       "effective tokens: weights applied, duplicate requestId counted once, window honored",
       r.stdout + r.stderr)
    ok([x["role"] for x in u["by_role"]] == ["orchestrator", rev]
       and u["by_dispatch"][0]["label"] == "Round 1 reviewer",
       "roles come from the sidecar, plugin prefix dropped; per-dispatch rows present")
    ok(home not in r.stdout, "usage output carries no absolute paths")
    r = py("loop_usage.py", "--repo", os.path.join(td, "nowhere"))
    ok(r.returncode == 1 and "no transcript directory" in r.stderr,
       "a repo with no transcripts is an error, not an empty table")

    # ---------- plugin registry ----------
    os.makedirs(os.path.join(home, ".claude", "plugins"))
    with open(os.path.join(home, ".claude", "plugins", "installed_plugins.json"), "w") as fh:
        json.dump({"version": 2, "plugins": {f"{PLUGIN}@quiller": [
            {"installPath": os.path.join(home, "cache", PLUGIN, "0.0.1"), "version": "0.0.1",
             "lastUpdated": "2026-01-01T00:00:00Z", "gitCommitSha": "abc123def4567890"}]}}, fh)

    # ---------- report stage writes the summary ----------
    write(f"{LOOP}/.phase", "done\n")
    r = py("render_report.py", LOOP, "--stop-note", f"user abort near {home}/x")
    out = json.loads(r.stdout)
    spath = os.path.join(repo, LOOP, "feedback", "run-summary.json")
    ok(r.returncode == 0 and out.get("run_summary") and os.path.exists(spath),
       "render_report writes feedback/run-summary.json", r.stderr)
    raw = open(spath).read()
    s = json.loads(raw)
    ok(s["plugin"]["name"] == PLUGIN and s["plugin"]["version"] == version,
       "summary names the plugin version from the code that ran")
    ok(s["plugin"]["installed"]["version"] == "0.0.1"
       and s["plugin"]["install_matches_running"] is False,
       "installed-vs-running mismatch is recorded")
    ok(SECRET not in raw and "Secret.swift" not in raw and "a/x:one" not in raw,
       "no finding claim, id, region or evidence reaches the summary")
    ok(home not in raw, "no absolute home path reaches the summary")
    f = s["findings"]
    ok(f["total"] == 2 and f["by_severity"] == {"major": 1, "minor": 1}
       and f["by_status"] == {"fixed": 1, "open": 1}
       and f["fix_review_rejections"] == 1 and f["fix_risk_flagged"] == 1,
       "finding counts by severity and status", json.dumps(f))
    ok(s["rounds"]["count"] == 1 and s["rounds"]["table"][0]["decision"] == "converged"
       and s["rounds"]["table"][0]["net"] == 1 and len(s["unattended_defaults"]) == 1,
       "rounds table parsed; unattended default captured")
    ok(s["stop"]["decision"] == "converged" and "~/x" in s["stop"]["stop_note"],
       "stop condition and stop note recorded")
    ok(s["dispatches"]["count"] == 2 and s["dispatches"]["unreturned"] == 0,
       "dispatch wall-clock reaches the summary")
    ok(s["anomalies"]["by_code"].get("read-guard-denied") == 1
       and s["anomalies"]["by_code"].get("workaround") == 2,
       "anomalies grouped by code", json.dumps(s["anomalies"]["by_code"]))
    ok(s["usage_reported"]["total"] == 3000 and "dispatches.jsonl" in s["window"]["basis"],
       "reported usage and the dispatch-derived window")
    ok(all(v for v in s["platform"].values()), "every platform probe has a value (unknown, never absent)")
    ok("run-summary" not in open(os.path.join(repo, LOOP, "REPORT.md")).read().lower(),
       "the summary is never a section of REPORT.md")

    # ---------- allowlist ----------
    write(f"{LOOP}/briefs/round-1-brief.json", "{}")
    write(f"{LOOP}/feedback/notes.txt", "x")
    write(f"{LOOP}/feedback/report 2.md", "x")
    def ignored(rel):
        return git("check-ignore", "-q", rel).returncode == 0
    for rel in ("feedback/run-summary.json", "feedback/anomalies.jsonl",
                "feedback/dispatches.jsonl", "feedback/x-0.1.0-2026-01-01.md",
                "archive/20260101-000000-abc1234/feedback/run-summary.json",
                "ledger.json", "archive/n/ledger.json"):
        ok(not ignored(f"{LOOP}/{rel}"), f"allowlist tracks {rel}")
    for rel in ("briefs/round-1-brief.json", "fragments/round-1.json", "feedback/notes.txt",
                "briefs/.dispatched", ".phase", "ledger 2.json"):
        ok(ignored(f"{LOOP}/{rel}"), f"allowlist ignores {rel}")
    os.remove(os.path.join(repo, LOOP, "feedback", "report 2.md"))
    os.remove(os.path.join(repo, LOOP, "feedback", "notes.txt"))

    # ---------- scaffold ----------
    r = py("feedback.py", "questions")
    q = json.loads(r.stdout)
    ok(q["found"] and len(q["watch"]) >= 5 and len(q["settled"]) >= 5
       and all(re.fullmatch(r"w-[a-z0-9-]+", w["id"]) for w in q["watch"])
       and len({w["id"] for w in q["watch"]}) == len(q["watch"]),
       "FIELD-QUESTIONS.md parses: watch items and settled decisions, unique ids")
    fq = open(os.path.join(ROOT, "FIELD-QUESTIONS.md")).read()
    ok("_Not yet generated._" not in fq and "BEGIN generated" in fq,
       "FIELD-QUESTIONS.md carries a generated dispositions section")
    r = py("feedback.py", "scaffold", LOOP, "--date", "2026-09-26")
    ok(r.returncode == 0, "scaffold runs", r.stderr)
    sc = json.loads(r.stdout)
    draft = os.path.join(repo, sc["draft"])
    ok(os.path.basename(draft) == f"{PLUGIN}-{version}-2026-09-26.md"
       and sc["watch_items"] == len(q["watch"]) and sc["effective_total"] == 960,
       "draft is named <plugin>-<version>-<date>.md and carries the measured cost", r.stdout)
    text = open(draft).read()
    ok(f"id-prefix: {SHORT}-{version}-20260926-hostrepo" in text and "status: draft" in text,
       "front matter carries the id prefix with the host name")
    ok("**MISMATCH**" in text and "`read-guard-denied` x1" in text and "| orchestrator |" in text,
       "the glance shows version mismatch, anomalies and the usage table")
    ok(SECRET not in text and home not in text, "the draft leaks neither claims nor home paths")
    r = py("feedback.py", "scaffold", LOOP, "--date", "2026-09-26")
    ok(r.returncode == 1 and "draft already exists" in r.stderr,
       "a second scaffold refuses to clobber a draft in progress")

    # ---------- finalize: validation ----------
    r = py("feedback.py", "finalize", LOOP)
    ok(r.returncode == 1 and "answer must be one of" in r.stderr,
       "finalize refuses unanswered watch items")
    first = q["watch"][0]["id"]
    text = text.replace("  - answer: _unanswered_", "  - answer: not observed")
    text = text.replace(f"**{first}** — ", f"**{first}** — ", 1)
    head, tail = text.split(f"- **{first}**", 1)
    tail = tail.replace("  - answer: not observed", "  - answer: observed", 1)
    open(draft, "w").write(head + f"- **{first}**" + tail)
    r = py("feedback.py", "finalize", LOOP)
    ok(r.returncode == 1 and f"{first}: `observed` needs one line of evidence" in r.stderr,
       "`observed` without evidence is refused")
    text = open(draft).read()
    head, tail = text.split(f"- **{first}**", 1)
    tail = tail.replace("  - evidence: ", "  - evidence: rounds.md row 1", 1)
    text = head + f"- **{first}**" + tail
    text = re.sub(r"(## Defects\n\n<!-- guide.*?-->\n)", lambda m: m.group(1) + (
        "\n### Panel lane died silently\n- happened: lane exited 0 with no candidates\n"
        "- expected: a loud failure\n- repro: run with NODE_OPTIONS set\n"
        "- evidence: feedback/anomalies.jsonl lane-error\n- cost: 2 turns\n- mechanism: \n"
        "\n### No repro for this one\n- happened: something\n- expected: \n- repro: \n"
        "- evidence: \n- cost: \n- mechanism: \n"), text, flags=re.S)
    text = re.sub(r"(## Wishes\n\n<!-- guide.*?-->\n)",
                  lambda m: m.group(1) + "\n- Timestamps in rounds.md rows\n", text, flags=re.S)
    open(draft, "w").write(text)
    r = py("feedback.py", "finalize", LOOP)
    ok(r.returncode == 0, "finalize accepts a complete report", r.stderr)
    fin = json.loads(r.stdout)
    pre = f"{SHORT}-{version}-20260926-hostrepo"
    ok(fin["ids"] == [f"{pre}-1", f"{pre}-2", f"{pre}-3"],
       "ids minted in document order across sections", r.stdout)
    ok(any("no repro or evidence" in w for w in fin["warnings"]) and len(fin["warnings"]) == 1,
       "a defect without repro or evidence draws a warning (and only that one)", r.stdout)
    final = open(draft).read()
    ok("status: filed" in final and "items: 3" in final and "<!-- guide" not in final,
       "report is marked filed; guide comments are gone")
    ok(f"### {pre}-1 — Panel lane died silently" in final
       and f"- **{pre}-3** — Timestamps in rounds.md rows" in final, "ids are stamped on the items")
    ok("## Friction\n\n_none_" in final, "empty sections read _none_")
    apx = re.findall(r"```json\n(.*?)\n```", final, re.S)
    ok(len(apx) == 2 and json.loads(apx[0])["plugin"]["version"] == version
       and json.loads(apx[1])["effective_total"] == 960,
       "the report is self-contained: summary and usage appended as JSON")
    drop = os.path.join(xdg, "quiller", "inbox", "hostrepo", os.path.basename(draft))
    ok(os.path.exists(drop) and open(drop).read() == final,
       "the report is copied to the XDG drop, under the host's name")
    ok(fin["git_ignored"] is False and fin["stage_by_path"].startswith("git add ")
       and "run-summary.json" in fin["stage_by_path"] and " -A" not in fin["stage_by_path"],
       "finalize prints an explicit-path staging line")
    r = sh(["bash", "-c", fin["stage_by_path"]])
    ok(r.returncode == 0 and f"{LOOP}/feedback/run-summary.json" in git("diff", "--cached", "--name-only").stdout,
       "the staging line works against the allowlist without -f", r.stderr)
    r = py("feedback.py", "finalize", LOOP, draft)
    ok(r.returncode == 1 and "already filed" in r.stderr, "a filed report cannot be finalized twice")

    # ---------- a second report the same day ----------
    r = py("feedback.py", "quick", LOOP, "--date", "2026-09-26")
    ok(r.returncode == 0, "quick bundle files in one call", r.stderr)
    qk = json.loads(r.stdout)
    ok(os.path.basename(qk["report"]) == f"{PLUGIN}-{version}-2026-09-26-2.md"
       and qk["kind"] == "quick" and qk["items"] == 0,
       "a second report the same day gets its own name", r.stdout)
    qtext = open(os.path.join(repo, qk["report"])).read()
    ok("Quick bundle — no questions asked" in qtext and "## Defects" not in qtext
       and "Appendix A" in qtext, "the quick bundle is objective only")
    r = py("feedback.py", "scaffold", LOOP, "--date", "2026-09-26")
    d3 = os.path.join(repo, json.loads(r.stdout)["draft"])
    t3 = open(d3).read().replace("  - answer: _unanswered_", "  - answer: n/a")
    t3 = re.sub(r"(## Friction\n\n<!-- guide.*?-->\n)",
                lambda m: m.group(1) + "\n### Docs conflate two checks\nA sentence.\n", t3, flags=re.S)
    open(d3, "w").write(t3)
    r = py("feedback.py", "finalize", LOOP)
    ok(json.loads(r.stdout)["ids"] == [f"{pre}-4"],
       "item numbering continues across the day's reports (ids never collide)", r.stdout + r.stderr)

    # ---------- the drop never lands inside the host repo ----------
    r = py("feedback.py", "quick", LOOP, "--date", "2026-09-27",
           extra={"XDG_DATA_HOME": os.path.join(repo, ".local-share")})
    q2 = json.loads(r.stdout)
    ok(q2["drop"].startswith("~/.local/share/quiller/inbox/hostrepo/")
       and not os.path.exists(os.path.join(repo, ".local-share")),
       "an XDG_DATA_HOME inside the host repo is ignored", r.stdout + r.stderr)

    # ---------- maintainer ingest (repo checkout only) ----------
    ingest = os.path.join(REPO, "tools", "ingest_feedback.py")
    if os.path.exists(ingest):
        r = sh([sys.executable, ingest, "--dry-run"], cwd=td)
        ok(r.returncode == 0 and f"`{pre}-1`" in r.stdout and f"`{pre}-4`" in r.stdout,
           "ingest reads the drop and lists every item id", r.stdout[-2000:] + r.stderr)
        ok("| hostrepo |" in r.stdout and "**mismatch** (installed 0.0.1)" in r.stdout,
           "the digest flags the install mismatch before any claim")
        ok(f"`{pre}-2` — No repro for this one — _no repro; no evidence_" in r.stdout,
           "a defect without repro or evidence is flagged for triage")
        ok(any(l.startswith(f"| `{first}` |") and "**observed** — rounds.md row 1" in l
               and "n/a" in l for l in r.stdout.splitlines()),
           "watch answers are tabulated across bundles", r.stdout[:3000])
        ok("| `read-guard-denied` | 3 |" in r.stdout, "anomalies are grouped by code across bundles")
        info = json.loads(r.stderr.strip().splitlines()[-1])
        ok(info["dry_run"] and len(info["copied"]) == 3 and f"{pre}-3" in info["new_item_ids"],
           "dry run reports what it would copy and register", r.stderr)
        ok(not os.path.exists(os.path.join(REPO, "docs", "inbox", "hostrepo")),
           "dry run writes nothing into the repo")

    # ---------- archive carries feedback with its loop ----------
    git("commit", "-q", "-m", "conclusions")
    r = py("merge_ledger.py", "archive", LOOP, "20260926-000000-abc1234")
    ok(r.returncode == 0 and "feedback" in json.loads(r.stdout.splitlines()[0])["moved"],
       "archive moves feedback/ with the loop", r.stdout + r.stderr)
    adir = os.path.join(repo, LOOP, "archive", "20260926-000000-abc1234")
    ok(os.path.exists(os.path.join(adir, "feedback", "run-summary.json"))
       and not os.path.exists(os.path.join(repo, LOOP, "feedback", "run-summary.json")),
       "the run summary rides into the archive")
    r = py("feedback.py", "quick", LOOP, "--date", "2026-09-28", "--no-drop")
    ok(r.returncode == 0 and "/archive/20260926-000000-abc1234/feedback/" in json.loads(r.stdout)["report"],
       "feedback filed after archive reports on the newest archive", r.stdout + r.stderr)
    at = open(os.path.join(repo, json.loads(r.stdout)["report"])).read()
    ok("host: hostrepo" in at and "reporting on the newest archive" in at
       and "drop" not in json.loads(r.stdout),
       "…under the host's name, saying so; --no-drop copies nothing")

    # ---------- a loop bootstrapped by an older plugin ----------
    old = os.path.join(td, "oldhost")
    os.makedirs(os.path.join(old, LOOP))
    sh(["git", "init", "-q"], cwd=old)
    old_allow = re.sub(r" v\d+\.\d+\.\d+\.", " v0.12.0.", "\n".join(
        l for l in allow.splitlines() if "feedback" not in l)) + "\n"
    with open(os.path.join(old, LOOP, ".gitignore"), "w") as fh:
        fh.write(old_allow)
    with open(os.path.join(old, LOOP, "ledger.json"), "w") as fh:
        json.dump({"round": 0, "findings": []}, fh)
    r = py("feedback.py", "quick", LOOP, "--no-drop", cwd=old)
    res = json.loads(r.stdout)
    gi = open(os.path.join(old, LOOP, ".gitignore")).read()
    ok(r.returncode == 0 and res["git_ignored"] is False and "!**/feedback/*.md" in gi
       and f"{LOOP}/.gitignore" in res["stage_by_path"],
       "an older plugin-managed allowlist gains the feedback rules, and is staged",
       r.stdout + r.stderr)
    ok(not IS_QA or gi.rstrip().endswith("*.pyc"),
       "…inserted before the trailing re-exclusions")
    ok(any("verdict.json" in m for m in res["missing"]),
       "a loop with no verdict says which fields are missing")
    with open(os.path.join(old, LOOP, ".gitignore"), "w") as fh:
        fh.write("# the host's own rules\n*\n!.gitignore\n")
    r = py("feedback.py", "quick", LOOP, "--no-drop", "--date", "2026-01-02", cwd=old)
    res = json.loads(r.stdout)
    ok(res["git_ignored"] is True and "stage_by_path" not in res
       and open(os.path.join(old, LOOP, ".gitignore")).read().startswith("# the host's own")
       and any("not versioned" in w for w in res["warnings"]),
       "a host-owned .gitignore is never touched; the report says it is not versioned")

if __name__ == "__main__":
    main()
