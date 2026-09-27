#!/usr/bin/env python3
"""Self-test for mutate.py's run modes. Hermetic: a tempdir git repo with a
two-function module, a test script, and a fake plugin-cache version tree
built from copies of the real scripts. Exits nonzero on the first failure.

Covers the 0.16.0 field fixes (the 2026-09-20 weatherapp report):
- `--only` runs a subset of the NAMED manifest; an unknown id is an error
  before anything runs (five runs in one loop were split by hand into
  scratch copies).
- `--detach` + `wait`: the summary a foreground run prints, the run's own
  exit status, exit 3 while still running, a results file that a refusal
  still ENDS, and an error — not a spin — when no run exists.
- a STALE copy refuses when a newer version is installed beside it (two
  implementers ran the 0.13.0 copy under 0.14.0); --allow-stale overrides;
  the newest copy and a development checkout run.
- every result carries elapsed_s.
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "scripts"))

PASS = 0
def ok(cond, label, detail=""):
    global PASS
    if not cond:
        print(f"FAIL: {label}\n{detail}", file=sys.stderr)
        sys.exit(1)
    PASS += 1
    print(f"ok: {label}")

def main():
    td = os.path.realpath(tempfile.mkdtemp(prefix="mutate-selftest-"))
    try:
        run(td)
        print(f"\nALL {PASS} CHECKS PASSED")
    finally:
        shutil.rmtree(td, ignore_errors=True)

def run(td):
    repo = os.path.join(td, "repo")
    os.makedirs(repo)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", FIELD_LOG_OFF="1")
    def sh(cmd, cwd=repo):
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)
    def mutate(*args, script=os.path.join(SCRIPTS, "mutate.py")):
        return sh([sys.executable, script] + list(args))
    sh(["git", "init", "-q"])
    sh(["git", "config", "user.email", "selftest@example.invalid"])
    sh(["git", "config", "user.name", "selftest"])
    with open(os.path.join(repo, "m.py"), "w") as fh:
        fh.write("def f(x):\n    return x + 1\n\ndef g(x):\n    return x * 2\n")
    with open(os.path.join(repo, "t.py"), "w") as fh:
        fh.write("import m, sys, time\n"
                 "time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 0)\n"
                 "assert m.f(1) == 2 and m.g(2) == 4\n")
    def manifest(test_cmd):
        with open(os.path.join(repo, "man.json"), "w") as fh:
            json.dump({"test_cmd": test_cmd, "mutants": [
                {"id": "a", "file": "m.py", "original": "x + 1", "replacement": "x + 2"},
                {"id": "b", "file": "m.py", "original": "x * 2", "replacement": "x * 3"},
                {"id": "c", "file": "m.py", "original": "x * 2", "replacement": "x * 2.0",
                 "expect": "survived"}]}, fh)
    manifest(f"{sys.executable} t.py")
    sh(["git", "add", "m.py", "t.py"])
    sh(["git", "commit", "-q", "-m", "init"])

    # ---------- foreground, and --only ----------
    r = mutate("man.json")
    d = json.loads(r.stdout)
    ok(r.returncode == 0 and (d["killed"], d["survived"], d["mismatches"]) == (2, 1, 0),
       "a full run reports 2 killed, 1 survived as expected", r.stderr)
    ok(all(isinstance(x.get("elapsed_s"), float) for x in d["results"])
       and isinstance(d["elapsed_s"], float) and "only" not in d,
       "every result, and the run, carries elapsed_s")
    ok(not os.path.exists(os.path.join(repo, "man.json.results.json")),
       "a foreground run writes no results file")
    r = mutate("man.json", "--only", "b,c")
    d = json.loads(r.stdout)
    ok(r.returncode == 0 and [x["id"] for x in d["results"]] == ["b", "c"]
       and d["only"] == ["b", "c"], "--only runs the named subset", r.stderr)
    before = open(os.path.join(repo, "man.json")).read()
    r = mutate("man.json", "--only", "b,z")
    ok(r.returncode == 2 and "['z']" in r.stderr and r.stdout.strip() == "",
       "--only with an unknown id is refused before anything runs", r.stderr)
    ok(open(os.path.join(repo, "man.json")).read() == before
       and sorted(os.listdir(repo)) == [".git", "m.py", "man.json", "t.py"],
       "the manifest is untouched and no scratch copy was made")

    # ---------- detach + wait ----------
    r = mutate("man.json", "--detach")
    d = json.loads(r.stdout)
    ok(r.returncode == 0 and d["detached"] and d["results"] == "man.json.results.json",
       "--detach returns at once with the results path", r.stderr)
    r = mutate("wait", "man.json")
    d = json.loads(r.stdout)
    ok(r.returncode == 0 and (d["killed"], d["survived"]) == (2, 1) and d["total"] == 3
       and "pid" not in d and "done" not in d,
       "wait prints the run's summary and exits with its status", r.stdout + r.stderr)
    manifest(f"{sys.executable} t.py 1.5")
    mutate("man.json", "--detach")
    r = mutate("wait", "man.json", "--timeout", "1")
    ok(r.returncode == 3 and json.loads(r.stdout)["done"] is False,
       "wait exits 3 while the run is still going", r.stdout + r.stderr)
    r = mutate("wait", "man.json")
    ok(r.returncode == 0 and json.loads(r.stdout)["killed"] == 2,
       "a second wait collects the finished run")
    # A mismatch must come back as exit 1 through wait.
    with open(os.path.join(repo, "man.json"), "w") as fh:
        json.dump({"test_cmd": f"{sys.executable} t.py", "mutants": [
            {"id": "a", "file": "m.py", "original": "x + 1", "replacement": "x + 1.0"}]}, fh)
    mutate("man.json", "--detach")
    r = mutate("wait", "man.json")
    ok(r.returncode == 1 and json.loads(r.stdout)["mismatches"] == 1,
       "a surviving mutant expected killed comes back as exit 1 through wait", r.stdout)
    # A refusal must END the results file.
    manifest(f"{sys.executable} t.py")
    with open(os.path.join(repo, "m.py"), "a") as fh:
        fh.write("# uncommitted\n")
    mutate("man.json", "--detach")
    r = mutate("wait", "man.json", "--timeout", "20")
    ok(r.returncode == 2 and "uncommitted changes" in json.loads(r.stdout)["error"]
       and "DIRTY" in r.stderr,
       "a detached run that refuses ends its results file; wait relays why",
       r.stdout + r.stderr)
    sh(["git", "checkout", "-q", "m.py"])
    for n in ("man.json.results.json", "man.json.results.log"):
        os.remove(os.path.join(repo, n))
    r = mutate("wait", "man.json")
    ok(r.returncode == 2 and "no detached run" in r.stderr,
       "wait with no run is an error, not a spin")
    # A stale results file must never satisfy the next wait.
    with open(os.path.join(repo, "man.json.results.json"), "w") as fh:
        json.dump({"done": True, "exit": 0, "killed": 99, "results": []}, fh)
    mutate("man.json", "--detach")
    r = mutate("wait", "man.json")
    ok(json.loads(r.stdout)["killed"] == 2, "--detach clears a stale results file first")

    # ---------- stale copies ----------
    cache = os.path.join(td, "cache", "review-loop-tools")
    for v in ("0.15.0", "0.16.0", "0.9.0"):
        shutil.copytree(SCRIPTS, os.path.join(cache, v, "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
    old = os.path.join(cache, "0.15.0", "scripts", "mutate.py")
    new = os.path.join(cache, "0.16.0", "scripts", "mutate.py")
    r = mutate("man.json", script=old)
    ok(r.returncode == 2 and "0.15.0 copy" in r.stderr and new in r.stderr
       and r.stdout.strip() == "",
       "a stale copy refuses and names the newer path", r.stderr)
    r = mutate("man.json", "--detach", script=old)
    ok(r.returncode == 2 and "detached" not in r.stdout,
       "…in the foreground, before it detaches", r.stdout + r.stderr)
    r = mutate("man.json", "--allow-stale", "--only", "a", script=old)
    ok(r.returncode == 0 and json.loads(r.stdout)["killed"] == 1, "--allow-stale overrides")
    r = mutate("man.json", "--only", "a", script=new)
    ok(r.returncode == 0, "the newest installed copy runs (0.9.0 beside it is older: 9 < 16)",
       r.stderr)
    r = mutate("man.json", "--only", "a")
    ok(r.returncode == 0, "a development checkout (directory not named by version) runs")

if __name__ == "__main__":
    main()
