# Loop Controls

Every knob across **review-loop-tools** and **qa-loop-tools**, organized by
where it lives — and what to actually do with it. Tags: `[qa]` `[review]`
`[both]`.

## Starting a loop

*Surface: the Claude Code prompt.*

- **`/qa-loop-tools:qa-loop`** `[qa]` — kicks off the UX/QA loop on the
  current repo. Say a round count in the same message to override the
  default 5.
  *In practice:* "run the qa loop, max 3 rounds, use 2 testers" sets all
  three knobs in one line — the skill reads them into ledger.json.
- **`/review-loop-tools:review-loop`** `[review]` — starts the adversarial
  code-review loop. Three seed modes: name a **scope** (a sha range, diff
  file, or PR) to review just that change; a `REVIEW.md` at the repo root
  becomes the seed findings; otherwise a cold full review of HEAD.
  *In practice:* "review-loop the changes in main..feature-x" scopes the
  whole loop to one change; paste a human review into `REVIEW.md` to make
  the loop grind through *your* list.
- **`/model`** `[both]` — your main-session model *is* the implementer's
  model (and the orchestrator's): both implementers use `model: inherit`.
  *In practice:* strongest model for real hardening; a Sonnet session for a
  cheap pass. Never run the session on a model an agent is pinned to (see
  Model pins).

## Loop configuration

*Surface: `.qa-loop/ledger.json`, created on first run.*

- **`max_rounds`** `[both]` (default 5) — the hard iteration backstop.
  *In practice:* 2–3 for a smoke pass; 5 for a real hardening run. The
  Stage-1 gate quotes a cost estimate — trim this number there if it's steep.
- **`parallel_testers`** `[qa]` (default 1, cap 3) — runs test passes across
  N isolated worker simulators. Functional checks parallelize; performance
  measurement always runs on one uncontended simulator (the perf lane). Cuts
  wall-clock roughly by N; token cost unchanged.
  *In practice:* reply "use 2 testers" at the workflow-approval gate. Use 3
  only on a beefy Mac — each simulator wants 2–6 GB of RAM.
- **`emit_regression_tests`** `[qa]` (default false) — when on, a dedicated
  regression-test-writer turns every verified-fixed bug into an XCUITest:
  real selectors mined from your source, `XCTSkip`-guarded so an unfinished
  test can't break CI, and it never touches `project.pbxproj`.
  *In practice:* turn on once the app is stabilizing and you want findings to
  become durable CI tripwires. Verify each test's selectors once, delete the
  skip line, done.

## Files that are controls

*Surface: the target repo — `.qa-loop/` and `.review-loop/`.*

- **`WORKFLOWS.md`** `[qa]` — the human-approved contract: personas,
  workflow IDs, per-workflow effort expectations ("≤3 taps for a power
  user"), the Fixture policy that pins app randomness, and persona labels.
  *In practice:* this is your main steering wheel — edit it directly at the
  gate. Effort expectations become severity calibration; the Fixture policy
  (a launch arg, a seed, a deal picker) makes repros replayable; mark a
  workflow single-persona to waive the both-personas test minimum.
- **`ledger.json` routing flip** `[qa]` — to accept a UX proposal, edit its
  finding: `"routing": "proposal"` → `"auto"`, then re-run. Acceptance
  automatically triggers a design-intent check that emits constraints the
  implementation must satisfy.
  *In practice:* the only ledger surgery you should ever do by hand;
  everything else merges through scripts.
- **`merge_ledger.py` verbs** `[both]` — the only sanctioned ledger
  mutations: `resolve <ledger> <id> <status> <round> "<note>"` records a
  human decision (close a finding you've already decided against so agents
  stop re-filing it); `set-round <ledger> <N> [sha]` does round bookkeeping;
  `open <ledger> [auto|proposal|all]` extracts open/partial findings as a
  JSON brief; `archive <loop-dir> [name]` moves a finished run's state into
  `archive/<name>/` so the next loop starts clean.
  *In practice:* a finding's live status is `current_status` — a top-level
  `status` field doesn't exist, which is why extraction goes through the
  `open` verb instead of hand-parsing.
- **`HARNESS_NOTES.md`** `[qa]` — simulator interaction quirks the testers
  learn (dwell-tap toggles, swipe-only sliders, screenshot scale factors),
  carried into every dispatch.
  *In practice:* pre-seed it. If you already know "the radar slider needs a
  swipe," write it in before round 1 and no tester ever rediscovers it.
- **`.phase`** `[both]` — the stall-guard marker; a Stop hook blocks the
  orchestrator from ending its turn while it reads `round-…`.
  *In practice:* escape hatch — if a dead session leaves the guard armed,
  write `done` into it and the guard stands down.
- **What to commit** `[qa]` — the loop writes its own `.qa-loop/.gitignore`:
  `evidence/`, `fragments/`, and `.phase` stay out; WORKFLOWS, TESTCASES,
  HARNESS_NOTES, ledger, rounds, coverage, and REPORT are meant to be
  committed.

## Model pins

*Surface: `agents/*.md` frontmatter.*

- **ux-tester: `opus` · fix-reviewer: `sonnet` · implementer: `inherit`**
  `[qa]` — three seats, three models: the loop's guard against correlated
  blind spots. The review loop pins its skeptical-reviewer to `opus` against
  the inheriting implementer. `[review]`
  *In practice:* one rule — keep all pins distinct from each other **and**
  from your session model. Switch your session to Opus? Move the tester's
  pin. Fix-reviewer rejecting too much? Its pin is the tuning knob before
  you weaken the rejection policy.

## Commit guard

*Surface: environment variables, set in the session — not committed.*

- **`REVIEW_LOOP_MAX_DIFF`** `[both]` (default unlimited) — blocks any
  implementer commit whose staged diff exceeds N lines.
  *In practice:* set ~400 for unattended runs — a runaway "fix" that
  rewrites half the app gets stopped at the commit, not discovered in the
  report.
- **`REVIEW_LOOP_TEST_CMD`** `[both]` (default off) — a command that must
  exit 0 before any commit is allowed.
  *In practice:* point it at your fast unit suite; keep it under a minute or
  every round crawls.

## During a run

*Surface: the live session.*

- **The Stage-1 gate** `[qa]` — the loop's only blocking stop: it announces
  `max_rounds`, `parallel_testers`, and a cost estimate (recalibrated with
  actuals after round 1), then waits for your workflow sign-off.
  *In practice:* this is where you steer — edit WORKFLOWS.md, change
  settings, or trim rounds with real numbers in hand. After this it runs
  autonomously.
- **`FIX REJECTED: <id> — <reason>`** `[qa]` — the fix-reviewer found a fix
  that satisfies the finding but harms the product (gameable metric,
  corrupted state). The finding reverts to open; the implementer retries
  next round with the rejection as its brief.
  *In practice:* read these when they appear — a rejection often means the
  *finding* was a trap and belongs in proposals for a human decision.
- **`thrashing_soft`** `[both]` — thrashing signals with mitigating progress
  (0 open blockers, positive closes) now pause and ask you — abort with the
  report, or one more round? — instead of hard-aborting. A second thrashing
  signal after you approve a continuation is final.
  *In practice:* say "one more round" when the open findings are cheap and
  the trend is genuinely converging; take the abort when findings are
  reopening. Unattended runs don't wait: the default is abort-with-report,
  then closeout.
- **CLOSEOUT** `[review]` — after any stop, one mop-up cycle fixes and
  re-verifies the leftover cheap findings: open `introduced_by_fix` findings
  (any severity — the loop's own regressions never ship to BACKLOG
  unexamined) plus open minors. One implementer dispatch, one targeted
  reviewer verification, no iteration; failures land in BACKLOG.md with
  notes and the report gets a Closeout section.
  *In practice:* nothing to configure — it runs when eligible findings
  exist. Open majors that aren't introduced_by_fix are deliberately excluded:
  they stopped the loop for a reason you should read.
- **Interrupting** `[qa]` — killing a round is always safe. Durable state:
  ledger, merged fragments, coverage, docs. Resume restarts the round from
  its deterministic reset.
  *In practice:* Esc without fear. Also: a quiet transcript isn't a dead
  loop — check the background-task list before assuming a stall.

## Reading the report

*Surface: `.qa-loop/REPORT.md` — the parts a human must actually read.*

Skim in this order:

1. **WATCH LIST** — the most invasive diffs and every trap-flagged
   (`fix_risk`) finding.
2. **UX PROPOSALS** — behavior changes awaiting your call.
3. **FIX REVIEW REJECTIONS** — every fix the reviewer shot down.
4. **COVERAGE GAPS** — blocked/skipped test cases with reasons.
5. **PERSONA MATRIX** — the workflow × persona table, where a "both"
   workflow tested by one persona shows as a hole.

CONVERGED is only ever declared after a verified full pass — but the WATCH
LIST exists because decorrelated reviewers reduce, not eliminate, the chance
of agents agreeing on a bad fix. Ten minutes here is the human half of the
contract.

## Playbooks

- **First run on a new app** — all defaults. Spend your effort at the gate:
  fix workflow effort expectations, pin the Fixture policy, pre-seed
  HARNESS_NOTES. Check the cost estimate before saying go.
- **Cheap smoke pass** — `max_rounds 2`, Sonnet session, no regression
  tests. The opus tester still finds real issues; you're trading implementer
  depth for cost.
- **Pre-release deep audit** — "use 3 testers", `max_rounds 5`,
  `emit_regression_tests true`, `REVIEW_LOOP_TEST_CMD` set. Budget a workday
  of wall-clock and read every report section.
- **Accepting a proposal** — flip its `routing` to `"auto"` in ledger.json,
  re-run. Intent check emits constraints → implementer must satisfy them →
  fix review verifies each one. Check the next report's rejection section.
