# review-loop-tools

A Claude Code plugin that runs an **adversarial implementer/reviewer convergence
loop**: a skeptical reviewer finds problems, an implementer fixes (or argues
against) them, and the loop repeats until the codebase converges — with
thrashing detection and a hard iteration backstop so it can't spin forever.

## How it works

Three roles:

1. **Orchestrator (main agent)** — pure plumbing. It never edits source code
   itself. It dispatches the two subagents, records loop state, runs the metrics
   script, and decides whether to continue. Crucially, the reviewer's input each
   round is the **raw diff computed by git** (`git diff <round_start_sha>..HEAD`),
   never the orchestrator's summary of what changed; the implementer's claims
   travel alongside, labeled as unverified claims.
2. **`implementer` subagent** — addresses open findings with engineering
   judgment: fixes what's real, declines false positives with a concrete
   technical reason, builds and tests, and commits each round.
3. **`skeptical-reviewer` subagent** — a hostile pre-production reviewer that
   assumes the code is flawed, validates the implementer's claims against the
   actual code, and maintains a structured findings ledger.

Each round the metrics script computes a verdict: **converged**, **thrashing**
(oscillation — abort and escalate to a human), **stalemate** (stable
disagreements), **diminishing** (returns too small to continue), **backstop**
(max rounds hit), or **continue**.

## Usage

```
/review-loop-tools:review-loop
```

Optionally tell it a max round count (default 5). At the end it writes
`.review-loop/REPORT.md` with the stop condition, trend table, open/disputed
findings, and a HUMAN SKIM LIST.

## Loop state

All state lives in the **target repository** under `.review-loop/`:
`ledger.json` (findings ledger), `rounds.md` (per-round trend table), and
`REPORT.md` (final report). Nothing is stored in the plugin directory, so
findings never bleed between projects. The loop writes its own
`.review-loop/.gitignore` (`fragments/`, `briefs/`, `.phase`); the ledger,
trend table, report, and `archive/` are meant to be committed. Each new loop
archives the previous run's state into `.review-loop/archive/<name>/`
automatically, and after any stop a **closeout** cycle fixes and re-verifies
leftover cheap findings (the loop's own `introduced_by_fix` regressions and
open minors) so they don't ship to BACKLOG unexamined.

## Model configuration

The **implementer** uses `model: inherit` — it runs on whatever model you select
for your main session (via `/model`). The **reviewer** is pinned to a fixed
model in its frontmatter (`agents/skeptical-reviewer.md`) so the two agents run
on different models, a partial guard against correlated blind spots.

*if you run your main session on the same model the reviewer is pinned
to, implementer/reviewer model diversity silently collapses — edit the reviewer's
`model:` pin (in `agents/skeptical-reviewer.md`) to restore it.*

## Every knob in one place

[CONTROLS.md](CONTROLS.md) ships with the plugin: all settings, file-based
controls, model pins, env vars, and playbook recipes for both loop plugins.
In a session, ask `/review-loop-tools:controls` and Claude answers from the
shipped reference.

## Token efficiency and hooks

Findings JSON never transits the orchestrator: the reviewer writes its LEDGER
to `.review-loop/fragments/` and `scripts/merge_ledger.py` merges it
deterministically. The reviewer also computes the round diff itself from a sha
range, so the diff enters only the context that reads it. Two hooks guard the
loop at zero token cost: a `Stop` hook blocks the orchestrator from ending its
turn while a round is in flight (tracked via `.review-loop/.phase`), and a
`SubagentStop` hook validates fragment JSON before a subagent may finish.

## Checkable claims and cheaper reports

Three scripts move judgment-free work out of the models: `render_report.py`
generates every mechanical section of REPORT.md (the orchestrator fills only
the WATCH LIST), `hotspots.py` gives a cold review a churn-ranked map of
where defects concentrate, and `mutate.py` re-runs an implementer's
mutation-testing claims in an isolated `git worktree` from a manifest the
implementer names in its CHANGES block — so "8/8 mutants killed" is
verified, not trusted. The trend table also gains a Promoted column so a
severity promotion on new evidence no longer looks like a regression.

## Measured cost controls (0.7.0)

Two instrumented studies showed the loop's cost is tool output written into
context (66%) and orchestrator turns in large sessions (3.3×), not model
reasoning. 0.7.0 acts on that: a `read_guard` hook denies whole-file dumps,
unfiltered test runs, and whole-diff re-pulls during a loop (with the fix in
its message); the round diff is materialized once (`diff` verb); rounds run
the implementer's scoped `verify_cmd` and the full suite runs once at
closeout; `next-round` folds merge + metrics + advance into one turn and an
Agent-tool hook stamps `:dispatched`; a `session_guard` hook warns when a
loop is started in a large session; minors skip rounds and go to closeout;
scope mode defaults to 2 rounds with blocker escalation; `set-usage` records
per-round tokens for a Tokens column and an optional `token_budget` stop.

## Optional commit guard

A `PreToolUse` hook (`scripts/commit_guard.sh`) can block oversized or
test-failing commits during unattended rounds. It's advisory — the loop works
without it. Configure via environment variables (set in the repo/session, not
committed):

- `REVIEW_LOOP_MAX_DIFF` — max staged changed lines allowed per commit
  (default: unlimited).
- `REVIEW_LOOP_TEST_CMD` — a test command that must pass before a commit is
  allowed.

## Caveat: read the report

Because the implementer and reviewer are the same model family, the loop
**cannot catch both agents agreeing on a wrong fix**. A human should skim the
report's **HUMAN SKIM LIST** — the 3–5 most invasive diffs across all rounds —
before trusting the result.
