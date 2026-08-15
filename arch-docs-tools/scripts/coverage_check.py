#!/usr/bin/env python3
"""Cross-check an architecture docs folder against the actual source tree.

Usage: coverage_check.py <docs-dir> <src-root>
Reports source files never mentioned (by relative path or basename) in any
doc, largest first — advisory input for the module-inventory completeness
pass. Always exits 0; the orchestrator judges the gaps.
"""
import json, os, sys

EXCLUDE = {".git", "node_modules", "Pods", "Carthage", "build", ".build",
           "dist", "out", "vendor", "DerivedData", ".next", ".venv", "venv",
           "__pycache__", ".qa-loop", ".review-loop", "coverage", "target"}
SOURCE_EXT = {".swift", ".m", ".mm", ".ts", ".tsx", ".js", ".jsx", ".py",
              ".rb", ".go", ".rs", ".java", ".kt", ".c", ".cc", ".cpp",
              ".cs", ".php", ".vue", ".svelte"}

def main():
    if len(sys.argv) != 3:
        print("usage: coverage_check.py <docs-dir> <src-root>",
              file=sys.stderr)
        sys.exit(2)
    docs_dir, root = sys.argv[1], os.path.abspath(sys.argv[2])
    text = ""
    for dp, _, fn in os.walk(docs_dir):
        for n in fn:
            if n.endswith(".md"):
                with open(os.path.join(dp, n), encoding="utf-8",
                          errors="ignore") as fh:
                    text += fh.read()
    total = mentioned = 0
    missing = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in EXCLUDE and not d.startswith(".")]
        for n in fn:
            if os.path.splitext(n)[1].lower() not in SOURCE_EXT:
                continue
            path = os.path.join(dp, n)
            rel = os.path.relpath(path, root)
            total += 1
            if rel in text or n in text:
                mentioned += 1
            else:
                try:
                    with open(path, "rb") as fh:
                        loc = sum(1 for _ in fh)
                except OSError:
                    loc = 0
                missing.append((loc, rel))
    missing.sort(reverse=True)
    print(json.dumps({
        "source_files": total, "mentioned": mentioned,
        "unmentioned": len(missing),
        "top_unmentioned": [{"path": p, "loc": l} for l, p in missing[:25]],
    }, indent=2))

if __name__ == "__main__":
    main()
