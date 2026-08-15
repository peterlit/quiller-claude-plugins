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
- You NEVER hand-edit ledger.json. Testers write LEDGER fragments to files,
  and every merge goes through merge_ledger.py.
- Maintain the phase marker `.qa-loop/.phase` (a Stop hook enforces it): write
  "round-<N>-testing" before dispatching testers, "round-<N>-implementing"
  before dispatching the implementer, "awaiting-human" when stopping at the
  Stage 1 gate, and "done" right after the final report. An ended turn while
  the phase says "round…" is a stall.
- All loop state lives in the TARGET REPO at `.qa-loop/`. Never write it into
  the plugin directory. Suggest adding `.qa-loop/evidence/` to .gitignore.
- While any tester dispatch is in flight, NOBODY touches a simulator — no
  screenshots, taps, or launches from you. Preflight interactions happen
  strictly BEFORE dispatch; evidence gathering is the tester's job. A stray
  orchestrator tap or screenshot races the tester and corrupts its pass.
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

## Stage 1 — Workflows (once; the ONLY blocking human gate)
1. If `.qa-loop/ledger.json` doesn't exist, create it with:
   `{ "round": 0, "build_sha": null, "max_rounds": 5, "parallel_testers": 1, "findings": [] }`
   (use the user's max_rounds and parallel_testers if they gave them; cap
   parallel_testers at 3 — each simulator wants 2-6GB of RAM). Also write
   `.qa-loop/.gitignore` containing exactly these three lines:
   `evidence/`, `fragments/`, `.phase` — everything else in `.qa-loop/`
   (WORKFLOWS.md, TESTCASES.md, HARNESS_NOTES.md, ledger.json, rounds.md,
   coverage.json, REPORT.md) is meant to be committed.
2. If `.qa-loop/WORKFLOWS.md` doesn't exist: read the code, docs, and app
   metadata, then draft it with: persona definitions (novice = discoverability;
   power user = efficiency and rare-but-legit complex tasks), workflows with
   stable IDs (WF-1, WF-2, …), each workflow's reasonable-effort expectation
   (e.g. "WF-2: log a purchase — <= 3 taps for a power user"), and a
   "Fixture policy" section: identify the app's randomness levers (launch
   arguments, debug pickers, seeds, fixture data) and pin concrete values so
   every run is reproducible. If the app offers no way to pin its randomness,
   note that — the tester will file a proposal-routed finding recommending one.
3. Write "awaiting-human" to `.qa-loop/.phase`, then STOP and ask the human to
   review WORKFLOWS.md. When you stop, announce the loop settings so the human
   can adjust them at this natural touchpoint: "max_rounds=<M>,
   parallel_testers=<P> — reply 'use N testers' to parallelize test passes."
   When they respond, RE-READ the file (they may have edited it directly) and
   reconcile their feedback before proceeding. Do not start testing without
   this sign-off.
In later rounds you may update WORKFLOWS.md when app functionality changes, but
material edits are FLAGGED in the report — never re-gated on the human.

## Stage 2 — Test cases (once; refresh only affected workflows later)
Write "round-0-testing" to `.qa-loop/.phase` (exploration counts as in-flight
work for the stall guard). Dispatch `ux-tester` in EXPLORATION mode in CHUNKS — one dispatch per workflow,
or batches of at most 3 workflows: each dispatch runs its workflows in both
personas, APPENDS its test cases to `.qa-loop/TESTCASES.md`, and returns a
one-line summary. Print a one-line progress update between dispatches
("WF-4/12 explored, 2 candidate concerns"). Never send all workflows to a
single dispatch — a monolithic pass runs silently for tens of minutes and can
exhaust the tester's context with screenshots before it writes anything.
In later rounds, refresh only the test cases for workflows whose screens
changed.

Exploration output is TEST CASES plus HYPOTHESES. Anything that looked wrong
during exploration is recorded in a "Candidate concerns" section of
TESTCASES.md as a hypothesis — NEVER pre-seeded into the ledger. Round 1
dispatches carry these concerns as reproduce-or-dismiss-with-evidence; only
reproduced concerns mint finding IDs. Unverified findings in the ledger would
skew every metric downstream.

## Each round (N = 1 .. max_rounds)
1. Preflight (Stage 0). Set build_sha = current HEAD; persist it; set round = N.
2. Reset app state deterministically (on EVERY worker device, in parallel mode).
3. Choose the test set:
   - Round 1, or previous verdict was `full_pass_required`: FULL pass (all test
     cases).
   - Otherwise TARGETED: test cases whose workflows/screens are touched by the
     diff since the last build_sha, the repro steps of every open or
     claimed-fixed finding, plus a small fixed smoke set.
