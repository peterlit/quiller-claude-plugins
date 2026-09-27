---
name: feedback
description: Files a field report on the architecture-docs run for the plugin maintainer — the plugin version that actually ran, verdicts, anomalies and measured token cost, plus what worked, what broke and what was decided without a human. Invoke after a docs run finishes, or when the user asks for feedback on the architecture-docs run, a field report, or a plugin bug report. Pass --quick for the objective bundle alone.
---
You are filing a field report for the MAINTAINER of arch-docs-tools — not for the
owner of this repo. The report is about the plugin: what it did well, where
it failed or cost effort, what you decided on your own. It is never about
the app's findings, and it never quotes source code or finding claims.

The script does the mechanical half. You supply only what you observed in
THIS run. An empty section is a good answer; a guess is not.

## Quick bundle (`--quick`, or the user asked for "just the numbers")

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/feedback.py quick docs/architecture`

It writes the report, copies it to the drop, and prints the path. Go to
step 5. No questions, no writing — this is the floor, and it is worth
filing even when you have nothing to add.

## Full report

1. Scaffold:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/feedback.py scaffold docs/architecture`
   It reads the run summary the report stage wrote (building it now if the
   run predates that), measures effective tokens per role from this repo's
   session transcripts, and writes a DRAFT with every section laid out. It
   prints the draft's path. Name the docs directory the run wrote to if it was not `docs/architecture`.
   If it says the usage window is unknown, re-run with `--since <when the
   docs run started>` (ISO time or epoch seconds).
2. Read two sections of `${CLAUDE_PLUGIN_ROOT}/FIELD-QUESTIONS.md` before
   writing a word: **Settled decisions** and **Open and recently shipped
   items**. A defect that re-raises a settled decision without new numbers
   is declined unread; an item already listed belongs under "Seen again",
   by its id, not re-described.
3. Fill in the draft with the Edit tool. Write BELOW each guide comment.
   - **Watch items**: answer every one — `observed`, `not observed`, or
     `n/a` (the run never reached the situation) — with one line of
     evidence when observed. Answer from the loop's files, not from memory:
     `feedback/run-summary.json` (split, diagram counts, lint and coverage numbers) and the documents themselves.
   - **Defects**, in impact order: what happened, what was expected, the
     smallest repro, an evidence path, the cost, a mechanism if you have
     one. A defect with no repro and no evidence is triaged last.
   - **Decisions taken without the human**: every place the skill wanted a
     person and you chose instead — what was wanted, what you chose, why.
   - **Environment and harness artifacts**: what went wrong that was NOT
     the plugin's fault. Your call here is where the maintainer's triage
     starts, so make it deliberately.
   - Keep, Friction, Seen again, Host-repo recommendations, Wishes: as the
     guide comments say. Leave a section empty if you have nothing.
   Do not write item ids yourself, do not edit the front matter, and do not
   paste the run summary — finalize does all three.
4. Finalize:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/feedback.py finalize docs/architecture`
   It refuses a report with unanswered watch items (fix and re-run), mints
   an id per item, appends the summary and usage as fenced JSON, and copies
   the file to the maintainer's machine-local drop. Relay its warnings.
5. Commit the conclusions BY EXPLICIT PATH — the `stage_by_path` line
   finalize printed, then a commit of exactly those files (message:
   `docs: arch-docs-tools field report <date>`). Never `git add -A`, never a
   directory add. If finalize reported `git_ignored: true`, skip the commit
   and say so: the drop copy is the delivery.
6. Tell the user, in three lines: the report's path, the drop path, and
   the item ids with their titles. Nothing is sent anywhere — the drop is a
   directory on this machine that the maintainer's ingest reads.

## Rules
- Report only what this run showed. If you did not see it, it did not
  happen; if you are unsure, say so in the item.
- This is never a gate. If the user declines, stop; the docs run's result does
  not depend on a report being filed.
- Record deviations WHEN THEY HAPPEN, not here:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/field_log.py anomaly docs/architecture workaround "<one line>"`
  — by report time the details are already gone.
