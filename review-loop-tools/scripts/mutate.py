#!/usr/bin/env python3
"""Manifest-driven mutation runner: makes "N/N mutants killed" checkable.

Usage: mutate.py <manifest.json> [--repo <root>] [--allow-dirty]

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
"""
import json, os, shutil, subprocess, sys, tempfile

def die(msg, code=1):
    print(f"mutate: {msg}", file=sys.stderr)
    sys.exit(code)

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
        die("usage: mutate.py <manifest.json> [--repo <root>]", 2)
    manifest = json.load(open(sys.argv[1]))
    repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else "."
    allow_dirty = "--allow-dirty" in sys.argv
    top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        die("not a git repository")
    root = top.stdout.strip()
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
    files = sorted({m["file"] for m in manifest["mutants"] if m.get("file")})
    st = subprocess.run(["git", "-C", root, "status", "--porcelain", "--"] + files,
                        capture_output=True, text=True)
    dirty = [l for l in st.stdout.splitlines() if l.strip()]
    if dirty and not allow_dirty:
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
                print("=" * 60, file=sys.stderr)
                print(f"mutate: BASELINE RED for test_cmd {cmd!r} (exit "
                      f"{baselines[cmd]}) — the unmutated tree does not pass "
                      f"this gate, or the command matches nothing, so no kill "
                      f"count from it can be trusted. Nothing was run.\n{tail}",
                      file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print(json.dumps({"killed": 0, "survived": 0, "errors": 0,
                                  "mismatches": 0, "baseline_red": cmd,
                                  "results": []}, indent=2))
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
                            **({"test_cmd": cmd} if cmd != test_cmd else {})})
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
    print(json.dumps({"killed": killed, "survived": survived, "errors": errors,
                      "mismatches": mismatches, "results": results}, indent=2))
    sys.exit(1 if (mismatches or errors) else 0)

if __name__ == "__main__":
    main()