4. Write "round-<N>-testing" to `.qa-loop/.phase` and run the FUNCTIONAL LANE.
   Every chunk dispatch carries: its slice of the test set, the path to the
   prior ledger.json, the harness notes `.qa-loop/HARNESS_NOTES.md` (create it
   empty if missing), the Fixture policy from WORKFLOWS.md, its evidence
   directory, the fragment path `.qa-loop/fragments/round-<N>-<chunk-slug>.json`
   where it must write its LEDGER, the results path
   `.qa-loop/fragments/round-<N>-<chunk-slug>.results.json` where it must
   record EVERY assigned test case (passed/failed/blocked/skipped + reason),
   and (round >= 2) the sha range `<last build_sha>..HEAD` (the tester runs
   `git diff` on it itself) plus the implementer's CHANGES block labeled as
   claims to validate. Round 1 dispatches also carry the Candidate concerns
   for their workflows, labeled as hypotheses to reproduce or dismiss. Each
   chunk returns a 2-line summary only; print a one-line progress update per
   completed chunk.
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
     and its own evidence subdir `.qa-loop/evidence/round-<N>/<worker-name>/`.
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
8. Act on `decision`:
   - `continue`: write "round-<N>-implementing" to `.qa-loop/.phase`, then
     dispatch `qa-implementer` with the OPEN auto-routed findings, the
     testers' summaries, and the evidence paths. Wait for its CHANGES block
     and confirm it committed. Go to round N+1.
   - `full_pass_required`: go to round N+1 with a FULL pass and NO implementer
     dispatch (nothing to fix — you are confirming convergence on this build).
   - anything else: stop and write the final report.

## Stop conditions (computed by qa_metrics.py, evaluated in this order)
- CONVERGED: 0 open auto-routed blockers AND majors, none newly introduced this
  round, AND the round was a full pass whose coverage manifest accounts for
  every test case in TESTCASES.md (qa_metrics.py verifies this; unrun cases or
  a missing manifest degrade the verdict to `full_pass_required`). When the
  signals are present on a targeted pass, the verdict is `full_pass_required`.
- THRASHING (abort, escalate): any finding reopened >= 2 times, OR net <= 0 for
  two consecutive rounds, OR the same region recurs in new/reopened findings
  for three consecutive rounds. Regions are workflows/screens, so this catches
  "the loop keeps churning the checkout screen."
- STALEMATE: identical `disputed` set for two consecutive rounds.
- DIMINISHING: net <= 1 for two consecutive rounds AND 0 open blockers.
- BACKSTOP: N == max_rounds. Hard stop regardless of state.
All metrics are computed over auto-routed findings only. Proposal-routed
findings NEVER count toward convergence or thrashing — they are the human's
decisions, and the loop must not deadlock on them.

## Final report (always)
Write `.qa-loop/REPORT.md`:
- Which stop condition fired and why.
- The `.qa-loop/rounds.md` trend table.
- Open findings by severity with evidence links.
- Disputed items (agree-to-disagree), with both sides' arguments.
- UX PROPOSALS: every proposal-routed finding — the evidence, the cost to the
  user, and a sketch of the proposed fix. The human decides; to accept one,
  flip its routing to "auto" and re-run the loop.
- COVERAGE GAPS: every test case whose latest status is blocked or skipped,
  with its reason. (Example: device rotation is not scriptable in some
  environments and there is no simctl rotation command — if the app offers a
  launch argument to force orientation use that, otherwise the case stays
  here as a documented gap rather than silently dropped.)
- Material WORKFLOWS.md edits made during the loop, if any.
- WATCH LIST: the 3-5 most invasive fixes across all rounds plus every
  proposal, each with its commit and a one-line "look here because…". This is
  the part a human should actually read, because the loop cannot catch two
  same-family agents agreeing on a fix that is wrong for real users.
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
  "type": "bug | ux-design", "routing": "auto | proposal",
  "severity": "blocker | major | minor",
  "confidence": "confirmed | suspected",
  "region": "WF-2", "test_case": "TC-2.1", "build_sha": "abc123",
  "evidence": { "screenshots": ["evidence/round-1/wf2-step3.png"],
                "repro": ["launch", "tap Cart"],
                "measurements": { "taps": 9, "expected_taps": 3 } },
  "first_seen_round": 1, "introduced_by_fix": false,
  "status_history": [{ "round": 1, "status": "open" }],
  "current_status": "open", "note": ""
} ] }
```
Results fragment (`.qa-loop/fragments/round-<N>-<slug>.results.json`):
```json
{ "results": [ { "tc": "TC-2.1", "status": "passed|failed|blocked|skipped",
                 "reason": "" } ] }
```
Every assigned test case must appear exactly once; "blocked" means the
environment prevented the test and requires a reason.
