#!/usr/bin/env python3
"""Manifest-driven mutation runner: makes "N/N mutants killed" checkable.

Usage: mutate.py <manifest.json> [--repo <root>]

Manifest:
{
  "test_cmd": "swift test",          # must exit non-zero when a mutant is caught
  "timeout": 600,                    # seconds per mutant (optional)
  "mutants": [
    {"id": "m1", "file": "Sources/X.swift",
     "original": "a < b", "replacement": "a <= b",
     "line": 42,                     # optional: restrict the match to this line
     "expect": "killed"}             # or "survived" (e.g. an equivalent mutant)
  ]
}

Each mutant is applied in an isolated `git worktree` of HEAD (never the
working tree — commit first), the test command runs there, the file is
restored, and the worktree is removed at the end. Text substitution keeps it
language-agnostic. Exit 1 if any mutant's outcome differs from "expect".
Output: JSON results on stdout.
"""
import json, os, shutil, subprocess, sys, tempfile

def die(msg, code=1):
    print(f"mutate: {msg}", file=sys.stderr)
    sys.exit(code)

def apply(path, original, replacement, line):
    """Apply one mutant. Returns (original_text, error)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if line:
        lines = text.split("\n")
        if line < 1 or line > len(lines):
            return None, f"line {line} out of range"
        if original not in lines[line - 1]:
            return None, f"original text not found on line {line}"
        lines[line - 1] = lines[line - 1].replace(original, replacement, 1)
        new = "\n".join(lines)
    else:
        n = text.count(original)
        if n != 1:
            return None, f"original text occurs {n} times (need exactly 1; add 'line')"
        new = text.replace(original, replacement, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    return text, ""

def main():
    if len(sys.argv) < 2:
        die("usage: mutate.py <manifest.json> [--repo <root>]", 2)
    manifest = json.load(open(sys.argv[1]))
    repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else "."
    top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        die("not a git repository")
    root = top.stdout.strip()
    test_cmd = manifest.get("test_cmd")
    if not test_cmd or not isinstance(manifest.get("mutants"), list):
        die("manifest needs test_cmd and a mutants array")
    timeout = int(manifest.get("timeout", 600))
    wt = tempfile.mkdtemp(prefix="mutate-")
    add = subprocess.run(["git", "-C", root, "worktree", "add", "--detach", wt, "HEAD"],
                         capture_output=True, text=True)
    if add.returncode != 0:
        shutil.rmtree(wt, ignore_errors=True)
        die(f"git worktree add failed: {add.stderr.strip()}")
    results, mismatches = [], 0
    try:
        for i, m in enumerate(manifest["mutants"]):
            mid = m.get("id", f"m{i + 1}")
            expect = m.get("expect", "killed")
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
                # same second): never let the test run write or trust them.
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
                run = subprocess.run(test_cmd, shell=True, cwd=wt, capture_output=True,
                                     text=True, timeout=timeout, env=env)
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
                            "expected": expect, "match": match, "tail": tail})
    finally:
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force", wt],
                       capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
    killed = sum(1 for r in results if r.get("outcome") == "killed")
    survived = sum(1 for r in results if r.get("outcome") == "survived")
    print(json.dumps({"killed": killed, "survived": survived,
                      "mismatches": mismatches, "results": results}, indent=2))
    sys.exit(1 if mismatches else 0)

if __name__ == "__main__":
    main()
