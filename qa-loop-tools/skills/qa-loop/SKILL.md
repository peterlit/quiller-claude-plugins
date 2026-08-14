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
- The tester's round input is the prior ledger + the git diff since the last
  round's build_sha + the implementer's CHANGES block, labeled as the
  implementer's unverified claims — never your own summary of what changed.
- All loop state lives in the TARGET REPO at `.qa-loop/`. Never write it into
  the plugin directory. Suggest adding `.qa-loop/evidence/` to .gitignore.
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
   `{ "round": 0, "build_sha": null, "max_rounds": 5, "findings": [] }`
   (use the user's max_rounds if they gave one).
2. If `.qa-loop/WORKFLOWS.md` doesn't exist: read the code, docs, and app
   metadata, then draft it with: persona definitions (novice = discoverability;
   power user = efficiency and rare-but-legit complex tasks), workflows with
   stable IDs (WF-1, WF-2, …), and each workflow's reasonable-effort
   expectation (e.g. "WF-2: log a purchase — <= 3 taps for a power user").
3. STOP and ask the human to review WORKFLOWS.md. When they respond, RE-READ
   the file (they may have edited it directly) and reconcile their feedback
   before proceeding. Do not start testing without this sign-off.
In later rounds you may update WORKFLOWS.md when app functionality changes, but
material edits are FLAGGED in the report — never re-gated on the human.

## Stage 2 — Test cases (once; refresh only affected workflows later)
Dispatch `ux-tester` in EXPLORATION mode in CHUNKS — one dispatch per workflow,
or batches of at most 3 workflows: each dispatch runs its workflows in both
personas, APPENDS its test cases to `.qa-loop/TESTCASES.md`, and returns a
one-line summary. Print a one-line progress update between dispatches
("WF-4/12 explored, 2 candidate concerns"). Never send all workflows to a
single dispatch — a monolithic pass runs silently for tens of minutes and can
exhaust the tester's context with screenshots before it writes anything.
In later rounds, refresh only the test cases for workflows whose screens
changed.

## Each round (N = 1 .. max_rounds)
1. Preflight (Stage 0). Set build_sha = current HEAD; persist it; set round = N.
2. Reset app state deterministically.
3. Find the app's host PID (simulator apps are native macOS processes — use the
   pid printed by `xcrun simctl launch`, or `pgrep -x <AppName>`), then start
   the sampler in the background:
   `${CLAUDE_PLUGIN_ROOT}/scripts/nfr_sampler.sh <pid> .qa-loop/evidence/round-<N>/samples.jsonl &`
4. Choose the test set:
   - Round 1, or previous verdict was `full_pass_required`: FULL pass (all test
     cases).
   - Otherwise TARGETED: test cases whose workflows/screens are touched by the
     diff since the last build_sha, the repro steps of every open or
     claimed-fixed finding, plus a small fixed smoke set.
5. Dispatch `ux-tester` in TEST mode in CHUNKS (one dispatch per workflow, or
   batches of at most 3), each with: its slice of the test set, the prior
   ledger.json, the evidence directory `.qa-loop/evidence/round-<N>/`, and
   (round >= 2) the diff since the last round's build_sha plus the
   implementer's CHANGES block labeled as claims to validate. Each chunk
   returns a LEDGER fragment covering its slice; print a one-line progress
   update between chunks, then merge the fragments in step 6. Stop the sampler
   after the last chunk.
6. Merge the LEDGER into ledger.json (append to each finding's status_history;
   add new findings; update current_status).
7. Run metrics and read its decision:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/qa_metrics.py .qa-loop/ledger.json <N> <full|targeted>`
   It appends a row to `.qa-loop/rounds.md` and prints a JSON verdict with a
   `decision` field.
8. Act on `decision`:
   - `continue`: dispatch `qa-implementer` with the OPEN auto-routed findings,
     the tester's report, and the evidence paths. Wait for its CHANGES block and
     confirm it committed. Go to round N+1.
   - `full_pass_required`: go to round N+1 with a FULL pass and NO implementer
     dispatch (nothing to fix — you are confirming convergence on this build).
   - anything else: stop and write the final report.

## Stop conditions (computed by qa_metrics.py, evaluated in this order)
- CONVERGED: 0 open auto-routed blockers AND majors, none newly introduced this
  round, AND the round was a full pass. When the signals are present on a
  targeted pass, the verdict is `full_pass_required` instead.
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
- Material WORKFLOWS.md edits made during the loop, if any.
- WATCH LIST: the 3-5 most invasive fixes across all rounds plus every
  proposal, each with its commit and a one-line "look here because…". This is
  the part a human should actually read, because the loop cannot catch two
  same-family agents agreeing on a fix that is wrong for real users.
Print a one-line verdict and the path to the report.
