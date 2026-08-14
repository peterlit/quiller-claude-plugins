# qa-loop-tools

A Claude Code plugin that QA-tests an **iOS app the way a real user experiences
it**: it drives the app in the iOS Simulator through persona-based workflows,
hunts for UX friction and bugs with screenshot-and-measurement evidence, hands
findings to an implementer, and loops until the app converges — with thrashing
detection and a hard iteration backstop.

Sibling of [review-loop-tools](../review-loop-tools/): same convergence
machinery, but the reviewer reads the *running app*, not the code.

## How it works

Three roles:

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
  only declare CONVERGED after confirming on a full pass.

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
`scripts/nfr_sampler.sh` samples the app's real PID from the host: resident
memory over time (leak detection via repeated-action loops), CPU (sustained
burn), and network bytes via `nettop` — no proxy or Instruments setup. Two
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

## Loop state

Everything lives in the **target repository** under `.qa-loop/`:
`WORKFLOWS.md` (your approved contract), `TESTCASES.md` (derived),
`ledger.json`, `rounds.md`, `REPORT.md`, and `evidence/round-N/` (screenshots +
`samples.jsonl`). Nothing is stored in the plugin directory. Add
`.qa-loop/evidence/` to `.gitignore` — screenshots bloat repos.

## Requirements

- macOS with Xcode and a bootable iOS Simulator.
- The **iOS Simulator control tools** (the `Claude_Code_iOS_Simulator` MCP
  server) available in the session — `xcrun simctl` alone can launch and
  screenshot but cannot inject taps, so without the MCP the plugin degrades to
  launch-and-observe only.

## Model configuration

The **implementer** uses `model: inherit` — it runs on whatever model you
select for your main session (via `/model`). The **tester** is pinned to a
fixed model in its frontmatter (`agents/ux-tester.md`) so the two agents run on
different models, a partial guard against correlated blind spots.

*If you run your main session on the same model the tester is pinned to,
tester/implementer model diversity silently collapses — edit the tester's
`model:` pin (in `agents/ux-tester.md`) to restore it.*

## Usage

```
/qa-loop-tools:qa-loop
```

Optionally give a max round count (default 5). The final report is
`.qa-loop/REPORT.md`; read its **WATCH LIST** and **UX PROPOSALS** — the loop
cannot catch two same-family agents agreeing on a fix that is wrong for real
users.
