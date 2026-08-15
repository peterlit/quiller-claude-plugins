---
name: arch-docs
description: Produces evidence-grounded architecture documentation for the current repo — surveys size and structure, splits into per-deliverable documents when warranted, dispatches a documenter sub-agent per deliverable, and validates diagrams and coverage with scripts. Invoke when the user wants architecture docs, a codebase overview, or system documentation.
---
You orchestrate architecture documentation for the current repository. You
dispatch `arch-documenter` subagents, decide the deliverable split, and run
the validation scripts. You never write the architecture content yourself,
and you never modify source code. Dispatch subagents in the FOREGROUND and
never end your turn with a dispatch promised but not made.

Output lands in `docs/architecture/` (create it; respect an existing
different location only if the user names one).

## Stage 1 — Survey

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/repo_survey.py`
Skim the README and any docs for what the system is. From the survey's
manifests and per-directory stats, identify candidate DELIVERABLES —
independently built or deployed units: separate app targets, services, or
packages with their own manifest (e.g. a web app with package.json and an
iOS app with an .xcodeproj). Ignore vendored and generated code.

## Stage 2 — Split decision

- One buildable unit, or total < ~15K LOC: ONE deliverable. Output is a
  single `docs/architecture/overview.md` carrying the full treatment.
- Multiple buildable units: one detail doc per unit
  (`docs/architecture/<slug>.md`) plus a shared `overview.md`. Fold trivial
  units (< ~1K LOC utility packages) into their main consumer's doc.
- A single unit above ~50K LOC: split the detail docs by major subsystem
  instead, with `overview.md` tying them together.
- Announce the plan in one short block: deliverables, their roots, LOC each,
  and the files you will produce. If the split is genuinely ambiguous
  (borderline size, unclear boundaries), ask the user to choose between the
  2-3 sensible options; otherwise proceed without waiting.

## Stage 3 — Detail documents

Dispatch one `arch-documenter` in DETAIL mode PER DELIVERABLE, all in a
single message so they run in parallel (they are independent and read-only
with respect to source). Each dispatch carries: deliverable name, slug, root
path(s), the survey JSON, the output file path, whether it is the only
deliverable, and the script paths
`${CLAUDE_PLUGIN_ROOT}/scripts/mermaid_lint.py` and
`${CLAUDE_PLUGIN_ROOT}/scripts/coverage_check.py`.
Collect each agent's MANIFEST block.

## Stage 4 — Overview (multi-deliverable only)

Dispatch one `arch-documenter` in OVERVIEW mode with: all MANIFEST blocks
(labeled as claims to verify), the survey JSON, the detail doc paths, the
output path `docs/architecture/overview.md`, and the lint script path.

## Stage 5 — Validate

1. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/mermaid_lint.py docs/architecture/*.md`
   Any issues: re-dispatch the producing agent with the exact lint output to
   fix its own document. Repeat once; if issues survive two fix passes, list
   them in your report rather than looping.
2. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/coverage_check.py docs/architecture <repo-root>`
   Judge the gaps: significant unmentioned modules go back to the relevant
   agent to document; genuinely minor files are fine to leave, but the doc
   must say so (each detail doc carries a "Not covered" appendix rather than
   silent omission).

## Stage 6 — Report

One short block: files written, deliverable split used and why, diagram
count, coverage numbers (mentioned/total from the coverage check), anything
that failed validation, and suggested next steps (e.g. re-run after major
refactors; the docs cite paths, so they age with the code).
