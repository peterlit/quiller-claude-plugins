#!/usr/bin/env python3
"""File a field report for the plugin maintainer — the mechanical half.

Usage:
  feedback.py scaffold <dir> [--since T] [--until T] [--date YYYY-MM-DD] [--force]
  feedback.py finalize <dir> [<report.md>] [--no-drop]
  feedback.py quick    <dir> [--since T] [--until T] [--date YYYY-MM-DD] [--no-drop]
  feedback.py questions

<dir> is the loop directory (.review-loop, .qa-loop) or, for
arch-docs-tools, the docs directory (docs/architecture).

scaffold  gathers the objective bundle — the run summary the report stage
          wrote (built now if missing), effective tokens per role measured
          from the session transcripts, the maintainer's watch questions —
          and writes a DRAFT report with every section laid out. The agent
          fills in only what it observed.
finalize  validates the draft (every watch item answered, evidence where
          one was observed), mints an ID per item, appends the summary and
          usage as fenced JSON so the file is self-contained, and copies it
          to the machine-local drop the maintainer's ingest reads:
          ${XDG_DATA_HOME:-~/.local/share}/quiller/inbox/<host>/
quick     scaffold + finalize with no questions: version, verdicts,
          anomalies and cost. The floor — it costs the agent nothing, and
          it is worth more than most prose.

This script decides nothing about the run and never reads source code. It
is identical in every plugin that ships it; the summary builder beside it
(run_summary.py or arch_summary.py) is what differs.

Measured origin: ten field memos arrived under six naming schemes, each
re-deriving its token table with a throwaway script, stating the plugin
version from memory, and hand-delivered — and one decisions record arrived
eleven days after the run it described.
"""
import datetime, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCHEMA = 1
SHORT = {"review-loop-tools": "rl", "qa-loop-tools": "qa", "arch-docs-tools": "ad"}
ANSWERS = ("observed", "not observed", "n/a")
UNANSWERED = "_unanswered_"
GUIDE = re.compile(r"<!-- guide\b.*?-->\n?", re.S)
GUIDE_OPEN = "<!-- guide (write BELOW this comment; finalize removes it): "

# (heading, carries item ids, guide text). Order is the report's order.
SECTIONS = [
    ("Keep", False,
     "What worked and must not be \"simplified\" away. One bullet each, with the number "
     "or the moment that showed it."),
    ("Defects", True,
     "Plugin defects, in IMPACT order. One `### <short title>` per defect, then the "
     "labeled lines below. Leave a line empty rather than guessing.\n"
     "### <short title>\n"
     "- happened: \n- expected: \n- repro: <smallest steps or command>\n"
     "- evidence: <path in the loop dir, round, or anomaly code>\n"
     "- cost: <turns, tokens or wall-clock, if known>\n"
     "- mechanism: <your suggested fix, if you have one>"),
    ("Friction", True,
     "Not a defect, but it cost effort: docs that conflated two things, a verb whose "
     "output was misread, a default wrong for this repo. One `### <short title>` each, "
     "then a sentence or two."),
    ("Decisions taken without the human", True,
     "Every place the contract wanted a human and you chose instead. One "
     "`### <short title>` each, then:\n- wanted: \n- chose: \n- why: "),
    ("Seen again", False,
     "Items listed in FIELD-QUESTIONS.md (open, shipped or settled) that this run met "
     "again. One bullet each: `- <id> — still happens | fixed for us — <one line>`."),
    ("Host-repo recommendations", False,
     "Actions for THIS repo, not the plugin (lanes to keep, session hygiene). Bullets."),
    ("Environment and harness artifacts", True,
     "Things that went wrong and were NOT the plugin's fault (a stale env var, a tool "
     "not loaded, a scheme that refuses UI tests). One `### <short title>` each — the "
     "maintainer's triage starts from your call."),
    ("Wishes", True,
     "One line each, as `- ` bullets."),
]

def die(msg, code=1):
    print(f"feedback: {msg}", file=sys.stderr)
    sys.exit(code)

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default

def plugin_root():
    return os.path.dirname(HERE)

