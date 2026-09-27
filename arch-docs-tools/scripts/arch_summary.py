#!/usr/bin/env python3
"""The objective half of an arch-docs field report.

Usage:
  arch_summary.py start <docs-dir>
  arch_summary.py write <docs-dir> [--print]

start  records when the run began (<docs-dir>/feedback/run.json) — the
       skill calls it at Stage 1, so the token measurement has a window.
write  re-runs the three validation scripts against the finished docs and
       writes <docs-dir>/feedback/run-summary.json: plugin version (read
       from this script's own plugin.json — the code that ran), platform,
       survey totals, the deliverable split that was chosen, diagram counts
       per document, lint and coverage numbers, anomalies.

Counts and document names only: no source paths, no document text. The
summary leaves the host repo inside a field report.
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import field_log      # noqa: E402
import run_summary    # noqa: E402  (plugin identity and platform probes)

SCHEMA = 1

def repo_root(d):
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return os.path.abspath(".")

def git_state(root, docs_dir):
    def git(*a):
        try:
            return subprocess.run(["git", "-C", root] + list(a), capture_output=True,
                                  text=True, timeout=20)
        except Exception:
            return None
    inside = git("rev-parse", "--is-inside-work-tree")
    if not inside or inside.returncode != 0:
        return {"git_repo": False}
    ign = git("check-ignore", "-q", os.path.abspath(docs_dir))
    return {"git_repo": True, "loop_dir_ignored": bool(ign and ign.returncode == 0)}

def run_json(script, args, cwd=None):
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                           capture_output=True, text=True, timeout=300, cwd=cwd)
        return json.loads(r.stdout)
    except Exception:
        return None

def docs_in(docs_dir):
    out = []
    try:
        names = sorted(n for n in os.listdir(docs_dir) if n.endswith(".md"))
    except OSError:
        return out
    for n in names:
        p = os.path.join(docs_dir, n)
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        kinds = {}
        for m in re.finditer(r"^```mermaid[^\n]*\n\s*([A-Za-z0-9-]+)", text, re.M):
            kinds[m.group(1)] = kinds.get(m.group(1), 0) + 1
        out.append({"file": n, "bytes": len(text.encode("utf-8")),
                    "lines": text.count("\n") + 1,
                    "diagrams": sum(kinds.values()), "diagram_kinds": kinds,
                    "not_covered_appendix": bool(re.search(r"(?im)^#+\s*not covered", text)),
                    "inference_labels": len(re.findall(r"\bInference:", text)),
                    "mtime": os.path.getmtime(p)})
    return out

def lint(docs_dir, docs):
    files = [os.path.join(docs_dir, d["file"]) for d in docs]
    if not files:
        return {"ran": False}
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "mermaid_lint.py")] + files,
                           capture_output=True, text=True, timeout=120)
    except Exception:
        return {"ran": False}
    issues = [l for l in r.stdout.splitlines() if l.strip()]
    m = re.search(r"(\d+) block\(s\)", r.stderr)
    # Issue KINDS, not lines: a lint line quotes the document.
    kinds = {}
    for l in issues:
        k = l.split(": ", 1)[-1]
        k = re.sub(r"[`'\"].*", "", k).strip()[:60] or "other"
        kinds[k] = kinds.get(k, 0) + 1
    return {"ran": True, "blocks": int(m.group(1)) if m else None,
            "issues": len(issues), "by_kind": kinds}

def build(docs_dir, stop_note=""):
    docs_dir = docs_dir.rstrip("/") or docs_dir
    root = repo_root(docs_dir)
    plugin = run_summary.plugin_identity()
    docs = docs_in(docs_dir)
    fdir = os.path.join(docs_dir, "feedback")
    started = (run_summary.load_json(os.path.join(fdir, "run.json"), {}) or {}).get("started_ts")
    missing = []
    basis = "feedback/run.json"
    if not isinstance(started, (int, float)):
        # No start marker (an older plugin): the oldest document written in
        # the newest document's twelve hours is the best available bound.
        newest = max([d["mtime"] for d in docs], default=None)
        recent = [d["mtime"] for d in docs if newest and newest - d["mtime"] < 43200]
        started = min(recent) if recent else None
        basis = "oldest recently written document (no start marker)"
        missing.append("feedback/run.json (no start marker — the usage window begins "
                       "at the first document written, so survey and dispatch cost "
                       "before it is not measured)")
    ended = max([d["mtime"] for d in docs], default=None)
    survey = run_json("repo_survey.py", [root]) or {}
    cov = run_json("coverage_check.py", [docs_dir, root]) or {}
    lnt = lint(docs_dir, docs)
    if not docs:
        missing.append(f"no .md documents in {os.path.relpath(docs_dir, root)}")
    arows = field_log.read_rows(os.path.join(fdir, "anomalies.jsonl"))
    by_code = {}
    for r in arows:
        by_code[r.get("code") or "unknown"] = by_code.get(r.get("code") or "unknown", 0) + 1
    manifests = {}
    for m in survey.get("manifests") or []:
        manifests[m.get("kind")] = manifests.get(m.get("kind"), 0) + 1
    detail = [d for d in docs if d["file"] != "overview.md"]
    split = ("single document" if len(docs) <= 1
             else f"overview + {len(detail)} detail document(s)")
    diagrams = sum(d["diagrams"] for d in docs)
    for d in docs:
        d["written_at"] = run_summary.iso(d.pop("mtime"))
    return {
        "schema": SCHEMA,
        "generated_at": field_log.now_iso(),
        "plugin": plugin,
        "host": {"repo": os.path.basename(root),
                 "loop_dir": os.path.relpath(os.path.abspath(docs_dir), root),
                 **git_state(root, docs_dir)},
        "platform": run_summary.platform_info(plugin["name"]),
        "window": {"started_at": run_summary.iso(started), "ended_at": run_summary.iso(ended),
                   "basis": basis,
                   "wall_s": round(ended - started, 1)
                   if started and ended and ended >= started else None},
        "survey": {"total_files": survey.get("total_files"),
                   "total_loc": survey.get("total_loc"),
                   "top_level_dirs": len(survey.get("by_top_dir") or {}),
                   "manifests": manifests},
        "split": split,
        "documents": docs,
        "lint": lnt,
        "coverage": {k: cov.get(k) for k in ("source_files", "mentioned", "unmentioned")},
        "objective": {
            "Survey": f"{survey.get('total_files', '?')} source files, "
                      f"{survey.get('total_loc', '?')} LOC, "
                      f"{sum(manifests.values())} manifest(s)",
            "Split": split,
            "Documents": f"{len(docs)} · {diagrams} diagram(s)",
            "Lint": (f"{lnt.get('issues')} issue(s) in {lnt.get('blocks')} block(s)"
                     if lnt.get("ran") else "not run"),
            "Coverage": (f"{cov.get('mentioned')}/{cov.get('source_files')} source files "
                         f"mentioned" if cov else "not run"),
        },
        "anomalies": {"count": len(arows), "by_code": by_code, "rows": arows},
        "missing": missing,
    }

def write(docs_dir, stop_note=""):
    summary = build(docs_dir, stop_note)
    fdir = field_log.feedback_dir(docs_dir)
    if not fdir:
        raise OSError(f"{docs_dir} is not a directory")
    path = os.path.join(fdir, "run-summary.json")
    tmp = path + ".partial"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path

def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("start", "write"):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    verb, docs_dir = args[0], args[1]
    if verb == "start":
        os.makedirs(os.path.join(docs_dir, "feedback"), exist_ok=True)
        path = os.path.join(docs_dir, "feedback", "run.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"started_ts": round(time.time(), 3),
                       "started_at": field_log.now_iso()}, fh)
            fh.write("\n")
        print(json.dumps({"started": path}))
        return
    if not os.path.isdir(docs_dir):
        print(f"arch_summary: {docs_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    if "--print" in args:
        print(json.dumps(build(docs_dir), indent=2))
        return
    print(json.dumps({"run_summary": write(docs_dir)}))

if __name__ == "__main__":
    main()
