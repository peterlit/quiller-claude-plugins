# QA loop v0.12.0 — token usage and feedback

Run of 2026-09-09 against Causeway at `1a63ce2`, autonomous (the owner asked for max 4 rounds, 3 testers,
"make your judgement calls", and as many XCUITests as possible). Plugin `qa-loop-tools@quiller` **0.12.0**.
Settings: `max_rounds=4`, `parallel_testers=3`, `emit_regression_tests=true`, `token_budget=6.5M → 7.5M`
(harness scale). Measured with `tools/loop-usage.py --since 1788958000` against the raw transcripts, same
accounting as `docs/loop-token-usage.md`. The owner stopped the loop during round 4's confirmation pass.
The orchestrator's judgment calls are in [`qa-loop-2026-09-09-decisions.md`](qa-loop-2026-09-09-decisions.md).

## 1. Headline

| | |
|---|---|
| Wall clock | ~8 h 40 min (08:49 → ~17:30) |
| Rounds | round 0 (3 exploration dispatches) + round 1 full + round 2 targeted + round 3 targeted + round 4 full (stopped at 24/90) |
| Stop condition | owner wrap-up during the confirmation pass; rounds 1-3 ended `full_pass_required` with 0 blockers / 0 majors |
| Subagent dispatches | 71 (62 testers, 4 regression writers, 2 implementers, 3 fix-reviewers) |
| Test cases | 90 (14 novice-only, rest both/power); 24 + 36 + 24 + 24 executions across rounds |
| Findings | 37 — 0 blocker, 8 major, 24 minor + 5 proposals; 24 fixed and verified on device, 3 minor open, 5 proposals open, 5 wontfix (3 duplicates) |
| Fixes | 22 per-workflow commits (14 + 8), all reviewed; 2 fix-review rejections, both resolved |
| XCUITests | 21 → **70 executions / 67 methods**, all ARMED, all green at `0cd71fa`; Node 161 → 167; Swift unit 11 → 14 |
| **Total effective tokens** | **40.1 M** |
| Orchestrator share | 6.4 M (16%) — this session ran the whole loop in one context (4 MB transcript at the end) |
| Subagent share | 33.7 M (84%) |
| Harness-reported subagent tokens | 5.8 M → **6.9× below** effective |
| Cost per finding | 1.08 M (last loop: 1.05 M); per verified fix 1.67 M |

## 2. Where it went

| Agent | n | requests | effective |
|---|---:|---:|---:|
| `ux-tester` (opus pin) | 62 | 2,603 | 21.2 M |
| `regression-test-writer` (inherit) | 4 | 275 | 7.2 M |
| `qa-implementer` (inherit) | 2 | 135 | 3.7 M |
| `fix-reviewer` (sonnet pin) | 3 | 148 | 1.6 M |