def summary_module():
    # arch_summary first: arch-docs-tools ships run_summary.py too (for its
    # plugin-identity and platform probes), but its report is arch_summary's.
    for name in ("arch_summary", "run_summary"):
        if os.path.exists(os.path.join(HERE, name + ".py")):
            return __import__(name)
    die("no summary builder (run_summary.py / arch_summary.py) beside feedback.py")

def repo_root(d):
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(d))

def resolve_source(d):
    """The directory whose run this report describes. A loop dir with no
    live ledger but with archives means the loop was archived before anyone
    filed feedback — the newest archive is the run."""
    d = d.rstrip("/") or d
    if not os.path.isdir(d):
        die(f"{d} is not a directory — run this from the repo the plugin ran in")
    if os.path.exists(os.path.join(d, "ledger.json")) or \
            os.path.exists(os.path.join(d, "feedback", "run-summary.json")):
        return d, None
    arch = os.path.join(d, "archive")
    cands = []
    if os.path.isdir(arch):
        for name in os.listdir(arch):
            p = os.path.join(arch, name)
            if os.path.exists(os.path.join(p, "ledger.json")):
                cands.append((os.path.getmtime(os.path.join(p, "ledger.json")), p))
    if cands:
        src = max(cands)[1]
        return src, f"no live loop state in {d}; reporting on the newest archive, {src}"
    return d, None      # arch docs dir, or a loop that never produced a ledger

def parse_questions(path=None):
    """FIELD-QUESTIONS.md -> {"watch": [...], "settled": [...]} of
    {"id", "text"}. Items are `- **<id>** — <text>` bullets under the two
    headed sections; continuation lines are joined."""
    path = path or os.path.join(plugin_root(), "FIELD-QUESTIONS.md")
    out = {"watch": [], "settled": [], "path": path, "found": os.path.exists(path)}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out
    bucket, cur = None, None
    for line in lines:
        if line.startswith("## "):
            h = line[3:].strip().lower()
            bucket = ("watch" if h.startswith("watch items") else
                      "settled" if h.startswith("settled decisions") else None)
            cur = None
            continue
        if bucket is None:
            continue
        m = re.match(r"- \*\*([a-z0-9][a-z0-9-]*)\*\* — (.+)$", line)
        if m:
            cur = {"id": m.group(1), "text": m.group(2).strip()}
            out[bucket].append(cur)
        elif cur is not None and line.startswith("  ") and line.strip():
            cur["text"] += " " + line.strip()
        elif not line.strip():
            cur = None
    return out

