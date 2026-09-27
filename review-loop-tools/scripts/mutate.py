#!/usr/bin/env python3
"""Manifest-driven mutation runner: makes "N/N mutants killed" checkable.

Usage:
  mutate.py <manifest.json> [--repo <root>] [--only id1,id2] [--detach]
                            [--allow-dirty] [--allow-stale]
  mutate.py wait <manifest.json> [--timeout <s>]

Manifest:
{
  "test_cmd": "swift test",          # must exit non-zero when a mutant is caught
  "timeout": 600,                    # seconds per mutant (optional)
  "mutants": [
    {"id": "m1", "file": "Sources/X.swift",
     "original": "a < b", "replacement": "a <= b",
     "line": 42,                     # optional: restrict the match to this line
     "test_cmd": "…",                # optional: this mutant's own gate (UI mutants
                                     #   pay the UI suite; unit mutants do not)
     "expect": "killed"}             # or "survived" (e.g. an equivalent mutant)
    # "replacement": "" is valid and DELETES the matched line.
  ]
}

Each mutant is applied in an isolated `git worktree` of HEAD (never the
working tree — commit first), the test command runs there, the file is
restored, and the worktree is removed at the end. Text substitution keeps it
language-agnostic. Exit 1 if any mutant's outcome differs from "expect".
Output: JSON results on stdout.

Two guards make the kill count mean something (both measured in the field):
- BASELINE: every distinct test_cmd runs once UNMUTATED first and must exit
  0 — a filter pipeline that matched nothing under `-quiet` made grep exit
  1 and reported every mutant "killed".
- DIRTY TREE: the worktree is cut from HEAD, so uncommitted changes to the
  manifest's files are NOT under test — a pre-commit run reported every
  mutant "survived" against the old code. Refused unless --allow-dirty.

Long manifests and the 10-minute command ceiling (measured: five mutation
runs in one loop were each split by hand into scratch copies of the
manifest, at ~2 minutes per xcodebuild mutant):
- `--only id1,id2` runs a SUBSET of the named manifest. No copy is made —
  the manifest stays the artifact of record. An id the manifest does not
  hold is an error before anything runs.
- `--detach` starts the run in its own session and returns at once;
  `mutate.py wait <manifest>` blocks until it finishes (default 540 s, under
  the ceiling) and prints the same JSON a foreground run prints, exiting
  with the run's own status. Exit 3 = still running, call `wait` again.
  Results are written to `<manifest>.results.json` as each mutant
  finishes, so a run that dies keeps what it measured.

STALE COPY: refused when a HIGHER version of this plugin sits beside this
one in the plugin cache (measured: two implementers searched for mutate.py
and ran the 0.13.0 copy under 0.14.0 — no baseline run, per-mutant
test_cmd ignored). Run the path named in your brief or dispatch;
--allow-stale overrides deliberately.
"""
import contextlib, json, os, re, shutil, subprocess, sys, tempfile, time

VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
LAST_ERROR = ""
RESULTS = {"path": None, "state": None}

def vkey(v):
    return tuple(int(x) for x in v.split("."))

