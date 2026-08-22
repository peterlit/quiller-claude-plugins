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

## Before you start

- **A fresh session** `[both]` — the single largest measured lever: the same
  plumbing request costs ~3.3× more in a large-context session (8.5M vs
  2.6M tokens over 22 rounds). A `UserPromptSubmit` hook reports the
  transcript size whenever a loop is invoked and warns above 2 MB.
  *In practice:* start loops in a new session. If you run one inside a long
  session anyway, say so at the gate — the loop will ask.

## Loop configuration

*Surface: `.qa-loop/ledger.json`, created on first run.*

- **`max_rounds`** `[both]` (default 5; **2 in review scope mode**, auto-
  escalating to 5 if a blocker appears) — the hard iteration backstop.
  Measured: every scoped review converged by round 2–3, and DIMINISHING
  cannot fire before round 3, so a higher cap never saved anything.
  *In practice:* leave the defaults; raise it only for cold full reviews of
  large trees.
- **`token_budget`** `[both]` (default null) — a hard ceiling on cumulative
  subagent tokens. The orchestrator records each dispatch's cost
  (`set-usage`) from the task results; `rounds.md` gains a Tokens column,
  and the BUDGET stop fires (closeout + report) when the sum crosses the
  ceiling.
  *In practice:* set it to what the Stage-1 estimate quoted plus margin; the
  report then shows exactly where the money went.
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
  skip line, done. The first regression dispatch of a loop also sweeps
  `.qa-loop/archive/*/ledger.json` for previously-fixed-but-unguarded bugs,
  so turning the flag on late still captures earlier loops' fixes.

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
  `open <ledger> [auto|proposal|all|closeout] [--region WF-n]` extracts
  open/partial findings as a JSON brief (`closeout` = the closeout-eligible
  set; `--region` = only one workflow's findings, for tester chunks);
  `archive <loop-dir> [name]` moves a finished run's state into
  `archive/<name>/` so the next loop starts clean; `scope <ledger> <a..b>`
  records the change under review so the report's WATCH LIST leads with it;
  `diff <loop-dir> <N> <a..b>` materializes the round diff once for
  subagents; `set-usage` records token cost; `next-round <loop-dir> <N>
  [--fragment F]` folds merge + metrics + advance into one orchestrator
  turn (each turn re-reads the whole session context).
  *In practice:* a finding's live status is `current_status` — a top-level
  `status` field doesn't exist, which is why extraction goes through the
  `open` verb instead of hand-parsing.
- **`HARNESS_NOTES.md`** `[qa]` — simulator interaction quirks the testers
  learn (dwell-tap toggles, swipe-only sliders, screenshot scale factors),
  carried into every dispatch.
  *In practice:* pre-seed it. If you already know "the radar slider needs a
  swipe," write it in before round 1 and no tester ever rediscovers it.
- **`.phase`** `[both]` — the stall-guard marker with three honest states:
  bare `round-N-…` (a dispatch is owed; the Stop hook blocks), `…:dispatched`
  (an agent is running; stripped automatically when it returns), and
  `…:waiting:<reason>` (the orchestrator is waiting on something that isn't
  a subagent — a 529 backoff, a background task, you; the hooks leave it
  alone). Each plugin's hooks guard only their own loop directory.
  *In practice:* escape hatch — if a dead session leaves the guard armed,
  write `done` into it and the guard stands down.
- **Retry and fallback policy** `[both]` — a dispatch that dies with no
  fragment is retried up to 3× with in-turn backoff (60/180/300 s); agents
  write `<fragment>.partial` incrementally so a killed dispatch leaves its
  work, and the retry resumes from it. A pinned model is never swapped
  silently: fallback only after three failures, disclosed in the report.
  A result without its artifact (no CHANGES block, no fragment) is a pause —
  the same agent is resumed, never re-dispatched.
  *In practice:* nothing to configure; if you see "ran on <model>: outage"
  in a report, that round's adversarial diversity was reduced.
- **What to commit** `[both]` — each loop writes its own `.gitignore`
  (`evidence/`, `fragments/`, `briefs/`, `scratch/`, `.phase` stay out);
  WORKFLOWS, TESTCASES, HARNESS_NOTES, ledger, rounds, coverage, REPORT, and
  `archive/` are meant to be committed. If your repo ignores the whole loop
  directory, the loop notices (`git check-ignore`) and says so rather than
  pretending — archives then live only on that machine.
- **Minors never cost a round** `[review]` — round briefs carry blockers and
  majors only; minors (21 of 26 findings in the measured runs) accumulate and
  are fixed in the single closeout pass, where they were already eligible.
  *In practice:* nothing to set. If you want minors fixed in-round for a
  specific run, say so and the orchestrator briefs with `--severity minor`.
- **Read guard** `[both]` — while a loop phase is in flight, a `PreToolUse`
  hook denies the measured token sinks with the fix in its message: `cat` of
  a >200-line file, `head`/`sed` windows over 200 lines, unfiltered
  `xcodebuild test`/`swift test`, and re-pulling a whole diff that is already
  materialized in `briefs/round-N.diff`. Agents re-issue a windowed or
  filtered command; nothing is lost. Inactive outside loop phases.
- **Simulator discipline** `[both]` — every agent may touch only the device
  udid named in its dispatch, and never finds an app process by name
  (`pgrep -f`, `lldb -n`): other sessions' simulators share your Mac, and an
  unscoped attach once fired a memory warning into someone else's device.
  *In practice:* if you run several loops at once, this is the rule keeping
  them apart; the orchestrator names one booted device per dispatch.

- **Deterministic helpers** `[both]` — `render_report.py <loop-dir>` renders
  every mechanical REPORT.md section (trend incl. Promoted column, findings,
  proposals, rejections, persona matrix, coverage gaps, closeout); the model
  fills only the WATCH LIST. `[review]` `hotspots.py` maps git churn × size ×
  recency so cold reviews read where defects live; `mutate.py <manifest>`
  re-runs an implementer's mutation claims in an isolated worktree — "8/8
  killed" is now checkable (the implementer names its manifest in CHANGES as
  `mutations`). `[qa]` `plan_round.py` selects the targeted set and emits
  ≤5-test-case chunk manifests from `paths(WF-n)` lines in WORKFLOWS.md and
  `TC-x.y [persona] [smoke] [perf]` lines in TESTCASES.md; `nfr_analyze.py`
  turns sampler output plus the tester's `marks.jsonl` windows into numbers
  and candidate findings.
  *In practice:* you don't run these yourself — they are why the loops got
  cheaper. The two obligations they create: every workflow needs a
  `paths(WF-n): …` line (the orchestrator writes it at Stage 1), and every
  test case line must start `TC-x.y [persona]` with optional `[smoke]` /
  `[perf]` tags.

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
  then closeout. A converging series (every open finding introduced_by_fix,
  worst severity non-increasing, no reopens) no longer trips the churn
  signal at all.
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
