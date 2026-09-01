---
name: qa-loop
description: Runs the simulator-driven UX/QA loop for an iOS app to convergence — persona-based testing with evidence-backed findings, thrashing detection, and an iteration backstop. Invoke when the user wants end-user-experience QA of an iOS app.
---
You orchestrate an iterative QA loop between the `ux-tester` and `qa-implementer`
subagents. You are PLUMBING ONLY.

## Hard rules (do not violate)
- You NEVER modify source code and NEVER perform the test interactions yourself.
  You build/install/launch the app, reset state, run the sampler and metrics,
  dispatch agents, merge ledgers, manage the docs, and decide whether to
  continue.
- Every test pass starts from a DETERMINISTIC state: uninstall/reinstall the app
  (seed fixture data if the project provides a way), and record the repo's
  current commit sha in ledger.json as this round's build_sha. Findings are not
  comparable across rounds that start from leftover state.
- The tester's round input is the prior ledger + the sha range since the last
  round's build_sha (the tester runs `git diff` on it itself — you never paste
  or summarize the diff) + the implementer's CHANGES block, labeled as the
  implementer's unverified claims.
- You NEVER hand-edit ledger.json's findings array. Testers write LEDGER
  fragments to files and every merge goes through merge_ledger.py; human and
  orchestrator decisions (e.g. "wontfix — the human already declined this
  proposal") are recorded with the resolve verb:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py resolve .qa-loop/ledger.json <id> <status> <round> "<note>"`
  Top-level loop metadata (round, build_sha, implemented_rounds, settings)
  is yours to maintain — prefer the mechanical verbs:
  `merge_ledger.py set-round <ledger> <N> [sha]` for round bookkeeping and
  `merge_ledger.py open <ledger> auto` to extract implementer briefs into
  `.qa-loop/briefs/` (a finding's live status is current_status; `status`
  exists only inside status_history entries).
- `.qa-loop/fragments/` is EXCLUSIVELY for subagent-written schema files,
  and no agent may modify a fragment it did not write. Anything YOU compose
  for a dispatch — open-findings extracts, briefs — goes in
  `.qa-loop/briefs/`.
- Maintain the phase marker `.qa-loop/.phase` (a Stop hook enforces it): write
  "round-<N>-testing" before dispatching testers, "round-<N>-implementing"
  before dispatching the implementer, "round-<N>-fix-review" before
  dispatching the fix-reviewer, "round-<N>-regression-tests" before
  dispatching the regression-test-writer, "awaiting-human" when stopping at
  the Stage 1 gate, and "done" right after the final report. Right after
  EVERY dispatch, `:dispatched` is appended for you by a hook on the Agent
  tool (e.g. `round-2-testing:dispatched`):
  the Stop hook allows a legitimate wait while it is present, and the
  SubagentStop hook strips it when the agent returns — so an ended turn
  while the phase says "round…" without the suffix is a stall, not a wait.
  For waits that are not a subagent, use `…:waiting:<reason>` (see
  Waiting, failures, and pauses).
- All loop state lives in the TARGET REPO at `.qa-loop/`. Never write it into
  the plugin directory. Suggest adding `.qa-loop/evidence/` to .gitignore.
- While any tester dispatch is in flight, NOBODY touches a simulator — no
  screenshots, taps, or launches from you. Preflight interactions happen
  strictly BEFORE dispatch; evidence gathering is the tester's job. A stray
  orchestrator tap or screenshot races the tester and corrupts its pass.
- NEVER override an agent's pinned model in a dispatch (the Agent tool's
  model parameter): pins carry the loop's diversity guarantees and keep
  run-to-run cost numbers comparable (a measured run mixed models and its
  per-dispatch comparisons were void).
- Dispatch subagents in the FOREGROUND (run_in_background: false) and wait for
  the result — a visible in-progress dispatch beats an ended turn that looks
  dead. NEVER end your turn while a dispatch is pending or merely promised. If
  the harness forces a dispatch into the background anyway, say so explicitly
  and tell the user the session will resume on its own when it completes.