def fmt_int(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "unknown"

def fmt_dur(s):
    if not isinstance(s, (int, float)) or s <= 0:
        return "unknown"
    s = int(s)
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m{s % 60:02d}s"

def glance(summary, usage):
    """The human-readable digest of the objective bundle."""
    L = []
    p = summary.get("plugin") or {}
    inst = p.get("installed") or {}
    match = p.get("install_matches_running")
    L.append(f"- **Plugin:** {p.get('name')} **{p.get('version')}** (the code that ran) · "
             + (f"installed {inst.get('version')}" if inst else "no installed_plugins.json entry")
             + (" · match" if match else
                " · **MISMATCH** (symlinked or --plugin-dir install)" if match is False else ""))
    h = summary.get("host") or {}
    L.append(f"- **Host:** {h.get('repo')} · `{h.get('loop_dir')}`"
             + (" · loop dir is git-ignored here" if h.get("loop_dir_ignored") else ""))
    pf = summary.get("platform") or {}
    L.append("- **Platform:** " + " · ".join(
        f"{k} {v}" for k, v in pf.items() if k in ("macos", "xcode", "claude", "arch")))
    if "stop" in summary:
        st, rd = summary["stop"], summary.get("rounds") or {}
        L.append(f"- **Run:** {rd.get('count', 0)} round(s) · stop `{st.get('headline')}`"
                 + (f" (verdict `{st.get('decision')}`)" if st.get("headline") != st.get("decision") else "")
                 + (f" after round {st.get('round')}" if st.get("round") is not None else "")
                 + (f" — {st.get('reason')}" if st.get("reason") else "")
                 + (" · closeout ran" if st.get("closeout_ran") else ""))
        if st.get("stop_note"):
            L.append(f"- **How it actually ended:** {st['stop_note']}")
        f = summary.get("findings") or {}
        sev = f.get("by_severity") or {}
        stt = f.get("by_status") or {}
        L.append(f"- **Findings:** {f.get('total', 0)} — "
                 + ", ".join(f"{sev[k]} {k}" for k in ("blocker", "major", "minor") if sev.get(k))
                 + " · " + ", ".join(f"{v} {k}" for k, v in sorted(stt.items(), key=lambda kv: -kv[1]))
                 + f" · {f.get('fix_review_rejections', 0)} fix rejection(s)"
                 + f" · {(f.get('proposals') or {}).get('open', 0)} open proposal(s)")
    for k, v in (summary.get("objective") or {}).items():
        L.append(f"- **{k}:** {v}")
    rep = (summary.get("usage_reported") or {}).get("total")
    eff = (usage or {}).get("effective_total")
    cost = []
    if rep:
        cost.append(f"reported {fmt_int(rep)}")
    if eff:
        cost.append(f"effective {fmt_int(eff)}"
                    + (f" ({eff / rep:.1f}x reported)" if rep else ""))
    wall = (summary.get("window") or {}).get("wall_s")
    if wall:
        cost.append(f"wall {fmt_dur(wall)}")
    L.append("- **Cost:** " + (" · ".join(cost) if cost else "not measured"))
    d = summary.get("dispatches") or {}
    if d.get("count"):
        L.append(f"- **Dispatches:** {d['count']} · "
                 + ", ".join(f"{a} x{v['dispatches']} ({fmt_dur(v['wall_s'])})"
                             for a, v in sorted((d.get("by_agent") or {}).items()))
                 + (f" · {d['unreturned']} unreturned" if d.get("unreturned") else ""))
    a = summary.get("anomalies") or {}
    L.append("- **Anomalies:** " + (", ".join(
        f"`{k}` x{v}" for k, v in sorted((a.get("by_code") or {}).items()))
        if a.get("count") else "none recorded"))
    ud = summary.get("unattended_defaults") or []
    if ud:
        L.append(f"- **Unattended defaults taken:** {len(ud)}")
    hy = summary.get("hygiene") or {}
    if hy.get("violation_count"):
        L.append(f"- **Hygiene violations standing:** {hy['violation_count']} "
                 f"({', '.join(f'{k} x{v}' for k, v in hy.get('by_kind', {}).items())})")
    for m in summary.get("missing") or []:
        L.append(f"- **Missing:** {m}")
    return L

def usage_table(usage):
    if not usage or not usage.get("by_role"):
        return ["_No transcripts measured for this window._"]
    L = ["| Role | Dispatches | Requests | Effective | Input | Cache read | Cache write | Output |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in usage["by_role"]:
        L.append(f"| {r['role']} | {r['dispatches']} | {r['requests']:,} | {r['effective']:,} | "
                 f"{r['input_tokens']:,} | {r['cache_read_input_tokens']:,} | "
                 f"{r['cache_creation_input_tokens']:,} | {r['output_tokens']:,} |")
    L.append(f"| **all** | | | **{usage['effective_total']:,}** | | | | |")
    return L

def front_matter(meta):
    return ["---"] + [f"{k}: {meta[k]}" for k in meta] + ["---"]

def parse_front_matter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if k.strip():
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]

def iso_to_epoch(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def measure_usage(repo, summary, since, until):
    import loop_usage
    w = summary.get("window") or {}
    s = loop_usage.parse_time(since) if since else iso_to_epoch(w.get("started_at"))
    u = loop_usage.parse_time(until) if until else iso_to_epoch(w.get("ended_at"))
    if s is None:
        return {"by_role": [], "effective_total": 0, "transcripts": 0,
                "note": "no usage window: the run's start time is unknown — pass --since"}
    if u is not None and not until:
        u += 120          # the report stage's own last requests
    out = loop_usage.measure(repo=repo, since=s, until=u)
    out["window"]["basis"] = "--since/--until" if since else w.get("basis")
    if not out.get("project_dir_found"):
        out["note"] = ("no transcript directory for this repo under ~/.claude/projects "
                       "(another machine, or transcripts were cleaned up)")
    return out

FEEDBACK_RULES = ("!**/feedback/*.json", "!**/feedback/*.jsonl", "!**/feedback/*.md")

def upgrade_allowlist(top):
    """A loop bootstrapped by an older plugin carries that release's
    allowlist, which ignores feedback/ — the report would be filed into a
    directory git cannot see. When the loop-dir .gitignore is the PLUGIN'S
    (its first line says "Managed by"), add the three feedback rules. A
    host-owned .gitignore is never touched. Returns True if it changed."""
    gi = os.path.join(top, ".gitignore")
    try:
        with open(gi, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    lines = text.splitlines()
    if not lines or "Managed by" not in lines[0] or "-loop-tools" not in lines[0]:
        return False
    have = {l.strip() for l in lines}
    add = [r for r in FEEDBACK_RULES if r not in have]
    if not add:
        return False
    # Before any trailing re-exclusions (qa's __pycache__/ and *.pyc), so
    # the file still reads as negations first, exclusions last.
    while lines and not lines[-1].strip():
        lines.pop()
    i = len(lines)
    while i > 1 and lines[i - 1].strip() and lines[i - 1].strip() != "*" \
            and not lines[i - 1].lstrip().startswith(("!", "#")):
        i -= 1
    lines[i:i] = add
    with open(gi, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return True

def existing_reports(fdir, stem):
    out = []
    if os.path.isdir(fdir):
        for n in sorted(os.listdir(fdir)):
            if n.startswith(stem) and n.endswith(".md"):
                out.append(os.path.join(fdir, n))
    return out

def scaffold(args, quick=False):
    opt = {"--since": None, "--until": None, "--date": None}
    flags, pos = set(), []
    it = iter(args)
    for a in it:
        if a in opt:
            opt[a] = next(it, None)
        elif a in ("--force", "--no-drop"):
            flags.add(a)
        else:
            pos.append(a)
    if not pos:
        die("usage: feedback.py scaffold <dir> [--since T] [--until T] [--force]", 2)
    top = pos[0]
    source, note = resolve_source(top)
    upgraded = upgrade_allowlist(top)
    mod = summary_module()
    fdir = os.path.join(source, "feedback")
    os.makedirs(fdir, exist_ok=True)
    spath = os.path.join(fdir, "run-summary.json")
    summary = load_json(spath)
    built_now = False
    if not isinstance(summary, dict) or summary.get("schema") != SCHEMA:
        mod.write(source)
        summary = load_json(spath) or {}
        built_now = True
    repo = repo_root(top)
    usage = measure_usage(repo, summary, opt["--since"], opt["--until"])
    with open(os.path.join(fdir, "usage.json"), "w", encoding="utf-8") as fh:
        json.dump(usage, fh, indent=1)
        fh.write("\n")

    p = summary.get("plugin") or {}
    name, version = p.get("name") or "unknown", p.get("version") or "unknown"
    host = (summary.get("host") or {}).get("repo") or os.path.basename(repo)
    host = re.sub(r"[^A-Za-z0-9._]+", "-", os.path.basename(repo) or host).strip("-") or "host"
    date = opt["--date"] or datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        die("--date must be YYYY-MM-DD", 2)
    stem = f"{name}-{version}-{date}"
    prior = existing_reports(fdir, stem)
    drafts = [x for x in prior
              if parse_front_matter(open(x, encoding="utf-8").read())[0].get("status") == "draft"]
    if drafts and "--force" not in flags and not quick:
        die(f"a draft already exists: {drafts[0]} — fill it in and run finalize, "
            f"or pass --force to regenerate it (your answers in it are lost)")
    if drafts and not quick:
        path = drafts[0]
    else:
        # A quick bundle never reuses a draft: it would overwrite answers
        # somebody is still writing.
        path, n = os.path.join(fdir, stem + ".md"), 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(fdir, f"{stem}-{n}.md")

    q = parse_questions()
    meta = {"quiller-feedback": SCHEMA, "plugin": name, "version": version,
            "installed-version": (p.get("installed") or {}).get("version") or "unknown",
            "install-matches-running": str(bool(p.get("install_matches_running"))).lower(),
            "host": host, "date": date,
            "id-prefix": f"{SHORT.get(name, name)}-{version}-{date.replace('-', '')}-{host}",
            "kind": "quick" if quick else "full", "status": "draft"}
    L = front_matter(meta)
    L += ["", f"# Field report — {name} {version} — {host} — {date}", ""]
    L += ["## Run at a glance", ""] + glance(summary, usage) + [""]
    if note:
        L += [f"_{note}_", ""]
    if built_now:
        L += ["_The run summary was not written at report time (an older plugin, or an "
              "aborted run); it was built now from the state on disk._", ""]
    L += ["## Effective tokens by role", ""] + usage_table(usage) + [""]
    if usage.get("note"):
        L += [f"_{usage['note']}_", ""]
    L += ["## Watch items", ""]
    if quick:
        L += ["_Quick bundle — no questions asked._", ""]
    elif not q["watch"]:
        L += ["_This plugin version ships no watch items._", ""]
    else:
        L += [GUIDE_OPEN + "answer EVERY item with exactly one of: observed | not observed "
              "| n/a. `n/a` means the run never reached the situation. Give one line of "
              "evidence when observed (a path in the loop dir, a round, a count). -->", ""]
        for w in q["watch"]:
            L += [f"- **{w['id']}** — {w['text']}",
                  f"  - answer: {UNANSWERED}", "  - evidence: ", ""]
    if not quick:
        for title, _ids, guide in SECTIONS:
            L += [f"## {title}", "", f"{GUIDE_OPEN}{guide} -->", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L).rstrip() + "\n")
    out = {"draft": path, "source": source, "plugin": name, "version": version,
           "kind": meta["kind"], "watch_items": 0 if quick else len(q["watch"]),
           "settled_decisions": len(q["settled"]), "questions_file": q["path"],
           "summary_built_now": built_now, "effective_total": usage.get("effective_total"),
           "anomalies": (summary.get("anomalies") or {}).get("by_code") or {},
           "missing": summary.get("missing") or [],
           "allowlist_upgraded": upgraded}
    if not quick:
        out["next"] = (f"read the Settled and Open/shipped sections of {q['path']}, fill in "
                       f"{path}, then: feedback.py finalize {top}")
    return out, top, path, flags

def split_sections(body):
    """[(heading or None, [lines])] split on `## ` headings."""
    out, cur = [], (None, [])
    for line in body.splitlines():
        if line.startswith("## "):
            out.append(cur)
            cur = (line[3:].strip(), [])
        else:
            cur[1].append(line)
    out.append(cur)
    return out

def check_watch(lines):
    """-> (problems, answers) for the Watch items section."""
    problems, answers, cur = [], {}, None
    for line in lines:
        m = re.match(r"- \*\*([a-z0-9][a-z0-9-]*)\*\* — ", line)
        if m:
            cur = m.group(1)
            answers[cur] = {"answer": None, "evidence": ""}
            continue
        if cur is None:
            continue
        m = re.match(r"\s+- answer:\s*(.*)$", line)
        if m:
            answers[cur]["answer"] = m.group(1).strip().strip("`*_ ").lower()
            continue
        m = re.match(r"\s+- evidence:\s*(.*)$", line)
        if m:
            answers[cur]["evidence"] = m.group(1).strip()
    for wid, a in answers.items():
        ans = a["answer"] or ""
        ans = {"na": "n/a", "not applicable": "n/a", "not-observed": "not observed",
               "notobserved": "not observed"}.get(ans, ans)
        a["answer"] = ans
        if ans not in ANSWERS:
            problems.append(f"watch item {wid}: answer must be one of "
                            f"{' | '.join(ANSWERS)} (got {ans or 'nothing'!r})")
        elif ans == "observed" and not a["evidence"]:
            problems.append(f"watch item {wid}: `observed` needs one line of evidence")
    return problems, answers

def next_item_number(fdir, prefix, skip):
    n = 0
    pat = re.compile(re.escape(prefix) + r"-(\d+)\b")
    if os.path.isdir(fdir):
        for name in os.listdir(fdir):
            p = os.path.join(fdir, name)
            if not name.endswith(".md") or os.path.abspath(p) == os.path.abspath(skip):
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    for m in pat.finditer(fh.read()):
                        n = max(n, int(m.group(1)))
            except OSError:
                pass
    return n

def mint_ids(sections, prefix, start):
    """Stamp `### title` items (and Wishes bullets) in id-bearing sections.
    Idempotent: an item already carrying an id of this prefix keeps it."""
    idpat = re.compile(re.escape(prefix) + r"-(\d+)\b")
    carriers = {t for t, ids, _g in SECTIONS if ids}
    used = [int(m.group(1)) for _h, ls in sections for l in ls for m in idpat.finditer(l)]
    n = max([start] + used)
    minted, warnings = [], []
    for heading, lines in sections:
        if heading not in carriers:
            continue
        i = 0
        while i < len(lines):
            line = lines[i]
            is_item = line.startswith("### ") or (heading == "Wishes" and re.match(r"- \S", line))
            if is_item and not idpat.search(line):
                n += 1
                iid = f"{prefix}-{n}"
                if line.startswith("### "):
                    title = line[4:].strip()
                    lines[i] = f"### {iid} — {title}"
                else:
                    title = line[2:].strip()
                    lines[i] = f"- **{iid}** — {title}"
                minted.append({"id": iid, "section": heading, "title": title[:120]})
            elif is_item:
                m = idpat.search(line)
                minted.append({"id": m.group(0), "section": heading,
                               "title": re.sub(r"^(### |- )(\*\*)?" + re.escape(m.group(0))
                                               + r"(\*\*)? — ", "", line).strip()[:120]})
            i += 1
        if heading == "Defects":
            # A defect without a repro or an evidence path is triaged last:
            # "reproduce minimally first" is the maintainer's second diagnostic.
            blocks, cur = [], None
            for line in lines:
                if line.startswith("### "):
                    cur = [line, {}]
                    blocks.append(cur)
                elif cur is not None:
                    m = re.match(r"- (happened|expected|repro|evidence|cost|mechanism):\s*(.*)$", line)
                    if m:
                        cur[1][m.group(1)] = m.group(2).strip()
            for head, fields in blocks:
                lack = [k for k in ("repro", "evidence") if not fields.get(k)]
                if lack:
                    warnings.append(f"{head[4:].split(' — ')[0]}: no {' or '.join(lack)} given")
    return minted, warnings

def drop_dir(host, repo):
    """The machine-local delivery drop. Outside every repo by rule: a
    session in one repo never writes into another repo's tree, and an
    XDG_DATA_HOME that resolves INSIDE the host repo (repo-shipped env) is
    ignored in favor of ~/.local/share."""
    base = os.environ.get("XDG_DATA_HOME") or ""
    home_base = os.path.expanduser("~/.local/share")
    if base:
        rb, rr = os.path.realpath(base), os.path.realpath(repo)
        if not os.path.isabs(base) or rb == rr or rb.startswith(rr + os.sep):
            print("feedback: XDG_DATA_HOME points inside this repo (or is relative); "
                  "using ~/.local/share for the drop", file=sys.stderr)
            base = home_base
    else:
        base = home_base
    return os.path.join(base, "quiller", "inbox", host)

def finalize(args, quick=False, path=None):
    flags = {a for a in args if a == "--no-drop"}
    pos = [a for a in args if not a.startswith("--")]
    if not pos:
        die("usage: feedback.py finalize <dir> [<report.md>] [--no-drop]", 2)
    top = pos[0]
    source, _note = resolve_source(top)
    fdir = os.path.join(source, "feedback")
    if path is None and len(pos) > 1:
        path = pos[1]
    if path is None:
        drafts = []
        if os.path.isdir(fdir):
            for n in sorted(os.listdir(fdir)):
                p = os.path.join(fdir, n)
                if n.endswith(".md") and parse_front_matter(
                        open(p, encoding="utf-8").read())[0].get("status") == "draft":
                    drafts.append(p)
        if not drafts:
            die(f"no draft report in {fdir} — run `feedback.py scaffold {top}` first")
        if len(drafts) > 1:
            die("several drafts exist; name one: " + ", ".join(drafts), 2)
        path = drafts[0]
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    meta, body = parse_front_matter(text)
    if str(meta.get("quiller-feedback")) != str(SCHEMA):
        die(f"{path} is not a feedback draft (no `quiller-feedback: {SCHEMA}` front matter)")
    if meta.get("status") == "filed":
        die(f"{path} is already filed; scaffold a new report to add to it")
    quick = quick or meta.get("kind") == "quick"
    body = GUIDE.sub("", body)
    sections = split_sections(body)

    problems, answers = [], {}
    if not quick:
        for heading, lines in sections:
            if heading == "Watch items":
                problems, answers = check_watch(lines)
    if UNANSWERED in body and not problems and not quick:
        problems.append(f"a `{UNANSWERED}` placeholder is still in the report")
    if problems:
        for p in problems:
            print(f"feedback: {p}", file=sys.stderr)
        die(f"{len(problems)} problem(s) in {path} — fix them and run finalize again")

    prefix = meta.get("id-prefix") or "item"
    minted, warnings = mint_ids(sections, prefix, next_item_number(fdir, prefix, path))
    known = {t for t, _i, _g in SECTIONS}
    out = []
    for heading, lines in sections:
        if heading is not None:
            out.append(f"## {heading}")
        content = "\n".join(lines).strip("\n")
        if heading in known and not content.strip():
            content = "\n_none_"
        out.append(content if heading is None else content + "\n")
    body = "\n".join(out).rstrip() + "\n"

    summary = load_json(os.path.join(fdir, "run-summary.json"), {})
    usage = load_json(os.path.join(fdir, "usage.json"), {})
    meta["status"] = "filed"
    meta["items"] = len(minted)
    meta["filed-at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    final = "\n".join(front_matter(meta)) + "\n" + body
    final += ("\n## Appendix A — run summary\n\n```json\n"
              + json.dumps(summary, indent=1) + "\n```\n"
              "\n## Appendix B — effective tokens\n\n```json\n"
              + json.dumps(usage, indent=1) + "\n```\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(final)

    repo = repo_root(top)
    result = {"report": path, "kind": meta.get("kind"), "items": len(minted),
              "ids": [m["id"] for m in minted], "warnings": warnings,
              "watch_answers": {k: v["answer"] for k, v in answers.items()}}
    if "--no-drop" not in flags:
        try:
            dd = drop_dir(meta.get("host") or os.path.basename(repo), repo)
            os.makedirs(dd, exist_ok=True)
            dst = os.path.join(dd, os.path.basename(path))
            shutil.copy2(path, dst)
            home = os.path.expanduser("~")
            result["drop"] = "~" + dst[len(home):] if dst.startswith(home) else dst
        except OSError as e:
            result["drop"] = None
            result["warnings"].append(f"drop copy failed ({e}); deliver {path} by hand")
    commit = [path] + [os.path.join(fdir, n) for n in
                       ("run-summary.json", "usage.json", "anomalies.jsonl", "dispatches.jsonl")
                       if os.path.exists(os.path.join(fdir, n))]
    try:
        gi = os.path.join(top, ".gitignore")
        st = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--",
                             os.path.abspath(gi)], capture_output=True, text=True, timeout=20)
        if st.returncode == 0 and st.stdout.strip():
            commit.append(gi)       # the allowlist scaffold upgraded
    except Exception:
        pass
    try:
        ign = subprocess.run(["git", "-C", repo, "check-ignore", "-q", os.path.abspath(path)],
                             capture_output=True, timeout=20)
        result["git_ignored"] = ign.returncode == 0
    except Exception:
        result["git_ignored"] = None
    if result["git_ignored"]:
        result["warnings"].append("this repo ignores the report's path: it is not versioned "
                                  "here — the drop copy is the delivery")
    else:
        result["stage_by_path"] = "git add " + " ".join(
            "'" + c + "'" if " " in c else c for c in commit)
    return result

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    verb, rest = args[0], args[1:]
    if verb == "questions":
        print(json.dumps(parse_questions(), indent=1))
    elif verb == "scaffold":
        out, _top, _path, _flags = scaffold(rest)
        print(json.dumps(out, indent=1))
    elif verb == "finalize":
        print(json.dumps(finalize(rest), indent=1))
    elif verb == "quick":
        out, top, path, flags = scaffold(rest, quick=True)
        res = finalize([top] + sorted(flags & {"--no-drop"}), quick=True, path=path)
        res["effective_total"] = out.get("effective_total")
        res["missing"] = out.get("missing")
        print(json.dumps(res, indent=1))
    else:
        die(f"unknown verb {verb!r} (scaffold | finalize | quick | questions)", 2)

if __name__ == "__main__":
    main()
