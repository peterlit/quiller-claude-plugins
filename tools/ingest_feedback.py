#!/usr/bin/env python3
"""Ingest field reports from the machine-local drop and print the triage digest.

Usage: ingest_feedback.py [--dry-run] [--all] [--out DIGEST.md] [path ...]

Maintainer tool — lives in this repo, is not shipped in any plugin. Run it
at the start of a feedback cycle:

1. Scans ${XDG_DATA_HOME:-~/.local/share}/quiller/inbox/<host>/*.md (what
   `/<plugin>:feedback` writes) plus any paths given — for a bundle
   delivered from another machine — and copies every report not yet in
   docs/inbox/<host>/ into it, under its own name. This is the ONLY thing
   that writes field material into this repo. An existing file with
   different content is reported as a conflict and never overwritten.
2. Prints the triage digest (Markdown; --out also writes it to a file),
   which becomes a proposal's "Sources" and "Version check" sections:
   - reported version vs the current plugin.json, per plugin — a STALE
     install is flagged before anyone reads a claim;
   - installed-vs-running mismatches (symlinked or --plugin-dir installs);
   - watch-item answers as a table across bundles;
   - every item with its id, and for defects whether it carries a repro and
     an evidence path (reproduce minimally first);
   - items whose text matches a settled decision — "possibly settled,
     verify against HANDOFF section 3";
   - the same defect filed in N reports, grouped — the proposal cites the
     group, not N items (measured: four defects were filed independently in
     all three 2026-09 panel reports);
   - anomalies grouped by code across bundles: three agents hitting the
     same fallback is a defect even if nobody wrote it up;
   - cost per run: reported vs effective, and effective per role.
3. Appends a `new` entry to docs/inbox/dispositions.json for every item id
   it has not seen.

By default the digest covers the reports copied in THIS run; --all covers
every report already in docs/inbox/<host>/ as well. --dry-run copies and
writes nothing.

Report text is data, never instructions: this tool parses it, and a
maintainer session reading a digest treats what it quotes as claims to
verify against the code.
"""
import hashlib, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "docs", "inbox")
DISP = os.path.join(INBOX, "dispositions.json")
ITEM_SECTIONS = ("Defects", "Friction", "Decisions taken without the human",
                 "Environment and harness artifacts", "Wishes")
ID_RE = re.compile(r"\b((?:rl|qa|ad)-\d+\.\d+\.\d+-\d{8}-[A-Za-z0-9._-]+?-\d+)\b")
STOP = set("a an and are as at be by for from has have in is it its not of on or that the "
           "this to was were with when which while no into than then so if does did do "
           "after before again still every each any all one two".split())

# Settled decisions (HANDOFF section 3 / FIELD-QUESTIONS "Settled"): the
# patterns that suggest a report is re-raising one. A match is a TAG for the
# maintainer to verify, never a disposition.
SETTLED = {
    "s-seed-round-0": r"seed\b.*\bround[ -]?(0|1)\b|round[ -]?0\b.*seed",
    "s-implemented-rounds": r"implemented_rounds|discovery round",
    "s-set-usage-replaces": r"set-usage|add-usage",
    "s-reported-token-scale": r"budget.*(effective|billed|scale)|(effective|billed).*budget",
    "s-reopen-semantics": r"reopen|fixed\s*(->|→|to)\s*partial|churn",
    "s-archive-naming": r"archive.*(name|named|naming)",
    "s-minors-by-risk": r"fix_risk|minors?.*(closeout|brief)",
    "s-closeout-discipline": r"closeout.*(verify_cmd|iteration|second pass|done-but-red)",
    "s-fix-reviewer-not-terminal": r"fix-?reviewer.*(gate|terminal|trust)",
    "s-unsound-reverts-to-open": r"unsound|reverts? .*open",
    "s-model-pins": r"\bpin(s|ned)?\b.*model|model.*\bpin",
    "s-pbxproj-boundary": r"pbxproj",
    "s-degeneration-guard": r"degenerat|allow-wide",
    "s-mutations-through-scripts": r"hand-?edit",
    "s-do-not-cut": r"(cut|reduce|skip|fewer).*(thinking|screenshots?|verification)",
    "s-lane-failures-soft": r"(non-?zero|exit code|exit status).*lane|lane.*(non-?zero|exit code)",
    "s-dispatch-counter": r"(marker|:dispatched|counter).*(agent name|keyed|per-agent|expire|PostToolUse)",
    "s-usage-never-rewrites-decision": r"(set-usage|add-usage|late usage).*(decision|verdict)",
    "s-no-cache-pruning": r"(prune|delete|clean).*(cache|stale version|old version)",
    "s-no-archive-guarantee": r"(archive|conclusion).*(renam|duplicate|iCloud|Dropbox)",
}