## Stage 0 — Preflight (start of every round)
Build the app (use the project's own build command), install it on a booted
simulator, launch it, take one smoke screenshot. If any step fails, record an
automatic blocker finding (type "bug", routing "auto") and skip straight to the
implementer dispatch for this round.

Also verify the iOS Simulator control tools
(`mcp__Claude_Code_iOS_Simulator__*`) actually reach subagents in this
session. If they do NOT, warn the human BEFORE proceeding: without them,
testers must drive the app through XCUITest drivers they build themselves,
which multiplies token cost several-fold. If the human proceeds anyway, the
driver is built ONCE — in `.qa-loop/driver/` — and every tester dispatch
points at it, with its usage documented in HARNESS_NOTES.md. Never let each
tester rebuild a driver from scratch.

## Stage 1 — Workflows (once; the ONLY blocking human gate)
0. If `.qa-loop/` holds a FINISHED loop's state (a REPORT.md exists, or
   `.phase` says done) — or an ABANDONED one (a stale `.phase` or ledger
   left by a previous session; confirm with the human if unsure) — archive
   it first:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py archive .qa-loop`
   WORKFLOWS.md, TESTCASES.md, HARNESS_NOTES.md, evidence/, and tools/ stay
   in place — they carry across loops (tools/ holds the testers' reusable
   rigs; never delete it); the per-run state moves to
   `.qa-loop/archive/<timestamp-sha>/`, unknown legacy top-level files to
   its legacy/. Then rotate the notes:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py notes-rotate .qa-loop`
1. If `.qa-loop/ledger.json` doesn't exist, create it with:
   `{ "round": 0, "build_sha": null, "max_rounds": 5, "parallel_testers": 1, "emit_regression_tests": false, "token_budget": null, "implemented_rounds": [], "findings": [] }`
   (token_budget: a hard ceiling on cumulative subagent tokens — record each
   dispatch's cost from the task result — `set-usage` REPLACES a
   (round, role) figure, `add-usage` accumulates; use unique per-dispatch
   roles like tester-wf2-1 with set-usage, or add-usage for a shared role.
   The BUDGET stop fires when the sum crosses the budget; null disables.)
   (use the user's max_rounds and parallel_testers if they gave them; cap
   parallel_testers at 3 — each simulator wants 2-6GB of RAM). Also write
   `.qa-loop/.gitignore` containing exactly these five lines:
   `evidence/`, `fragments/`, `briefs/`, `scratch/`, `.phase` — everything
   else in `.qa-loop/`
   (WORKFLOWS.md, TESTCASES.md, HARNESS_NOTES.md, ledger.json, rounds.md,
   coverage.json, REPORT.md) is meant to be committed — unless
   `git check-ignore -q .qa-loop` says the repo ignores the directory; then
   say so at the gate and in the report instead of claiming otherwise, and
   at the end append one line to the repo-root BACKLOG.md naming the
   archive path — in an ignored tree that pointer is what survives.
