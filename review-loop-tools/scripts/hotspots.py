#!/usr/bin/env python3
"""Hotspot map for cold reviews: where history says defects concentrate.

Usage: hotspots.py [repo-root] [--since 6.months] [--top 30]
Scores each tracked source file by commit churn x size x recency and prints
a markdown table (stdout) plus JSON on stderr. Stdlib + git only. Give this
to the reviewer so a cold review spends its reading budget where bugs live
instead of sweeping the tree uniformly.
"""
import json, math, os, subprocess, sys, time

SOURCE_EXT = {".swift", ".m", ".mm", ".ts", ".tsx", ".js", ".jsx", ".py",
              ".rb", ".go", ".rs", ".java", ".kt", ".c", ".cc", ".cpp",
              ".cs", ".php", ".vue", ".svelte"}

def main():
    args = sys.argv[1:]
    root, since, top = ".", "6.months", 30
    i = 0
    while i < len(args):
        if args[i] == "--since":
            since = args[i + 1]; i += 2
        elif args[i] == "--top":
            top = int(args[i + 1]); i += 2
        else:
            root = args[i]; i += 1
    root = os.path.abspath(root)
    log = subprocess.run(
        ["git", "-C", root, "log", f"--since={since}", "--format=%ct",
         "--name-only"], capture_output=True, text=True)
    if log.returncode != 0:
        print(f"hotspots: git log failed: {log.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    churn, last = {}, {}
    ts = None
    for line in log.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            ts = int(line)
            continue
        if os.path.splitext(line)[1].lower() in SOURCE_EXT:
            churn[line] = churn.get(line, 0) + 1
            last[line] = max(last.get(line, 0), ts or 0)
    now = time.time()
    rows = []
    for path, n in churn.items():
        full = os.path.join(root, path)
        if not os.path.exists(full):
            continue
        size_kb = os.path.getsize(full) / 1024
        days = (now - last[path]) / 86400
        score = n * (1 + math.log1p(size_kb)) / (1 + days / 90)
        rows.append({"path": path, "commits": n, "size_kb": round(size_kb, 1),
                     "days_since_change": int(days), "score": round(score, 2)})
    rows.sort(key=lambda r: -r["score"])
    rows = rows[:top]
    print(f"| # | File | Commits ({since}) | KB | Days since change | Score |")
    print("|---|---|---|---|---|---|")
    for k, r in enumerate(rows, 1):
        print(f"| {k} | `{r['path']}` | {r['commits']} | {r['size_kb']} | "
              f"{r['days_since_change']} | {r['score']} |")
    print(json.dumps({"hotspots": rows}), file=sys.stderr)

if __name__ == "__main__":
    main()
