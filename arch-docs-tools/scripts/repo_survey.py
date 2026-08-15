#!/usr/bin/env python3
"""Survey a repository: size, language mix, and buildable units.

Usage: repo_survey.py [root]
Prints JSON: totals, a per-top-level-dir breakdown, and detected project
manifests — the raw material for the deliverable-split decision.
"""
import json, os, sys

EXCLUDE = {".git", "node_modules", "Pods", "Carthage", "build", ".build",
           "dist", "out", "vendor", "DerivedData", ".next", ".venv", "venv",
           "__pycache__", ".qa-loop", ".review-loop", "coverage", "target"}
SOURCE_EXT = {".swift", ".m", ".mm", ".h", ".ts", ".tsx", ".js", ".jsx",
              ".py", ".rb", ".go", ".rs", ".java", ".kt", ".c", ".cc",
              ".cpp", ".cs", ".php", ".vue", ".svelte", ".sql", ".sh",
              ".css", ".scss", ".html"}
MANIFESTS = {"package.json": "node", "pyproject.toml": "python",
             "setup.py": "python", "go.mod": "go", "Cargo.toml": "rust",
             "Package.swift": "swift-package", "pom.xml": "maven",
             "build.gradle": "gradle", "build.gradle.kts": "gradle",
             "Gemfile": "ruby", "composer.json": "php",
             "CMakeLists.txt": "cmake"}

def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    by_dir, manifests = {}, []
    total_files = total_loc = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE and not d.startswith(".")]
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        top = "." if rel == "." else rel.split(os.sep)[0]
        # Xcode projects are directories; record and don't descend.
        for d in list(dirnames):
            if d.endswith((".xcodeproj", ".xcworkspace")) and depth <= 3:
                manifests.append({"path": os.path.relpath(
                    os.path.join(dirpath, d), root), "kind": "xcode"})
                dirnames.remove(d)
        for name in filenames:
            path = os.path.join(dirpath, name)
            relpath = os.path.relpath(path, root)
            if name in MANIFESTS and depth <= 3:
                manifests.append({"path": relpath, "kind": MANIFESTS[name]})
            ext = os.path.splitext(name)[1].lower()
            if ext in SOURCE_EXT:
                try:
                    with open(path, "rb") as fh:
                        loc = sum(1 for _ in fh)
                except OSError:
                    continue
                d = by_dir.setdefault(top, {"files": 0, "loc": 0,
                                            "languages": {}})
                d["files"] += 1
                d["loc"] += loc
                d["languages"][ext] = d["languages"].get(ext, 0) + loc
                total_files += 1
                total_loc += loc
    print(json.dumps({"root": root, "total_files": total_files,
                      "total_loc": total_loc, "by_top_dir": by_dir,
                      "manifests": manifests}, indent=2))

if __name__ == "__main__":
    main()
