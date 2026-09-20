#!/usr/bin/env python3
"""Heuristic linter for ```mermaid blocks in markdown files.

Catches the common generation errors — unknown diagram type, unbalanced
brackets, unquoted special characters in flowchart labels, subgraph/end
mismatch, empty blocks — without embedding a real mermaid renderer.
Sequence diagrams: a semicolon inside Note or message text is a statement
separator to Mermaid and produces "Parse error on line N" (measured: one
shipped diagram), and a QUOTED participant alias renders with literal
quotes — both are issues. erDiagram relationship lines (||--o{ and kin)
are exempt from brace balancing; their crow's-foot glyphs are not braces.
Exit 1 if any issue is found.

Usage: mermaid_lint.py <file.md> [more.md ...]
"""
import re, sys

TYPES = ("flowchart", "graph", "sequenceDiagram", "erDiagram", "classDiagram",
         "stateDiagram-v2", "stateDiagram", "C4Context", "journey", "gantt",
         "pie", "mindmap", "timeline", "quadrantChart")

def strip_quoted(s):
    return re.sub(r'"[^"]*"', '""', s)

def lint_block(lines, path, start):
    issues = []
    body = [l for l in lines if l.strip()]
    if not body:
        return [f"{path}:{start}: empty mermaid block"]
    first = body[0].strip()
    if not first.startswith(TYPES):
        head = first.split()[0] if first.split() else "<blank>"
        issues.append(f"{path}:{start}: unknown diagram type '{head}'")
    is_flow = first.startswith(("flowchart", "graph"))
    is_seq = first.startswith("sequenceDiagram")
    is_er = first.startswith("erDiagram")
    counts = {"()": 0, "[]": 0, "{}": 0}
    subgraphs = ends = 0
    SEQ_TEXT = re.compile(r"^\s*(?:Note\s+(?:over|right of|left of)\s+[^:]+"
                          r"|[^\s:]+\s*(?:-->>|->>|-->|->|--x|-x|--\)|-\))\s*[^\s:]+)\s*:(.*)$")
    for i, raw in enumerate(lines):
        l = strip_quoted(raw)
        if is_er and re.search(r"\s(\|\||\|o|\}\||\}o)(--|\.\.)(\|\||o\||\|\{|o\{)\s", raw):
            continue   # relationship line: crow's-foot glyphs, not braces
        counts["()"] += l.count("(") - l.count(")")
        counts["[]"] += l.count("[") - l.count("]")
        counts["{}"] += l.count("{") - l.count("}")
        if is_seq:
            m = SEQ_TEXT.match(raw)
            if m and ";" in m.group(1):
                issues.append(f"{path}:{start + i + 1}: sequence text contains ';' "
                              f"(a statement separator — Mermaid parse error); use a comma or dash")
            if re.match(r'^\s*participant\s+\S+\s+as\s+"', raw):
                issues.append(f"{path}:{start + i + 1}: quoted participant alias renders "
                              f"with literal quotes — write the plain name")
        if is_flow:
            s = l.strip()
            if s.startswith("subgraph"):
                subgraphs += 1
            elif s == "end":
                ends += 1
            for m in re.finditer(r'\[([^\]"]*)\]', l):
                label = m.group(1)
                if any(ch in label for ch in "();|"):
                    issues.append(f"{path}:{start + i + 1}: flowchart label "
                                  f"needs quotes: [{label}]")
    for pair, n in counts.items():
        if n != 0:
            issues.append(f"{path}:{start}: unbalanced {pair} in block")
    if is_flow and subgraphs != ends:
        issues.append(f"{path}:{start}: {subgraphs} subgraph(s) but "
                      f"{ends} end(s)")
    return issues

def main():
    if len(sys.argv) < 2:
        print("usage: mermaid_lint.py <file.md> [...]", file=sys.stderr)
        sys.exit(2)
    issues, blocks = [], 0
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            doc = fh.read().splitlines()
        in_block, buf, start = False, [], 0
        for n, line in enumerate(doc, 1):
            fence = line.strip()
            if not in_block and fence.startswith("```mermaid"):
                in_block, buf, start = True, [], n
            elif in_block and fence.startswith("```"):
                in_block = False
                blocks += 1
                issues += lint_block(buf, path, start)
            elif in_block:
                buf.append(line)
        if in_block:
            issues.append(f"{path}:{start}: unclosed mermaid fence")
    for i in issues:
        print(i)
    print(f"mermaid_lint: {blocks} block(s), {len(issues)} issue(s)",
          file=sys.stderr)
    sys.exit(1 if issues else 0)

if __name__ == "__main__":
    main()
