#!/usr/bin/env python3
"""Effective-token accounting for a loop, from raw session transcripts.

Usage:
  loop_usage.py [--since EPOCH|ISO] [--until EPOCH|ISO] [--repo PATH] [--dir PROJECT_DIR]
                [--by-role] [--rows]

Shipped with the plugin on purpose: the measurement is the most expensive
part of every field report, and it was reimplemented from a docstring by
both field agents (measured: "the previous two measurements were made with
throwaway scratchpad scripts that did not survive the session"; the copy
that did survive hard-coded one host repo's project directory). One shipped
script keeps the numbers comparable across repos and plugin versions.

The project directory is DERIVED: Claude Code keeps a repo's transcripts in
~/.claude/projects/<the repo's absolute path with every non-alphanumeric
character replaced by '-'>. --repo names the repo (default: the current
directory); --dir overrides the derivation outright.

`--since`/`--until` are PER RECORD, not per file: a transcript's mtime is
only a cheap pre-filter, and every usage record is kept or dropped on its
own timestamp, so a long session touched five minutes ago contributes only
the requests made inside the window. A record with no parsable timestamp is
COUNTED (dropping it would silently under-report) and tallied as `undated`.

Accounting (unchanged from every prior measurement, so figures compare):
  effective = input x1 + cache_read x0.1 + cache_write x2 + output x5
Usage records are deduplicated by requestId; images count a flat 1,600.

Output: JSON. Default and --by-role print one row per ROLE — a subagent's
type (`implementer`, `skeptical-reviewer`, …) or `orchestrator` for a main
session — with `effective`, the four billed classes, `requests`,
`dispatches` (transcripts) and `images` — plus `by_dispatch`, one row per
subagent transcript in time order. --rows prints one row per transcript
instead (no paths: `file` is the basename).
"""
import glob, json, os, re, sys
from collections import defaultdict
from datetime import datetime

IMG = 1600
CLASSES = ("input_tokens", "cache_read_input_tokens",
           "cache_creation_input_tokens", "output_tokens")

def project_dir(repo="."):
    """Where Claude Code keeps this repo's transcripts. Tries the path as
    given and its realpath (a repo reached through a symlink is stored under
    the path the session was started with)."""
    base = os.path.expanduser("~/.claude/projects")
    seen = []
    for p in (os.path.abspath(repo), os.path.realpath(repo)):
        enc = re.sub(r"[^A-Za-z0-9]", "-", p)
        cand = os.path.join(base, enc)
        if cand not in seen:
            seen.append(cand)
    for cand in seen:
        if os.path.isdir(cand):
            return cand
    return seen[0]