Cache reads are again the whole story (3,161 subagent requests; 130 screenshots ≈ 0.2 M). The regression
writer is the new cost centre: 7.2 M for 49 tests is 147 K per armed test, because each writer runs the
tests it writes (owner's instruction, see decision D6) — the whole UI target three times over the loop.

## 3. What it bought

- **Three majors the code reviews had waved through**: the deal-alert double-tap discard (masked, not fixed,
  since last loop — reproduced 2/2 the moment the keypad was down), a same-day second export that trashes
  the only backup, and a landscape rail that hides Daily/Wins/How to play behind an inert cue.
- **Landscape was tested for the first time** (two loops had it `blocked`): the driver rotates the device.
- **The ⏰ same-day two-day sequence was walked for real** with the date pin; both prior WF-14 majors
  verified fixed on the device rather than by reading code.
- **49 armed XCUITests** that seed app state through launch arguments (`QAFixtures.swift`), so the checks
  the testers repeat every round now run for free.
- The fix-reviewer earned its seat once: it predicted calendar-marker clipping at accessibility sizes from
  the diff, and the device confirmed it the next round.

## 4. Feedback on v0.12.0

### What works, keep it

1. **The fixture policy + a date pin.** Once WORKFLOWS.md pinned `CAUSEWAY_TODAY_OVERRIDE`, every daily/⏰/🌟
   case became replayable and the two-day grace sequence testable. The skill's insistence on a Fixture
   policy section is what made an app-side pin get built in the first place (last loop's proposal).
2. **Chunked dispatches with a turn budget** — 62 tester dispatches, none ran away; the largest was 118 K.
3. **`fix_risk`/trap notes in claims.** The implementer respected every trap (no y-nudge for the double
   tap, no persisted-field migration for the run count, Prev as re-simulation not Undo).
4. **The reviewer/tester split on "fixed".** The reviewer rejected a fix that the tester later verified
   fixed (Dynamic Type) — and the reviewer was right about the side effect. Both seats were needed.
5. **The `resolve` verb** was enough for every orchestrator decision (dedupes, policy contradictions,
   reviewer rejections addressed elsewhere) without touching the findings array.

### Bugs and gaps, worst first

1. **`provision_workers.sh` uses fixed device names and deletes every `qa-worker-*` it finds.** Another
   session on this Mac ran the same script the same minute: it deleted my three workers (I would have
   deleted its). Namespace the names by repo/session (`qa-worker-<hash>-N`) and only ever delete devices
   listed in your own manifest. I created `causeway-qa-N` by hand for the whole run (decision D4).
2. **The MCP simulator-control tool needs a per-device human grant.** On three fresh devices with the owner
   away, Stage 0 dies ("user did not respond to the access request"). The skill's documented fallback — a
   tester-built XCUITest driver — cost about an hour to build and debug (decision D9). Ship one with the
   plugin: `.qa-loop/driver/` here is a working, generic superset (launch with env, tap/drag/type, rotate,
   identifier queries, one-call label dumps, screenshots to host paths, immortal against XCTest issues).
   It also removes the "grant" step entirely from autonomous runs.
3. **`notes-rotate`'s second pass archives the LARGEST section.** Three times it archived the freshly
   written Environment section — the one every tester needs first — while keeping stale geometry. Rotate
   by age or by `## Chunk` heading only, and never the first section. The 10 KB ceiling is also too small
   for a driver-era rig; I split the file (core notes + `tools/README.md` for fixture/sheet recipes) by
   hand and trimmed after every batch (≈12 manual trims).
4. **Tester and orchestrator instructions contradict each other on `## Chunk` sections** (testers: "rotation
   archives those at loop end"; orchestrator: "rotate before EVERY dispatch batch"). Fresh chunk notes were
   archived before the next chunk could read them until I folded them into general sections by hand.
5. **Evidence directories collide across loops.** `archive` moves ledgers but not `evidence/round-N/`, so
   this loop's `round-1/wf-*` dirs held 1,117 files from 2026-08-22/30; three testers reported "stale
   evidence" before I moved them to `evidence/loops-before-20260909/`. Archive evidence with the loop, or
   name evidence dirs by loop timestamp.
6. **Sibling chunks of one workflow file the same finding under different ids.** WF-12 and WF-14 were split
   across two workers; three duplicate pairs resulted (resolved as `wontfix — DUPLICATE`, which also makes
   the wontfix count lie). Keep a workflow's chunks on one worker, or add a "sibling chunk reserved these
   ids" line to the dispatch, or a claim-similarity dedupe in the merge.
7. **`plan_round.py` degenerates every targeted pass to findings+smoke** because the app's few large view
   files map to most workflows through `paths()`; per-workflow commits did not help. Round 2 and 3 were
   therefore both 24-36 cases of the same shape. Symbol- or hunk-level mapping, or `--allow-wide` by
   default when the diff is many small commits, would restore real targeting.
8. **`full_pass_required` with open minors and one round left strands the minors.** Round 3 left two
   one-line fixes open because the verdict forbids an implementer dispatch. Allow the implementer when
   only minors are open, or let the confirmation pass be smoke + the repros of this loop's fixes.
9. **Tiny chunks.** 23 chunks per full pass, seven of them one or two cases; each dispatch pays ~40-60 K
   of fixed cost (reading notes, README, WORKFLOWS). A minimum chunk of three cases, or per-worker
   batching of tiny chunks, would cut a full pass by a third.
10. **`open --region WF-n` never selects findings whose region is a screen name** (`Main`, `DailyView`,
    `ContentView`). The identifier findings the writer files only ever reach the implementer; no tester
    chunk verifies them (I resolved two by hand from the writer's green run — decision D15).
11. **The regression writer's default skip guard** produces tests that "automate nothing" in an
    autonomous run. The arm-when-green-on-a-named-device policy I used produced 49 armed tests, 0 flaky
    after a timing fix. Make it a setting.
12. **The harness-scale budget is 6.9× under effective here** (5.8 M vs 40.1 M); CONTROLS.md says 4-11×. Fine
    as a warning, but a budget stop keyed on that scale cannot protect a real spend.
13. **The perf lane re-runs its `[perf]` cases every round** (TC-4.1 ran four times, all clean). A perf lane
    only when a perf candidate or a `[perf]`-tagged surface changed would save ~90 K per round.
14. **The MCP `build` tool targets "the first booted device"** — which was another session's simulator.
    Harmless for a simulator .app, but it should prefer a device the loop owns.
15. Small: `qa_metrics.py`'s stop reason on an aborted full pass is honest ("66 unrun") but the trend row
    still says `full`; the report needed a hand-written stop line. `render_report.py`'s watch-list
    candidates include duplicate-resolved findings as "proposal awaiting decision".

### Two judgment calls worth recording

- **Running the regression writer concurrently with the implementer** (round 1, worktree + cherry-pick)
  saved ~45 min but produced six tests written against pre-fix copy that failed on `main` and needed a
  repair dispatch (66 K). Sequential is cheaper unless the implementer's scope is known to be tiny.
- **A driver over the MCP tool even when a grant is available.** Launching with an environment (the date
  pin), rotation, `find <identifier>` and one-call `labels` dumps made the testers faster and more precise
  than screenshots; 130 images in 3,161 requests, against 440 last loop.