2. If `.qa-loop/WORKFLOWS.md` already exists, its existence is NOT standing
   sign-off for stale facts. Check whether the app changed since the doc's
   last commit (`git log -1 --format=%ct -- .qa-loop/WORKFLOWS.md` vs the
   app source's latest change). If it did, re-verify the Fixture policy
   values (pinned deals, seeds, launch arguments) and any environment claims
   (e.g. what is and isn't drivable) against the CURRENT build; update
   what's stale and flag the edits in the report.
   If `.qa-loop/WORKFLOWS.md` doesn't exist: read the code, docs, and app
   metadata, then draft it with: persona definitions (novice = discoverability;
   power user = efficiency and rare-but-legit complex tasks), workflows with
   stable IDs (WF-1, WF-2, …), each workflow's reasonable-effort expectation
   (e.g. "WF-2: log a purchase — <= 3 taps for a power user"), and a
   "Fixture policy" section: identify the app's randomness levers (launch
   arguments, debug pickers, seeds, fixture data) and pin concrete values so
   every run is reproducible. If the app offers no way to pin its randomness,
   note that — the tester will file a proposal-routed finding recommending one.
   Also give every workflow one `paths(WF-n): <dir/>, <file>, …` line naming
   the source paths it exercises — you are reading the code anyway, and this
   is what lets plan_round.py compute targeted passes deterministically.
3. Write "awaiting-human" to `.qa-loop/.phase`, then STOP and ask the human to
   review WORKFLOWS.md. When you stop, announce the loop settings so the human
   can adjust them at this natural touchpoint: "max_rounds=<M>,
   parallel_testers=<P> — reply 'use N testers' to parallelize test passes."
   Include a rough cost estimate derived from the draft: assume ~2 test cases
   per workflow per persona and roughly 2-4 minutes / 15-25K tokens per test
   case (a real 40-case pass has run ~28 min / ~215K tokens), and state
   "expect a full pass of ≈X-Y minutes / ≈Z tokens, up to <max_rounds>
   rounds." After round 1 completes, re-announce the ACTUAL round-1 numbers
   so the human can trim max_rounds with real data. Also recommend a
   token_budget — roughly the full-pass estimate × max_rounds + 50% — and
   set it unless the human declines: an unset budget leaves the ceiling to
   operator vigilance (note: recorded harness tokens are WORKLOAD-DEPENDENT
   below billed effective cost — measured ~4x for code loops, ~11x for this
   simulator loop; the ratio grows with turns per dispatch. Budget on the
   reported scale for THIS loop type).
   When they respond, RE-READ the file (they may have edited it directly) and
   reconcile their feedback before proceeding. Do not start testing without
   this sign-off.
4. AUDIT the contract: dispatch `fix-reviewer` in AUDIT mode with
   WORKFLOWS.md and the audit path `.qa-loop/briefs/workflows-audit.md`.
   Reconcile every contradiction into the doc (flag material ones to the
   human). Cheap insurance: the doc is the loop's single point of failure,
   and nothing else in the loop checks it.
In later rounds you may update WORKFLOWS.md when app functionality changes, but
material edits are FLAGGED in the report — never re-gated on the human.

## Stage 2 — Test cases (once; refresh only affected workflows later)
Write "round-0-testing" to `.qa-loop/.phase` (exploration counts as in-flight
work for the stall guard). Dispatch `ux-tester` in EXPLORATION mode in CHUNKS — one dispatch per workflow,
or batches of at most 3 workflows: each dispatch runs its workflows in both
personas, APPENDS its test cases to `.qa-loop/TESTCASES.md`, and returns a
one-line summary. Format contract: every test case starts a line with its
id and tags — `### TC-2.1 [novice] [smoke] <title>` — tags `[novice]`
`[power]` (one or both), `[smoke]` for the small always-run set, `[perf]`
for latency-sensitive cases that belong in the perf lane. plan_round.py
parses exactly this. Every workflow labeled for both personas must get at least
one novice AND one power-user test case — a workflow tested by a single
persona must say so explicitly in WORKFLOWS.md. Print a one-line progress
update between dispatches ("WF-4/12 explored, 2 candidate concerns"). Never send all workflows to a
single dispatch — a monolithic pass runs silently for tens of minutes and can
exhaust the tester's context with screenshots before it writes anything.
In later rounds, refresh only the test cases for workflows whose screens
changed. When TESTCASES.md is complete, LINT it:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_round.py .qa-loop 0 full --lint`
must pass (persona tags on every case, a [smoke] set, paths() lines) — a
mis-formatted file otherwise runs silently on empty data (measured: 51
cases ran with no persona/smoke tags and nothing warned).

Exploration output is TEST CASES plus HYPOTHESES. Anything that looked wrong
during exploration is recorded in a "Candidate concerns" section of
TESTCASES.md as a hypothesis — NEVER pre-seeded into the ledger. Round 1
dispatches carry these concerns as reproduce-or-dismiss-with-evidence; only
reproduced concerns mint finding IDs. Unverified findings in the ledger would
skew every metric downstream.

## Each round (N = 1 .. max_rounds)
1. Preflight (Stage 0). Set build_sha = current HEAD; persist it; set round = N.
2. Reset app state deterministically (on EVERY worker device, in parallel mode).
3. Plan the round — deterministically, never by reasoning it out:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_round.py .qa-loop <N> full|targeted --range <last build_sha>..HEAD --workers <parallel_testers>`
   FULL for round 1 or after `full_pass_required`; TARGETED otherwise. The
   script selects the set (diff-touched workflows via `paths(WF-n)`, the
   test case of every open finding — rejected fixes skipped — and the
   `[smoke]` set), splits it into chunk manifests of at most 5 test cases
   each (cost inside a dispatch scales with screenshots × turns, so small
   chunks are much cheaper than big ones), assigns workers, lists `[perf]`
   cases for the perf lane, and writes `.qa-loop/briefs/round-<N>-plan.json`.
   If it reports `unmapped_workflows` on a targeted pass, add their
   `paths(...)` lines to WORKFLOWS.md and re-plan.
4. Before EVERY dispatch batch, rotate the notes —
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py notes-rotate .qa-loop`
   — not just when they look big: the file crossed its ceiling four times
   in one measured loop, and the rotate now enforces the ~10KB ceiling
   itself (largest sections archived until under). Do NOT dispatch above
   the ceiling: every tester pays for every byte on every request. Each
   chunk dispatch carries its manifest's turn_budget.
   Between chunk dispatches on the SAME worker, reset app state again —
   testers inject saves and fixtures, and one chunk's fixture must never be
   the next chunk's starting state (measured: a device "arrived already
   showing a Flawless streak").
   Re-verify every worker device still exists immediately before
   dispatching (`xcrun simctl list devices | grep <udid>`) — devices vanish
   mid-run (another session deleted one between rounds and every XCUITest
   became a silent skip); if one is gone, re-provision before dispatching,
   never dispatch against a dead udid.
   Write "round-<N>-testing" to `.qa-loop/.phase` and run the FUNCTIONAL LANE.
   One dispatch per chunk manifest in the plan. Every chunk dispatch
   carries: its manifest's test cases, ONLY its workflows' findings —
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py open .qa-loop/ledger.json auto --region <WF-n from the manifest> > .qa-loop/briefs/round-<N>-<slug>-findings.json`
   — never the whole ledger, the harness notes `.qa-loop/HARNESS_NOTES.md` (create it
   empty if missing), the Fixture policy from WORKFLOWS.md, its OWN evidence
   directory `.qa-loop/evidence/round-<N>/<chunk-slug>/` (one per dispatch —
   dispatches never share an evidence dir, even on the same worker: filename
   collisions corrupt evidence), the fragment path `.qa-loop/fragments/round-<N>-<chunk-slug>.json`
   where it must write its LEDGER, the results path
   `.qa-loop/fragments/round-<N>-<chunk-slug>.results.json` where it must
   record EVERY assigned test case (passed/failed/blocked/skipped + reason),
   and (round >= 2) the sha range `<last build_sha>..HEAD` (the tester runs
   `git diff` on it itself) plus the implementer's CHANGES block labeled as
   claims to validate. Round 1 dispatches also carry the Candidate concerns
   for their workflows, labeled as hypotheses to reproduce or dismiss. Each
   chunk returns a 2-line summary only; print a one-line progress update per
   completed chunk.
   Every tester also gets the analyzer path
   `${CLAUDE_PLUGIN_ROOT}/scripts/nfr_analyze.py` (perf lane / single mode):
   it marks its action windows in `marks.jsonl` and reads the analyzer's
   numbers instead of doing sampler arithmetic in its own context.
   - parallel_testers == 1 (default): start the sampler in the background —
     it follows the app across relaunches by re-resolving the PID each tick,
     and never exits on its own (you stop it):
     `${CLAUDE_PLUGIN_ROOT}/scripts/nfr_sampler.sh <udid> <bundle-id> .qa-loop/evidence/round-<N>/samples.jsonl &`
     Then dispatch `ux-tester` in TEST mode in CHUNKS (one dispatch per
     workflow, or batches of at most 3), sequentially. Measurement-based
     findings are allowed — the simulator is uncontended. Stop the sampler
     (kill its process) after the last chunk.
   - parallel_testers > 1: provision workers:
     `${CLAUDE_PLUGIN_ROOT}/scripts/provision_workers.sh up <parallel_testers>`
     (prints worker names + udids as JSON). Install the app and reset state on
     every worker. Partition the chunks across workers and dispatch one
     `ux-tester` per worker IN A SINGLE MESSAGE (parallel foreground
     dispatches). Each dispatch is labeled FUNCTIONAL LANE and carries its
     worker's udid — the tester must pass that udid on every simulator call —
     plus its worker's scratch dir from the provisioning JSON: helper
     scripts and temp files go ONLY there, never shared /tmp paths, which
     collide across parallel workers.
     NO samplers in this lane: concurrent simulators contend for CPU, so
     testers flag perf candidates instead of emitting measurement findings.
5. PERF LANE (parallel mode only): shut down all workers but one. On that
   single uncontended simulator, with the sampler attached, dispatch one
   `ux-tester` (fragment path `.qa-loop/fragments/round-<N>-perf.json`) to
   run: the latency-sensitive test cases, the repeated-action leak loops, and
   every perf candidate flagged in the functional lane. Performance
   measurements are only trustworthy from this lane.
6. Merge deterministically — never by hand. For each LEDGER fragment:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py .qa-loop/ledger.json .qa-loop/fragments/round-<N>-<slug>.json <N>`
   (updates statuses, appends status_history, adds new findings, unions
   evidence when two workers report the same finding id). And for each results
   fragment:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_coverage.py .qa-loop/coverage.json .qa-loop/fragments/round-<N>-<slug>.results.json <N>`
7. Run metrics and read its decision:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/qa_metrics.py .qa-loop/ledger.json <N> <full|targeted>`
   It appends a row to `.qa-loop/rounds.md` and prints a JSON verdict with a
   `decision` field.
8. REGRESSION TESTS (only when emit_regression_tests is true): if any bug
   finding was verified fixed by THIS round's test pass, write
   "round-<N>-regression-tests" to `.qa-loop/.phase` and dispatch
   `regression-test-writer` with those findings (ids, repro steps, evidence
   paths) and the fragment path `.qa-loop/fragments/round-<N>-regression.json`
   for any missing-identifier findings it files (merge that fragment if it
   appears). On the loop's FIRST regression dispatch, also sweep the archives:
   scan `.qa-loop/archive/*/ledger.json` for bug findings that ended fixed
   but have no test referencing their id (grep the UITest target and
   `.qa-loop/regression-tests/`), and include them in the dispatch —
   previously-fixed-but-unguarded bugs are exactly what regression tests are
   for. It mines real selectors from the source, writes XCTSkip-guarded
   tests, and commits them separately. This step runs whatever the decision
   is — converged rounds deserve guards too.
9. Act on `decision`:
   - `continue`:
     a. INTENT CHECKS: if any finding's routing was flipped proposal->auto
        since the last round (the human accepted a proposal), write
        "round-<N>-fix-review" to `.qa-loop/.phase` and dispatch
        `fix-reviewer` in INTENT CHECK mode covering all such findings
        (fragment path `.qa-loop/fragments/round-<N>-intent.json`). Merge it.
        The resulting constraints travel with those findings into every
        later dispatch.
     b. Write "round-<N>-implementing" to `.qa-loop/.phase`, then dispatch
        `qa-implementer` with the OPEN auto-routed findings (including any
        whose note says FIX REJECTED — the rejection reason is part of its
        brief), their fix_risk flags and constraints, the testers' summaries,
        and the evidence paths. It commits PER WORKFLOW — the next round's
        targeting depends on it. Wait for its CHANGES block, confirm it
        committed, then append N to ledger.json's top-level
        implemented_rounds array — the metrics use it to tell
        post-implementation rounds from discovery rounds.
     c. FIX REVIEW (its fragment contains REJECTIONS ONLY — "updated: 1"
        against "14 sound, 1 rejected" is the contract, not truncation;
        `fixed` is minted by the next test pass, never by the reviewer):
        write "round-<N>-fix-review" to `.qa-loop/.phase` and
        dispatch `fix-reviewer` in FIX REVIEW mode with: the sha range of the
        implementer's commits this round, the CHANGES block (labeled as
        claims), the findings it claims to address (with fix_risk and
        constraints), and the fragment path
        `.qa-loop/fragments/round-<N>-fixreview.json`. Merge its fragment.
     d. If the fix review judged any fix unsound or harmful, FLAG IT TO THE
        HUMAN immediately and prominently — print one warning line per
        rejection in your progress output: "FIX REJECTED: <finding-id> —
        <reason>". Rejected findings stay open with the rejection reason in
        their note and return to the implementer next round; harmful fixes
        also minted an introduced_by_fix finding.
     e. Go to round N+1.
   - `full_pass_required`: go to round N+1 with a FULL pass and NO implementer
     dispatch (nothing to fix — you are confirming convergence on this build).
   - `thrashing_soft`: write "awaiting-human" to `.qa-loop/.phase`, STOP,
     and ask — the verdict's reason tells you which question: below the cap,
     "abort, or one more round?"; AT max_rounds, "abort, or raise max_rounds
     and continue?". If they continue, record it:
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py consulted .qa-loop/ledger.json <N>`
     — metrics then makes the NEXT thrashing signal hard automatically
     (measured: a report re-asked a question the human answered a round
     earlier).
   - anything else: stop and write the final report.


## Waiting, failures, and pauses (the phase marker is not a binary)
- Three marker states: bare `round-N-…` = you owe a dispatch (the Stop hook
  blocks); `…:dispatched` = an agent is running (stripped automatically when
  it returns, including on failure); `…:waiting:<reason>` = you are honestly
  waiting on something that is NOT a subagent — a backoff, a background task,
  a human. The hooks never touch `:waiting:`; you clear it when you resume.
  Never re-stamp `:dispatched` with nothing running — use `:waiting:`.
- Transport failures (529 / overloaded / no fragment written): retry the SAME
  dispatch up to 3 times with backoff INSIDE your turn (`sleep 60`, `180`,
  `300`) — an in-turn sleep never ends the turn, so there is nothing for the
  guard to misread. Never swap a pinned model silently. A model fallback is
  allowed only after three failures, must be disclosed in the report
  ("<agent> ran on <model> for round N: outage"), and the affected fragment
  gets a note saying so.
- Partial work survives: agents write `<fragment>.partial` incrementally and
  `mv` it to the final name when done. A dead dispatch that left a
  `.partial` gets retried WITH that file as "your prior work — resume, do not
  redo". The guard ignores `.partial` files by construction.
- A result without its artifact — an implementer with no CHANGES block, a
  reviewer/tester with no fragment — is a PAUSE, not a completion (it
  usually stopped to wait on a background child). Resume the SAME agent
  (SendMessage); never re-dispatch a paused agent.

## Stop conditions (computed by qa_metrics.py, evaluated in this order)
- CONVERGED: 0 open auto-routed blockers AND majors, none newly introduced this
  round, AND the round was a full pass whose coverage manifest accounts for
  every test case in TESTCASES.md (qa_metrics.py verifies this; unrun cases or
  a missing manifest degrade the verdict to `full_pass_required`). When the
  signals are present on a targeted pass, the verdict is `full_pass_required`.
- THRASHING (abort, escalate): any finding reopened >= 2 times (fixed->open;
  fixed->partial is refinement and does not count), OR net <= 0 for two
  consecutive POST-IMPLEMENTATION rounds (discovery rounds are inherently
  net-negative and never count — that is what implemented_rounds gates), OR
  the same region recurs in new/reopened findings for three consecutive
  rounds. Regions are workflows/screens, so this catches "the loop keeps
  churning the checkout screen." Exempt from the churn signal: a CONVERGING
  SERIES — every open finding is introduced_by_fix, the worst open severity
  is non-increasing over three rounds, nothing reopened.
- THRASHING_SOFT: the same signals but with 0 open blockers AND positive
  closes this round. -> STOP and ask the human: abort with the report, or
  run one more round? A second thrashing signal after an approved
  continuation is hard — do not re-ask.
- STALEMATE: identical `disputed` set for two consecutive rounds.
- DIMINISHING: net <= 1 for two consecutive POST-IMPLEMENTATION rounds AND 0
  open blockers AND no new blockers/majors this round (a round that spawned
  regressions is not "diminishing").
- BACKSTOP: N == max_rounds. Hard stop regardless of state.
- BUDGET: cumulative subagent tokens (set-usage) >= token_budget -> stop and
  report. Evaluated right after CONVERGED.
All metrics are computed over auto-routed findings only. Proposal-routed
findings NEVER count toward convergence or thrashing — they are the human's
decisions, and the loop must not deadlock on them.

## Final report (always)
Render it — do not write it by hand:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_report.py .qa-loop`
generates every mechanical section from the state files: stop condition,
trend table (incl. the Promoted column), open findings by severity with
evidence, disputes, UX PROPOSALS, FIX REVIEW REJECTIONS, severity changes,
PERSONA MATRIX and COVERAGE GAPS (from coverage.json), wontfix. Then edit
ONLY the WATCH LIST slots and add material WORKFLOWS.md edits if any. What
the sections mean, for your WATCH LIST judgment:
- Disputed items (agree-to-disagree), with both sides' arguments.
- UX PROPOSALS: every proposal-routed finding — the evidence, the cost to the
  user, and a sketch of the proposed fix. The human decides; to accept one,
  flip its routing to "auto" and re-run the loop (acceptance triggers a
  design-intent check before implementation — accepted behavior changes get
  MORE scrutiny, not less).
- FIX REVIEW REJECTIONS: every fix judged unsound or harmful across the loop,
  with the reviewer's reason and the finding's current state — these need
  human eyes even if later resolved.
- PERSONA MATRIX: a workflow × persona table built from coverage.json
  (personas recorded per test-case result), so a workflow labeled "both" but
  exercised by one persona shows as a visible hole, not an implicit claim.
- COVERAGE GAPS: every test case whose latest status is blocked or skipped,
  with its reason. (Example: device rotation is not scriptable in some
  environments and there is no simctl rotation command — if the app offers a
  launch argument to force orientation use that, otherwise the case stays
  here as a documented gap rather than silently dropped.)
- Material WORKFLOWS.md edits made during the loop, if any.
- WATCH LIST: the 3-5 most invasive fixes across all rounds, every proposal,
  every finding carrying fix_risk (listed for that reason — its obvious fix
  was a trap), and every fix-review rejection — each with its commit and a
  one-line "look here because…". This is the part a human should actually
  read: the fix-reviewer decorrelates the loop's blind spots but cannot
  eliminate them.
Print a one-line verdict and the path to the report, and set
`.qa-loop/.phase` to "done". If worker simulators exist, tear them down:
`${CLAUDE_PLUGIN_ROOT}/scripts/provision_workers.sh down`

## Interrupting and resuming
Killing a round at any point is safe: the durable state is ledger.json, the
merged fragments, coverage.json, and the docs — evidence for an aborted round
may be partial, and that is fine. To resume: read `.qa-loop/.phase` to see
where the loop was, then restart the interrupted round from its step 1 — the
deterministic reset makes a restart free. Never try to resume a half-finished
test pass mid-chunk.

## Contracts (what subagents write — keep dispatches consistent with these)
LEDGER fragment (`.qa-loop/fragments/round-<N>-<slug>.json`):
```json
{ "findings": [ {
  "id": "ux/WF-2:checkout-tap-count",
  "claim": "REQUIRED on new findings: what is wrong and its concrete failure mode, 1-2 sentences — the ledger must stand alone as the implementer's brief",
  "type": "bug | ux-design", "routing": "auto | proposal",
  "severity": "blocker | major | minor",
  "confidence": "confirmed | suspected",
  "region": "WF-2", "test_case": "TC-2.1", "build_sha": "abc123",
  "evidence": { "screenshots": ["evidence/round-1/wf2-step3.png"],
                "repro": ["launch", "tap Cart"],
                "measurements": { "taps": 9, "expected_taps": 3 } },
  "first_seen_round": 1, "introduced_by_fix": false,
  "status_history": [{ "round": 1, "status": "open" }],
  "current_status": "open", "note": "",
  "fix_risk": "metric-integrity | incentive | behavior-change | state-migration (OPTIONAL — set when the obvious fix is a trap)",
  "constraints": ["OPTIONAL — written by the fix-reviewer's intent check on accepted proposals"],
  "severity_history": [{ "round": 3, "from": "minor", "to": "major" }]
} ] }
```
(`severity_history` is written by the merge when a fragment changes a
finding's severity; it feeds the Promoted column — never write it yourself.)
Fragments MAY omit status_history entirely — merge_ledger.py appends this
round's entry from current_status. When status_history is included, every
"round" value must be an integer (annotations go in "note").
Results fragment (`.qa-loop/fragments/round-<N>-<slug>.results.json`):
```json
{ "results": [ { "tc": "TC-2.1", "persona": "novice|power",
                 "status": "passed|failed|blocked|skipped", "reason": "" } ] }
```
Every assigned test case must appear exactly once; "blocked" means the
environment prevented the test and requires a reason.