def parse_time(v):
    """Epoch seconds from an epoch (seconds or millis) or an ISO timestamp;
    None when absent or unparsable."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) / 1000.0 if v > 1e11 else float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        f = float(s)
        return f / 1000.0 if f > 1e11 else f
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def eff(u):
    return (u.get("input_tokens", 0)
            + 0.1 * u.get("cache_read_input_tokens", 0)
            + 2 * u.get("cache_creation_input_tokens", 0)
            + 5 * u.get("output_tokens", 0))

def _meta(path):
    meta = path[:-6] + ".meta.json" if path.endswith(".jsonl") else path + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as fh:
            m = json.load(fh)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}

def agent_type_of(path):
    """A subagent's type, from its sidecar first — the transcript itself
    rarely carries it. `agent-<id>.jsonl` sits next to `agent-<id>.meta.json`
    ({"agentType": …, "description": …}); reading it is what makes sidechain
    rows attributable to implementer vs reviewer."""
    m = _meta(path)
    if m.get("agentType"):
        return m["agentType"]
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("attributionAgent"):
                    return r["attributionAgent"]
                break
    except Exception:
        pass
    if not os.path.basename(path).startswith("agent-"):
        # A MAIN-session transcript is not an agent. Without this guard the
        # scan below finds the orchestrator's own Agent tool_use blocks and
        # labels the orchestrator row with whatever it dispatched last.
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                for k in ("subagent_type", "agentType", "subagentType"):
                    if r.get(k):
                        return r[k]
    except Exception:
        pass
    return None

def _images(content):
    n = 0
    if isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "image":
                n += 1
            elif c.get("type") == "tool_result" and isinstance(c.get("content"), list):
                n += sum(1 for x in c["content"]
                         if isinstance(x, dict) and x.get("type") == "image")
    return n

def scan(proj, since=0.0, until=None):
    """One row per transcript with billed usage inside the window."""
    rows = []
    for path in glob.glob(os.path.join(proj, "**", "*.jsonl"), recursive=True):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if since and st.st_mtime < since:
            continue
        seen = set()
        n_req = n_img = n_undated = 0
        tot = defaultdict(float)
        sidechain = os.path.basename(path).startswith("agent-")
        first = last = None
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if not isinstance(r, dict):
                    continue
                # Decide `sidechain` before filtering, so a partially
                # in-window subagent still reports as one.
                if r.get("isSidechain"):
                    sidechain = True
                undated = False
                if since or until:
                    t = parse_time(r.get("timestamp"))
                    if t is None:
                        undated = True
                    elif (since and t < since) or (until and t > until):
                        continue
                    else:
                        first = t if first is None else min(first, t)
                        last = t if last is None else max(last, t)
                m = r.get("message") if isinstance(r.get("message"), dict) else {}
                u = m.get("usage") or r.get("usage")
                rid = r.get("requestId") or m.get("id")
                if isinstance(u, dict) and rid and rid not in seen:
                    seen.add(rid)
                    n_req += 1
                    if undated:
                        n_undated += 1
                    for k in CLASSES:
                        tot[k] += u.get(k, 0) or 0
                    tot["effective"] += eff({k: (u.get(k, 0) or 0) for k in CLASSES})
                n_img += _images(m.get("content"))
        if not n_req:
            continue
        tot["effective"] += n_img * IMG
        m = _meta(path)
        rows.append({"file": os.path.basename(path), "sidechain": sidechain,
                     "agent": agent_type_of(path) if sidechain else None,
                     "label": m.get("description"),
                     "requests": n_req, "images": n_img, "undated": n_undated,
                     "first": first, "last": last,
                     **{k: int(v) for k, v in tot.items()}})
    rows.sort(key=lambda r: -r["effective"])
    return rows

def role_of(row):
    if not row["sidechain"]:
        return "orchestrator"
    return (row.get("agent") or "subagent (untyped)").split(":")[-1]

def by_role(rows):
    agg = {}
    for r in rows:
        a = agg.setdefault(role_of(r), {"role": role_of(r), "dispatches": 0,
                                        "requests": 0, "images": 0, "undated": 0,
                                        "effective": 0, **{k: 0 for k in CLASSES}})
        a["dispatches"] += 1
        for k in ("requests", "images", "undated", "effective") + CLASSES:
            a[k] += r.get(k, 0)
    out = sorted(agg.values(), key=lambda a: -a["effective"])
    return out

def measure(repo=".", since=0.0, until=None, proj=None, rows=None):
    """The whole measurement as one dict — what the feedback bundle embeds."""
    proj = proj or project_dir(repo)
    found = os.path.isdir(proj)
    if rows is None:
        rows = scan(proj, since, until) if found else []
    roles = by_role(rows)
    return {
        "method": "effective = input x1 + cache_read x0.1 + cache_write x2 + output x5; "
                  "dedup by requestId; images 1,600 flat",
        "project_dir_found": found,
        "window": {"since": since or None, "until": until},
        "transcripts": len(rows),
        "undated_records": sum(r["undated"] for r in rows),
        "effective_total": sum(r["effective"] for r in rows),
        "effective_subagents": sum(r["effective"] for r in rows if r["sidechain"]),
        "effective_orchestrator": sum(r["effective"] for r in rows if not r["sidechain"]),
        "by_role": roles,
        # One row per subagent dispatch, oldest first: what a field report's
        # per-dispatch table was being hand-assembled from.
        "by_dispatch": [
            {"role": role_of(r), "label": (r.get("label") or "")[:100],
             "requests": r["requests"], "effective": r["effective"],
             "images": r["images"],
             "wall_s": round(r["last"] - r["first"], 1)
             if r.get("first") is not None and r.get("last") is not None else None}
            for r in sorted((x for x in rows if x["sidechain"]),
                            key=lambda x: (x.get("first") is None, x.get("first") or 0))],
    }

def main():
    args = sys.argv[1:]
    opt = {"--since": None, "--until": None, "--repo": ".", "--dir": None}
    flags = set()
    i = 0
    while i < len(args):
        a = args[i]
        if a in opt and i + 1 < len(args):
            opt[a] = args[i + 1]
            i += 2
        elif a in ("--by-role", "--rows"):
            flags.add(a)
            i += 1
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"loop_usage: unknown argument {a!r}", file=sys.stderr)
            return 2
    since = parse_time(opt["--since"]) if opt["--since"] else 0.0
    until = parse_time(opt["--until"]) if opt["--until"] else None
    if (opt["--since"] and since is None) or (opt["--until"] and until is None):
        print("loop_usage: --since/--until take epoch seconds or an ISO timestamp",
              file=sys.stderr)
        return 2
    proj = opt["--dir"] or project_dir(opt["--repo"])
    if not os.path.isdir(proj):
        print(f"loop_usage: no transcript directory for this repo "
              f"({os.path.basename(proj)} under ~/.claude/projects). Run from "
              f"the repo the loop ran in, or pass --repo/--dir.", file=sys.stderr)
        return 1
    rows = scan(proj, since or 0.0, until)
    undated = sum(r["undated"] for r in rows)
    if undated:
        print(f"note: {undated} record(s) had no parsable timestamp and were "
              f"COUNTED regardless of the window.", file=sys.stderr)
    if "--rows" in flags:
        print(json.dumps(rows, indent=1))
    else:
        print(json.dumps(measure(proj=proj, since=since or 0.0, until=until,
                                 rows=rows), indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