def newer_sibling():
    """(own version, newer version, its mutate.py) when a higher version of
    this plugin is installed beside this copy; None otherwise — including
    in a development checkout, whose directory is not named by version."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    own, parent = os.path.basename(root), os.path.dirname(root)
    if not VERSION_RE.fullmatch(own):
        return None
    best = None
    try:
        names = os.listdir(parent)
    except OSError:
        return None
    for name in names:
        if VERSION_RE.fullmatch(name) and vkey(name) > vkey(own) and os.path.exists(
                os.path.join(parent, name, "scripts", "mutate.py")):
            if best is None or vkey(name) > vkey(best):
                best = name
    if not best:
        return None
    return own, best, os.path.join(parent, best, "scripts", "mutate.py")

def results_path(manifest):
    return manifest + ".results.json"

def save_results(**kw):
    """Persist progress for `wait` (detached runs only). Atomic replace: a
    reader never sees half a file."""
    if not RESULTS["path"]:
        return
    RESULTS["state"].update(kw)
    tmp = RESULTS["path"] + ".partial"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(RESULTS["state"], fh, indent=2)
        fh.write("\n")
    os.replace(tmp, RESULTS["path"])

def note_anomaly(root, code, detail):
    """Telemetry for the run summary — only when a review loop lives in this
    repo; never raises, never changes the exit path."""
    try:
        loop = os.path.join(root, ".review-loop")
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import field_log
        field_log.anomaly(loop, code, detail, source="mutate.py")
    except Exception:
        pass

def die(msg, code=1):
    global LAST_ERROR
    LAST_ERROR = msg
    print(f"mutate: {msg}", file=sys.stderr)
    sys.exit(code)

def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, TypeError):
        return True

def wait(args):
    """`wait <manifest> [--timeout s]`: block until a detached run of this
    manifest finishes, print its summary, and exit with ITS status. Exit 3
    when it is still running at the timeout — call wait again."""
    pos, timeout = [], 540.0
    it = iter(args)
    for a in it:
        if a == "--timeout":
            timeout = float(next(it, "540"))
        elif a.startswith("--timeout="):
            timeout = float(a.split("=", 1)[1])
        else:
            pos.append(a)
    if not pos:
        die("usage: mutate.py wait <manifest.json> [--timeout <s>]", 2)
    rpath = results_path(pos[0])
    log = rpath[:-len(".json")] + ".log"
    deadline = time.monotonic() + timeout
    while True:
        state = None
        with contextlib.suppress(OSError, ValueError):
            with open(rpath, encoding="utf-8") as fh:
                state = json.load(fh)
        if state is None and not os.path.exists(log):
            die(f"no detached run for {pos[0]} (no {rpath}) — start one with "
                f"`mutate.py {pos[0]} --detach`", 2)
        if state and state.get("done"):
            code = int(state.get("exit", 1))
            out = {k: v for k, v in state.items() if k not in ("done", "pid", "started", "exit")}
            print(json.dumps(out, indent=2))
            if code:
                with contextlib.suppress(OSError):
                    with open(log, encoding="utf-8", errors="replace") as fh:
                        tail = fh.read()[-1500:].strip()
                    if tail:
                        print(tail, file=sys.stderr)
            sys.exit(code)
        if state and state.get("pid") and not alive(state["pid"]):
            die(f"the detached run died without finishing ({len(state.get('results', []))} "
                f"of {state.get('total', '?')} mutants recorded in {rpath}); see {log}", 1)
        if time.monotonic() >= deadline:
            done = len((state or {}).get("results", []))
            print(json.dumps({"done": False, "completed": done,
                              "total": (state or {}).get("total"),
                              "next": f"mutate.py wait {pos[0]}"}))
            sys.exit(3)
        time.sleep(2)

def apply(path, original, replacement, line):
    """Apply one mutant. Returns (original_text, error). An EMPTY replacement
    ("") deletes the whole line holding the match — the most natural mutant.
    It used to be rejected as a missing field, and a field implementer's
    manifest died on exactly that."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if line:
        lines = text.split("\n")
        if line < 1 or line > len(lines):
            return None, f"line {line} out of range"
        if original not in lines[line - 1]:
            return None, f"original text not found on line {line}"
        if replacement == "":
            del lines[line - 1]
        else:
            lines[line - 1] = lines[line - 1].replace(original, replacement, 1)
        new = "\n".join(lines)
    else:
        n = text.count(original)
        if n != 1:
            return None, f"original text occurs {n} times (need exactly 1; add 'line')"
        if replacement == "" and "\n" not in original:
            lines = text.split("\n")
            idx = next(i for i, l in enumerate(lines) if original in l)
            del lines[idx]
            new = "\n".join(lines)
        else:
            new = text.replace(original, replacement, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    return text, ""

def main():
    if len(sys.argv) < 2:
        die("usage: mutate.py <manifest.json> [--repo <root>] [--only id1,id2] "
            "[--detach] | mutate.py wait <manifest.json>", 2)
    if sys.argv[1] == "wait":
        wait(sys.argv[2:])
        return
    mpath = sys.argv[1]
    def opt(name):
        if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv):
            return sys.argv[sys.argv.index(name) + 1]
        for a in sys.argv:
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
        return None
    repo = opt("--repo") or "."
    allow_dirty = "--allow-dirty" in sys.argv
    top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        die("not a git repository")
    root = top.stdout.strip()
    stale = newer_sibling()
    if stale and "--allow-stale" not in sys.argv:
        note_anomaly(root, "mutate-stale-refused",
                     f"mutate.py {stale[0]} was run while {stale[1]} is installed")
        die(f"this is the {stale[0]} copy of mutate.py and {stale[1]} is installed "
            f"beside it — older copies lack guards the loop relies on. Run "
            f"{stale[2]} (the path your brief or dispatch names); never search "
            f"the plugin cache for a script. --allow-stale overrides deliberately", 2)
    if "--detach" in sys.argv:
        # Re-exec without --detach in a new session; the results file is
        # the contract, stdout/stderr go to a log next to it.
        rpath = results_path(mpath)
        for stale_file in (rpath, rpath + ".partial"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(stale_file)   # a stale result must never satisfy `wait`
        log = rpath[:-len(".json")] + ".log"
        child = [sys.executable, os.path.abspath(__file__)] + \
                [a for a in sys.argv[1:] if a != "--detach"] + ["--results", rpath]
        with open(log, "w") as lf:
            p = subprocess.Popen(child, stdout=lf, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        print(json.dumps({"detached": True, "pid": p.pid, "results": rpath, "log": log,
                          "next": f"mutate.py wait {mpath}"}))
        return
    if opt("--results"):
        RESULTS["path"] = opt("--results")
        RESULTS["state"] = {"done": False, "pid": os.getpid(),
                            "started": round(time.time(), 1), "results": []}
        save_results()
    try:
        manifest = json.load(open(mpath))
    except (OSError, ValueError) as e:
        die(f"cannot read manifest {mpath}: {e}", 2)
    test_cmd = manifest.get("test_cmd")
    if not test_cmd or not isinstance(manifest.get("mutants"), list):
        die("manifest needs test_cmd and a mutants array")
    # Parse-time validation: a bad manifest must fail LOUDLY before anything
    # runs. Silent under-verification launders a guess into a claim
    # (measured: an unsatisfiable mutant errored and the round still
    # reported 8/8 killed).
    config_errors = []
    for i, m in enumerate(manifest["mutants"]):
        mid = m.get("id", f"m{i + 1}")
        for k in ("file", "original"):
            if not m.get(k):
                config_errors.append(f"{mid}: missing '{k}'")
        # replacement must be PRESENT, but "" is valid: it deletes the
        # matched line (missing and empty are different claims).
        if not isinstance(m.get("replacement"), str):
            config_errors.append(f"{mid}: missing 'replacement' (a string; "
                                 f"\"\" is valid and means delete the matched line)")
        if m.get("expect", "killed") not in ("killed", "survived"):
            config_errors.append(f"{mid}: expect must be killed|survived")
        if "\n" in (m.get("original") or "") and m.get("line"):
            config_errors.append(f"{mid}: multi-line 'original' with a 'line' key is "
                                 f"unsatisfiable by construction (matching is per-line) — "
                                 f"drop 'line' or use a single-line original")
    for i, m in enumerate(manifest["mutants"]):
        tc = m.get("test_cmd", test_cmd)
        if not isinstance(tc, str) or not tc.strip():
            config_errors.append(f"{m.get('id', f'm{i + 1}')}: test_cmd must be a non-empty string")
    if config_errors:
        for e in config_errors:
            print(f"mutate: MANIFEST ERROR — {e}", file=sys.stderr)
        die(f"{len(config_errors)} manifest error(s); nothing was run", 2)
    only = opt("--only")
    if only is not None:
        want = [x.strip() for x in only.split(",") if x.strip()]
        have = [m.get("id", f"m{i + 1}") for i, m in enumerate(manifest["mutants"])]
        missing = [w for w in want if w not in have]
        if not want or missing:
            die(f"--only names mutant id(s) not in the manifest: {missing or '(none given)'}"
                f" — it holds: {', '.join(have)}", 2)
        # The WHOLE manifest was validated above; the subset is what runs.
        for i, m in enumerate(manifest["mutants"]):
            m.setdefault("id", f"m{i + 1}")
        manifest["mutants"] = [m for m in manifest["mutants"] if m["id"] in want]
    save_results(total=len(manifest["mutants"]))
    started = time.monotonic()
    files = sorted({m["file"] for m in manifest["mutants"] if m.get("file")})
    st = subprocess.run(["git", "-C", root, "status", "--porcelain", "--"] + files,
                        capture_output=True, text=True)
    dirty = [l for l in st.stdout.splitlines() if l.strip()]
    if dirty and allow_dirty:
        note_anomaly(root, "mutate-allow-dirty",
                     f"--allow-dirty over {len(dirty)} uncommitted manifest file(s)")
    if dirty and not allow_dirty:
        note_anomaly(root, "mutate-dirty-refused",
                     f"{len(dirty)} manifest file(s) had uncommitted changes")
        for l in dirty:
            print(f"mutate: DIRTY — {l}", file=sys.stderr)
        die("uncommitted changes to the manifest's files: the worktree is cut "
            "from HEAD and would test the OLD code (every mutant 'survives'). "
            "Commit first, then run; --allow-dirty overrides deliberately", 2)
    timeout = int(manifest.get("timeout", 600))
    wt = tempfile.mkdtemp(prefix="mutate-")
    add = subprocess.run(["git", "-C", root, "worktree", "add", "--detach", wt, "HEAD"],
                         capture_output=True, text=True)
    if add.returncode != 0:
        shutil.rmtree(wt, ignore_errors=True)
        die(f"git worktree add failed: {add.stderr.strip()}")
    results, mismatches = [], 0
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    def run_tests(cmd):
        # pipefail: a piped test_cmd (e.g. `swift test | grep …`) must
        # not report the filter's exit status as the suite's.
        return subprocess.run("set -o pipefail; " + cmd, shell=True,
                              executable="/bin/bash", cwd=wt,
                              capture_output=True, text=True,
                              timeout=timeout, env=env)
    try:
        # BASELINE: each distinct gate must be GREEN unmutated, or "killed"
        # measures the gate, not the mutant.
        baselines = {}
        for cmd in dict.fromkeys(m.get("test_cmd", test_cmd) for m in manifest["mutants"]):
            try:
                b = run_tests(cmd)
                baselines[cmd] = b.returncode
                tail = (b.stdout + b.stderr)[-400:].strip()
            except subprocess.TimeoutExpired:
                baselines[cmd] = "timeout"
                tail = "timeout"
            if baselines[cmd] != 0:
                note_anomaly(root, "mutate-baseline-red",
                             f"a test_cmd exited {baselines[cmd]} on the unmutated tree")
                print("=" * 60, file=sys.stderr)
                print(f"mutate: BASELINE RED for test_cmd {cmd!r} (exit "
                      f"{baselines[cmd]}) — the unmutated tree does not pass "
                      f"this gate, or the command matches nothing, so no kill "
                      f"count from it can be trusted. Nothing was run.\n{tail}",
                      file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                red = {"killed": 0, "survived": 0, "errors": 0,
                       "mismatches": 0, "baseline_red": cmd, "results": []}
                save_results(done=True, exit=2, **red)
                print(json.dumps(red, indent=2))
                sys.exit(2)
        for i, m in enumerate(manifest["mutants"]):
            mid = m.get("id", f"m{i + 1}")
            expect = m.get("expect", "killed")
            cmd = m.get("test_cmd", test_cmd)
            path = os.path.join(wt, m["file"])
            if not os.path.exists(path):
                results.append({"id": mid, "outcome": "error", "note": "file not found"})
                mismatches += 1
                continue
            saved, note = apply(path, m["original"], m["replacement"], m.get("line"))
            if saved is None:
                results.append({"id": mid, "outcome": "error", "note": note})
                mismatches += 1
                continue
            t0 = time.monotonic()
            try:
                # Stale bytecode caches can mask a restored file (same size,
                # same second): never let the test run write or trust them
                # (PYTHONDONTWRITEBYTECODE in env above).
                run = run_tests(cmd)
                outcome = "killed" if run.returncode != 0 else "survived"
                tail = (run.stdout + run.stderr)[-400:].strip()
            except subprocess.TimeoutExpired:
                outcome, tail = "killed", "timeout (treated as killed)"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(saved)   # restore before the next mutant
            match = outcome == expect
            if not match:
                mismatches += 1
            results.append({"id": mid, "file": m["file"], "outcome": outcome,
                            "expected": expect, "match": match, "tail": tail,
                            "elapsed_s": round(time.monotonic() - t0, 1),
                            **({"test_cmd": cmd} if cmd != test_cmd else {})})
            save_results(results=results)
    finally:
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force", wt],
                       capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
    killed = sum(1 for r in results if r.get("outcome") == "killed")
    survived = sum(1 for r in results if r.get("outcome") == "survived")
    errors = sum(1 for r in results if r.get("outcome") == "error")
    if errors:
        print("=" * 60, file=sys.stderr)
        print(f"mutate: {errors} MUTANT(S) ERRORED — the kill count is NOT "
              f"trustworthy. Treat this run as unverified.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
    summary = {"killed": killed, "survived": survived, "errors": errors,
               "mismatches": mismatches,
               "elapsed_s": round(time.monotonic() - started, 1),
               **({"only": [m["id"] for m in manifest["mutants"]]} if only is not None else {}),
               "results": results}
    code = 1 if (mismatches or errors) else 0
    save_results(done=True, exit=code, **summary)
    print(json.dumps(summary, indent=2))
    sys.exit(code)

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # A detached run that refuses or dies must still END its results
        # file, or `wait` would spin until its timeout on a finished run.
        st = RESULTS["state"]
        if RESULTS["path"] and st is not None and not st.get("done"):
            code = e.code if isinstance(e.code, int) else 1
            with contextlib.suppress(Exception):
                save_results(done=True, exit=code, error=LAST_ERROR or "see the log")
        raise
    except Exception as e:
        if RESULTS["path"] and RESULTS["state"] is not None:
            with contextlib.suppress(Exception):
                save_results(done=True, exit=1, error=f"{type(e).__name__}: {e}"[:300])
        raise