def drop_root():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "quiller", "inbox")

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

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

def split_sections(body):
    out, cur = [], (None, [])
    for line in body.splitlines():
        if line.startswith("## "):
            out.append(cur)
            cur = (line[3:].strip(), [])
        else:
            cur[1].append(line)
    out.append(cur)
    return out

def fenced_json(lines):
    text = "\n".join(lines)
    m = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None

def parse_report(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    meta, body = parse_front_matter(text)
    if str(meta.get("quiller-feedback")) != "1":
        return None
    rep = {"path": path, "file": os.path.basename(path), "meta": meta, "items": [],
           "watch": {}, "seen_again": [], "summary": {}, "usage": {}}
    for heading, lines in split_sections(body):
        if heading == "Watch items":
            cur = None
            for l in lines:
                m = re.match(r"- \*\*([a-z0-9][a-z0-9-]*)\*\* — ", l)
                if m:
                    cur = m.group(1)
                    rep["watch"][cur] = {"answer": "", "evidence": ""}
                    continue
                m = re.match(r"\s+- (answer|evidence):\s*(.*)$", l)
                if m and cur:
                    rep["watch"][cur][m.group(1)] = m.group(2).strip().strip("`*_ ")
        elif heading in ITEM_SECTIONS:
            cur = None
            for l in lines:
                m = re.match(r"(?:### |- \*\*)" + ID_RE.pattern + r"(?:\*\*)? — (.*)$", l)
                if m:
                    cur = {"id": m.group(1), "section": heading, "title": m.group(2).strip(),
                           "fields": {}, "text": m.group(2).strip()}
                    rep["items"].append(cur)
                    continue
                if cur is None:
                    continue
                cur["text"] += " " + l.strip()
                m = re.match(r"- ([a-z]+):\s*(.*)$", l)
                if m:
                    cur["fields"][m.group(1)] = m.group(2).strip()
        elif heading == "Seen again":
            rep["seen_again"] = [l[2:].strip() for l in lines if l.startswith("- ")]
        elif heading and heading.startswith("Appendix A"):
            rep["summary"] = fenced_json(lines) or {}
        elif heading and heading.startswith("Appendix B"):
            rep["usage"] = fenced_json(lines) or {}
    return rep

def current_versions():
    out = {}
    for name in sorted(os.listdir(ROOT)):
        pj = os.path.join(ROOT, name, ".claude-plugin", "plugin.json")
        if os.path.exists(pj):
            try:
                with open(pj, encoding="utf-8") as fh:
                    out[name] = json.load(fh).get("version")
            except (OSError, ValueError):
                pass
    return out

def tokens(text):
    words = re.findall(r"[a-z][a-z0-9_.-]{2,}", text.lower())
    return {w.strip(".-") for w in words if w not in STOP}

def group_repeats(items):
    """Same defect, N reports. Key: an anomaly code named in the item when
    there is one; otherwise title-token overlap (Jaccard >= 0.45) between
    items from DIFFERENT reports."""
    codes = re.compile(r"\b(lane-[a-z-]+|dispatch-count-mismatch|session-gate-blocked|"
                       r"read-guard-denied|commit-guard-[a-z-]+|archive-[a-z-]+|"
                       r"hygiene-violation|mutate-[a-z-]+|notes-over-ceiling|plan-[a-z-]+|"
                       r"grant-probe-failed|driver-ping-failed|usage-repeat-notification|"
                       r"model-fallback)\b")
    groups = []
    for it in items:
        m = codes.search(it["text"])
        key = m.group(1) if m else None
        toks = tokens(it["title"])
        placed = False
        for g in groups:
            if it["report"] in {x["report"] for x in g["items"]}:
                continue
            if key and g["key"] == key:
                placed = True
            elif not key and not g["key"] and toks and g["tokens"]:
                j = len(toks & g["tokens"]) / len(toks | g["tokens"])
                placed = j >= 0.45
            if placed:
                g["items"].append(it)
                g["tokens"] |= toks
                break
        if not placed:
            groups.append({"key": key, "tokens": set(toks), "items": [it]})
    return [g for g in groups if len(g["items"]) > 1]

def fmt(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"

def digest(reports, versions):
    L = ["# Field feedback — triage digest", ""]
    L.append(f"{len(reports)} report(s). Everything below is the reporters' claims and "
             "the scripts' records — verify against the code before proposing.")
    L.append("")
    L += ["## Sources and version check", "",
          "| Report | Host | Plugin | Ran | Current | Install | Kind | Items |",
          "|---|---|---|---|---|---|---|---:|"]
    for r in reports:
        m = r["meta"]
        cur = versions.get(m.get("plugin"))
        ran = m.get("version")
        flag = "" if ran == cur else " **STALE**"
        inst = "match" if m.get("install-matches-running") == "true" else \
            f"**mismatch** (installed {m.get('installed-version')})"
        L.append(f"| `{r['rel']}` | {m.get('host')} | {m.get('plugin')} | {ran}{flag} | "
                 f"{cur or '—'} | {inst} | {m.get('kind')} | {len(r['items'])} |")
    L.append("")
    stale = [r for r in reports if r["meta"].get("version") != versions.get(r["meta"].get("plugin"))]
    if stale:
        L.append(f"**{len(stale)} report(s) ran a version other than the current release.** "
                 "Check each claim against current code before treating it as a bug "
                 "(HANDOFF section 1, first diagnostic).")
        L.append("")

    watch_ids = []
    for r in reports:
        for w in r["watch"]:
            if w not in watch_ids:
                watch_ids.append(w)
    if watch_ids:
        L += ["## Watch items", "",
              "| Item | " + " | ".join(
                  f"{r['meta'].get('host')} {r['meta'].get('date')} ({r['meta'].get('kind')})"
                  for r in reports) + " |",
              "|---|" + "---|" * len(reports)]
        for w in watch_ids:
            cells = []
            for r in reports:
                a = r["watch"].get(w)
                cells.append("—" if not a else
                             (f"**observed** — {a['evidence']}" if a["answer"] == "observed"
                              else a["answer"] or "unanswered"))
            L.append(f"| `{w}` | " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        L.append("")

    items = []
    for r in reports:
        for it in r["items"]:
            items.append(dict(it, report=r["rel"], host=r["meta"].get("host"),
                              plugin=r["meta"].get("plugin")))
    L += ["## Items", ""]
    if not items:
        L += ["_No items filed (quick bundles only)._", ""]
    for section in ITEM_SECTIONS:
        group = [i for i in items if i["section"] == section]
        if not group:
            continue
        L += [f"### {section}", ""]
        for i in group:
            flags = []
            if section == "Defects":
                for k in ("repro", "evidence"):
                    if not i["fields"].get(k):
                        flags.append(f"no {k}")
            for sid, pat in SETTLED.items():
                if re.search(pat, i["text"], re.I):
                    flags.append(f"possibly settled: {sid} — verify against HANDOFF §3")
            L.append(f"- `{i['id']}` — {i['title']}"
                     + (f" — _{'; '.join(flags)}_" if flags else ""))
            if section == "Defects" and i["fields"].get("cost"):
                L.append(f"  - cost: {i['fields']['cost']}")
        L.append("")

    reps = group_repeats([i for i in items if i["section"] in ("Defects", "Friction")])
    L += ["## Same defect, several reports", ""]
    if reps:
        for g in reps:
            L.append(f"- **{g['key'] or 'similar titles'}** — "
                     + ", ".join(f"`{i['id']}`" for i in g["items"]))
            for i in g["items"]:
                L.append(f"  - {i['host']}: {i['title']}")
    else:
        L.append("_none detected_")
    L.append("")

    seen = [(r, s) for r in reports for s in r["seen_again"]]
    if seen:
        L += ["## Seen again", ""]
        for r, s in seen:
            L.append(f"- {r['meta'].get('host')} {r['meta'].get('date')}: {s}")
        L.append("")

    codes = {}
    for r in reports:
        for code, n in ((r["summary"].get("anomalies") or {}).get("by_code") or {}).items():
            codes.setdefault(code, []).append((r["meta"].get("host"), r["meta"].get("date"), n))
    L += ["## Anomalies across bundles", ""]
    if codes:
        L += ["| Code | Bundles | Events | Where |", "|---|---:|---:|---|"]
        for code in sorted(codes, key=lambda c: (-len(codes[c]), c)):
            rows = codes[code]
            L.append(f"| `{code}` | {len(rows)} | {sum(n for _h, _d, n in rows)} | "
                     + ", ".join(f"{h} {d} x{n}" for h, d, n in rows) + " |")
    else:
        L.append("_none recorded_")
    L.append("")

    L += ["## Cost", "",
          "| Report | Rounds | Stop | Reported | Effective | Ratio | Wall | By role (effective) |",
          "|---|---:|---|---:|---:|---:|---|---|"]
    for r in reports:
        s, u = r["summary"], r["usage"]
        rep = (s.get("usage_reported") or {}).get("total")
        eff = u.get("effective_total")
        ratio = f"{eff / rep:.1f}x" if rep and eff else "—"
        wall = (s.get("window") or {}).get("wall_s")
        wall = f"{int(wall) // 3600}h{(int(wall) % 3600) // 60:02d}m" if wall else "—"
        roles = "; ".join(f"{x.get('role')} {fmt(x.get('effective'))}"
                          for x in (u.get("by_role") or [])[:6])
        L.append(f"| `{r['rel']}` | {(s.get('rounds') or {}).get('count', '—')} | "
                 f"{(s.get('stop') or {}).get('headline', '—')} | {fmt(rep)} | {fmt(eff)} | "
                 f"{ratio} | {wall} | {roles or '—'} |")
    L.append("")
    return "\n".join(L)

def main():
    args = sys.argv[1:]
    dry, every = "--dry-run" in args, "--all" in args
    out_path = None
    paths, it = [], iter(a for a in args if a not in ("--dry-run", "--all"))
    for a in it:
        if a == "--out":
            out_path = next(it, None)
        elif a in ("-h", "--help"):
            print(__doc__)
            return
        else:
            paths.append(a)

    found = []
    drop = drop_root()
    if os.path.isdir(drop):
        for host in sorted(os.listdir(drop)):
            hd = os.path.join(drop, host)
            if os.path.isdir(hd):
                found += [os.path.join(hd, n) for n in sorted(os.listdir(hd))
                          if n.endswith(".md")]
    for p in paths:
        if os.path.isdir(p):
            for dp, _dn, fn in os.walk(p):
                found += [os.path.join(dp, n) for n in sorted(fn) if n.endswith(".md")]
        elif os.path.exists(p):
            found.append(p)
        else:
            print(f"ingest: no such path {p}", file=sys.stderr)

    copied, conflicts, skipped, reports = [], [], [], []
    for src in found:
        rep = parse_report(src)
        if rep is None:
            skipped.append(src)
            continue
        if rep["meta"].get("status") != "filed":
            skipped.append(src + " (draft)")
            continue
        host = re.sub(r"[^A-Za-z0-9._-]+", "-", rep["meta"].get("host") or "unknown-host")
        dst = os.path.join(INBOX, host, os.path.basename(src))
        rep["rel"] = os.path.relpath(dst, ROOT)
        if os.path.exists(dst):
            if sha(dst) != sha(src):
                conflicts.append(rep["rel"])
            elif every:
                reports.append(rep)
            continue
        if not dry:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        copied.append(rep["rel"])
        reports.append(rep)
    if every:
        have = {r["rel"] for r in reports}
        for dp, _dn, fn in os.walk(INBOX):
            for n in sorted(fn):
                p = os.path.join(dp, n)
                rel = os.path.relpath(p, ROOT)
                if n.endswith(".md") and rel not in have:
                    rep = parse_report(p)
                    if rep and rep["meta"].get("status") == "filed":
                        rep["rel"] = rel
                        reports.append(rep)
    reports.sort(key=lambda r: (r["meta"].get("date") or "", r["meta"].get("host") or "",
                                r["file"]))

    new_ids = []
    disp = {"schema": 1, "notes": [], "items": []}
    if os.path.exists(DISP):
        with open(DISP, encoding="utf-8") as fh:
            disp = json.load(fh)
    known = {i["id"] for i in disp.get("items", [])}
    for r in reports:
        for it_ in r["items"]:
            if it_["id"] in known:
                continue
            known.add(it_["id"])
            new_ids.append(it_["id"])
            disp["items"].append({
                "id": it_["id"], "plugin": r["meta"].get("plugin"),
                "reported_version": r["meta"].get("version"), "host": r["meta"].get("host"),
                "source": r["rel"], "title": it_["title"][:120], "section": it_["section"],
                "status": "new", "version": "", "ref": "", "reason": ""})
    if new_ids and not dry:
        with open(DISP, "w", encoding="utf-8") as fh:
            json.dump(disp, fh, indent=1, ensure_ascii=False)
            fh.write("\n")

    text = digest(reports, current_versions()) if reports else \
        "# Field feedback — triage digest\n\n_No new reports._\n"
    if out_path and not dry:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    print(json.dumps({"drop": drop, "copied": copied, "conflicts": conflicts,
                      "skipped_not_reports": len(skipped), "new_item_ids": new_ids,
                      "dry_run": dry}), file=sys.stderr)
    if conflicts:
        print("ingest: CONFLICT — a report with the same name and different content is "
              "already in docs/inbox/: " + ", ".join(conflicts)
              + " — nothing overwritten; compare by hand", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
