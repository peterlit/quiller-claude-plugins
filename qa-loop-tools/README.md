# qa-loop-tools

A Claude Code plugin that QA-tests an **iOS app the way a real user experiences
it**: it drives the app in the iOS Simulator through persona-based workflows,
hunts for UX friction and bugs with screenshot-and-measurement evidence, hands
findings to an implementer, and loops until the app converges — with thrashing
detection and a hard iteration backstop.

Sibling of [review-loop-tools](../review-loop-tools/): same convergence
machinery, but the reviewer reads the *running app*, not the code.

## How it works

Four roles:

1. **Orchestrator (main agent)** — pure plumbing. Builds/installs/launches the
   app, resets it to a deterministic state each round, runs the NFR sampler and
   metrics, dispatches the two subagents, and decides whether to continue. It
   never edits code and never performs test interactions itself.
2. **`ux-tester` subagent** — drives the app in the simulator in two explicit
   personas: *novice* (discoverability — can a first-time user find it?) and
   *power user* (efficiency — tap counts vs. expectations, and rare-but-legit
   complex tasks). Every finding carries evidence: exact repro steps,
   screenshots, and measurements.
3. **`qa-implementer` subagent** — fixes auto-routed findings, disputes false
   positives with numbers, builds, and commits. It never opens the simulator;
   the tester re-verifies every claimed fix with fresh eyes the next round.
4. **`fix-reviewer` subagent** — the loop's defense against its own biggest
   blind spot: two agents agreeing on a fix that is faithful to the finding
   and still wrong for the product (the canonical trap: "clock runs during
   sheets" fixed by pausing the clock — now any sheet is a pause button and
   best-times are gameable). Once per round it adversarially reviews the
   implementer's diff — scored metrics, incentives, persisted state, declared
   constraints — and rejects unsound fixes back to open (each rejection is
   flagged to you immediately and collected in the report's FIX REVIEW
   REJECTIONS section). It also runs a **design-intent check** whenever you
   accept a proposal: accepted behavior changes get *more* scrutiny, not
   less — the check emits constraints the implementation must satisfy.
   Findings whose *obvious fix is a trap* carry a `fix_risk` flag and land on
   the WATCH LIST for that reason.

## Stages

- **Stage 0 — Preflight** (every round): build → install → launch → smoke
  screenshot. A failure is an automatic blocker.
- **Stage 1 — Workflows** (once): the loop reads the code/docs and drafts
  `.qa-loop/WORKFLOWS.md` — personas, workflow IDs, and per-workflow effort
  expectations — then **stops and asks you to review it**. This is the loop's
  only blocking human gate; edit the file directly or reply with feedback.
- **Stage 2 — Test cases**: the tester explores the live app and derives
  `.qa-loop/TESTCASES.md` (persona-tagged, each case tied to a workflow ID).
- **Rounds**: test pass → evidence-backed findings ledger → metrics verdict →
  implementer fixes → re-test. Full pass on round 1; later rounds run a
  targeted set (changed areas + open-finding repros + smoke set). The loop can
  only declare CONVERGED after confirming on a full pass whose **coverage
  manifest** (`coverage.json`, built from per-test-case results every tester
  chunk must report) accounts for every case in TESTCASES.md — a full pass is
  verified, not claimed. Blocked/skipped cases surface in the report's
  COVERAGE GAPS section with reasons.

Stop conditions (converged / thrashing / stalemate / diminishing / backstop)
mirror review-loop-tools, with thrashing regions defined as workflows/screens.

## Findings: bugs vs. UX proposals

Every finding is typed and routed:

- **`bug`** and **small `ux-design`** findings (labels, missing spinners, hit
  targets) route **auto** — the implementer fixes them without asking.
- **Structural `ux-design`** findings (navigation shape, workflow redesign)
  route **proposal** — they appear in the report's UX PROPOSALS section with
  evidence and a sketch of the fix, and are excluded from convergence math.
  The loop never redesigns flows you approved in WORKFLOWS.md. To accept a
  proposal, flip its `routing` to `"auto"` in `ledger.json` and re-run.

## What the loop can honestly measure

Simulator apps run as native macOS processes, so the bundled
`scripts/nfr_sampler.sh` samples the app from the host: resident memory over
time (leak detection via repeated-action loops), CPU (sustained burn), and
network bytes via `nettop` — no proxy or Instruments setup. It tracks the app
by simulator UDID + bundle id, re-resolving the PID each tick, so it follows
the app across relaunches instead of dying with a PID; every sample carries
the pid so analysis can separate stints and never misreads a relaunch as a
memory drop. Two
honest limits, reflected in how findings are worded:

- **Battery is not measurable in a simulator.** The loop reports *sustained
  CPU while idle* as a battery-drain proxy instead.
- **Dropped frames aren't visible in screenshots.** Jank is approximated as
  action-to-visible-response latency and always marked as a heuristic.

## Parallel testers (optional)

Set `"parallel_testers": N` (2–3) in `.qa-loop/ledger.json` to run test passes
across N isolated worker simulators (`qa-worker-1..N`, provisioned and torn
down by `scripts/provision_workers.sh`). Wall-clock time drops roughly by the
worker count; token spend does not. Because concurrent simulators contend for
CPU, parallel runs split into two lanes: functional/UX checks run in parallel
with no samplers, and all performance measurements (latency, CPU, memory,
network) come from a short serial perf lane on a single uncontended simulator
afterwards. Single-tester mode (the default) keeps the sampler running through
the whole pass, as before.

## Token efficiency and hooks

Findings JSON never transits the orchestrator: testers write LEDGER fragments
to `.qa-loop/fragments/` and `scripts/merge_ledger.py` merges them
deterministically (including cross-worker evidence unions). Testers compute
the round diff themselves from a sha range. Three hooks guard the loop at zero
token cost: a `Stop` hook blocks the orchestrator from ending its turn while a
round is in flight (tracked via `.qa-loop/.phase`), a `SubagentStop` hook
validates fragment JSON before a subagent may finish, and the same optional
commit guard as review-loop-tools (`REVIEW_LOOP_MAX_DIFF`,
`REVIEW_LOOP_TEST_CMD`) can gate implementer commits.

## Loop state

Everything lives in the **target repository** under `.qa-loop/`:
`WORKFLOWS.md` (your approved contract, including the Fixture policy that pins
the app's randomness), `TESTCASES.md` (derived; also holds exploration's
Candidate concerns as hypotheses), `HARNESS_NOTES.md` (simulator interaction
quirks the testers discover, so they're learned once, not per round),
`ledger.json`, `rounds.md`, `coverage.json`, `REPORT.md`, and
`evidence/round-N/` (screenshots + `samples.jsonl`). Nothing is stored in the
plugin directory. The loop writes its own `.qa-loop/.gitignore` covering
`evidence/`, `fragments/`, and `.phase`; everything else is meant to be
committed. Interrupting a round is always safe — durable state is the ledger,
merged fragments, coverage, and docs, and the deterministic reset makes
restarting the round free.

## Requirements

- macOS with Xcode and a bootable iOS Simulator.
- The **iOS Simulator control tools** (the `Claude_Code_iOS_Simulator` MCP
  server) available in the session — `xcrun simctl` alone can launch and
  screenshot but cannot inject taps, so without the MCP the plugin degrades to
  launch-and-observe only.

## Model configuration

The **implementer** uses `model: inherit` — it runs on whatever model you
select for your main session (via `/model`). The **tester** and the
**fix-reviewer** are pinned to two *different* fixed models in their
frontmatter (`agents/ux-tester.md`, `agents/fix-reviewer.md`), so the three
seats run on three distinct models — a partial guard against correlated blind
spots. If you change any pin, keep all three distinct.

*If you run your main session on the same model the tester is pinned to,
tester/implementer model diversity silently collapses — edit the tester's
`model:` pin (in `agents/ux-tester.md`) to restore it.*

## Optional: regression-test skeletons

Set `"emit_regression_tests": true` in `.qa-loop/ledger.json` and a dedicated
`regression-test-writer` agent turns every bug verified fixed into an
**XCUITest** (Apple's built-in UI-testing framework: small Swift tests that
launch the app, tap through it, and fail the build if the bug returns). It
mines real `accessibilityIdentifier`s from your source for its element
queries (and files a minor finding when key elements have none — that hurts
accessibility too), drops the test into your UITest target only when the
project format picks up new files automatically (it never hand-edits
`project.pbxproj`; otherwise files land in `.qa-loop/regression-tests/` with
a note to add them in Xcode), and starts every test with an `XCTSkip` so an
unfinished test can never break CI — verify the selectors once, remove the
skip, and the fix is guarded forever. Off by default because it writes into
your repo's test suite.

## Usage

```
/qa-loop-tools:qa-loop
```

Optionally give a max round count (default 5). The final report is
`.qa-loop/REPORT.md`; read its **WATCH LIST** and **UX PROPOSALS** — the loop
cannot catch two same-family agents agreeing on a fix that is wrong for real
users.
