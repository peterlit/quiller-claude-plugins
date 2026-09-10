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
findings, and a WATCH LIST.

## Loop state

All state lives in the **target repository** under `.review-loop/`:
`ledger.json` (findings ledger), `rounds.md` (per-round trend table), and
`REPORT.md` (final report). Nothing is stored in the plugin directory, so
findings never bleed between projects. Conclusions in git, evidence and
scratch on disk: the loop writes a default-closed allowlist
`.review-loop/.gitignore` — only `REPORT.md`, `ledger.json`, `rounds.md`,
and `verdict.json` are tracked (at any depth, so archived conclusions under
`archive/<name>/` stay in git), while fragments, briefs, and anything
unanticipated (a Finder-duplicated `ledger 2.json`, say) never enter the
index. Staging is by explicit file path — a hook blocks `git add -A`/`.`/
`-f`/directory adds while a loop is live — and a hygiene check at setup and
report time flags tracked scratch, duplicate names, and oversized files.
Each new loop
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

## Multi-provider review panel (0.11.0, optional)

Model pins decorrelate within one model family; the panel decorrelates
across families. When enabled, external models — OpenAI's codex CLI,
Google's gemini CLI, and/or a locally running ollama model — review the
diff as additional skeptics. They are **finders only**: each files at most
10 candidate findings (no IDs, no ledger access), a blind `panel-verifier`
agent (pinned to a third model) checks every candidate against the actual
code, and only verified findings reach the chair reviewer, tagged
`via panel:<lane>`. The panel runs on the seed diff and once more after the
loop stops (`seed+final`), so metrics and convergence are untouched.

Remote lanes require recorded consent in `.review-loop/panel-consent.json`
— an untracked, per-checkout file, so consent never travels in git and a
cloned config cannot authorize egress on someone else's machine (the diff
leaves your machine; prefer API-key auth — Gemini's free OAuth tier may
train on inputs). The local ollama lane sends nothing anywhere when
`OLLAMA_HOST` is loopback (the default); pointed at a shared GPU box it is
treated as a remote lane and needs the same consent. The report's Panel
section shows per-lane
filed/confirmed/rejected counts — measured precision, the signal for
dropping a lane that isn't earning its keep. Lane failures are always
soft: skipped with a note, never blocking a round.

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
report's **WATCH LIST** — the seed scope, each round's largest diffs, and every trap-flagged or rejected finding —
before trusting the result.
