# review-loop-tools 0.13.0 feedback — 2026-09-19 run (header place switcher)

Run shape: SCOPE mode over one feature commit (bd73178: the Timeline header
title becomes a Menu over the saved places — Picker with the shown row
checkmarked, "Edit places…" jumps to the Places tab), skeptical reviewer
pinned to Opus, implementer inheriting the Fable 5.1 session, blind verifier
on Sonnet, and the three-lane PANEL (codex gpt-6-astra, gemini-3.5-flash,
ollama qwen3-coder:30b) on seed + final. Fresh session (0.0 MB at loop
start; the feature was built in the same session but after a /clear).
Verdict: CONVERGED at round 1; closeout ran. 7 ledger findings, all minor:
4 fixed, 1 partial (dispute upheld), 2 open → BACKLOG M60–M62. Full suites
at closeout: Core 579/0, app unit 288/0, UI 13 executed / 8 pre-existing
skips / 0 failures. Mutation: round 1 4/4 killed; closeout 4 killed + 1
declared-equivalent survivor, 0 errors.

## Usage data

Reported subagent tokens (harness figure; billed effective runs ~4× higher
for code loops per CONTROLS.md) and wall-clock per dispatch:

| Phase | Agent (model) | Tokens | Tool uses | Wall | Outcome |
|---|---|---|---|---|---|
| seed panel, run 1 | codex + gemini lanes | n/a | — | ~60 s | BOTH ERRORED (NODE_OPTIONS, below); ollama 10 candidates |
| seed panel, run 2 | all three lanes, `env -u NODE_OPTIONS` | n/a | — | ~210 s | 1 + 8 + 10 candidates |
| seed | panel-verifier (sonnet) | 39,128 | 21 | 161 s | 2/19 kept (both minor) |
| seed | skeptical-reviewer (opus) | 72,947 | 36 | 450 s | 4 minors (2 own, 2 panel), 0 blockers/majors |
| r1 | implementer (fable 5.1) | 44,208 | 24 | 371 s | 1/1 fixed, 4/4 mutants |
| r1 | skeptical-reviewer (opus) | 50,332 | 28 | 440 s | fixed; +1 minor (its own 2 call-site mutants SURVIVED) |
| final panel | all three lanes | n/a | — | ~200 s | 1 + 8 + 10 candidates |
| final | panel-verifier (sonnet) | 44,185 | 26 | 189 s | 2/19 kept (1 net-new) |
| closeout | implementer | 65,498 | 24 | 760 s | 3 fixed, 1 partial + dispute |
| closeout | skeptical-reviewer (opus) | 75,551 | 58 | 551 s | dispute upheld; +2 minors; full suites green |

Totals: 391,849 reported subagent tokens; ~55 min of agent wall-clock, of
which ~25 min overlapped (final panel + verifier alongside the closeout
implementer). Orchestrator turns: 3 per round as advertised, plus 4 for the
panel plumbing. Per-round: seed 112,075 · r1 94,540 · closeout + final
panel 185,234.

Panel kept-rates (verifier-adjudicated), both passes:

| Lane | Seed | Final | Notes |
|---|---|---|---|
| codex gpt-6-astra | 1/1 | 0/1 | Files one precise finding per pass; the seed one (UI-test prefix filter over-excludes) was real; the final one was a duplicate of a ledgered item. |
| gemini-3.5-flash | 1/8 | 2/8 | Kept items: the test re-implements the closure body (demoted major→minor); the UI-test button-label collision (demoted). Rejected: a Picker `.tag(Optional)` "type mismatch" and a "Menu loses colors to tint" — both contradicted by the identical shipped Menu/Picker at MapScreen.swift:888; a "header lags the network" claim the code comments explicitly address. Severity inflated every time. |
| ollama qwen3-coder:30b | 0/10 | 0/10 | 0/40 across two runs now. Cites a file that does not exist, a `@MainActor` violation on a class that is `@MainActor`, a "blocker" crash with no reachable path. Drop the lane. |

Verifier cost per kept panel finding: 83,313 tokens for 4 kept, of which 1
duplicated a ledgered item — ~28K tokens per net-new panel minor, all
test-only. Consistent with 2026-09-13 (~23K).

## What worked notably well

- **The reviewer's own call-site mutants, again.** The r1 implementer's
  manifest killed 4/4 on the helper BODIES; the reviewer mutated the two
  CALL SITES (`menuOrder(...)` → raw store; `placeRowTitle` → `displayName`)
  and both survived the round's verify_cmd. Same pattern as the 2026-09-13
  run (MapScreen call site). The skill should say this outright: an
  implementer manifest that mutates only the functions it wrote is not
  evidence the view uses them.
- **The dispute channel, used honestly and adjudicated with evidence.** The
  closeout implementer declared one mutant `expect:survived` and argued
  equivalence (the store is current-first by construction); the closeout
  reviewer read CurrentPlace.merge, PlacesScreen.onMove/onDelete and
  adoptRecovered and UPHELD it with line cites. `partial` + a BACKLOG
  sketch is the right terminal state, not a forced green.
- **The closeout reviewer caught a false CHANGES claim.** "No prefix
  comparison remains" was untrue (line 240 still prefix-matches) — filed
  as its own minor with the tighter predicate. The implementer's
  self-report is an input, never a conclusion; the loop enforced that.
- **The blind verifier's rejections were checkable.** Every rejection
  cited the contradicting line (MapScreen.swift:888-909 for the two
  SwiftUI-pattern claims; Stores.swift:11 for the actor claim). The
  verifier also noticed, unprompted, that the header comment falsifies
  gemini's "lags the network" claim — the optional "one line of my own"
  channel earning its keep.
- **`next-round` + `open closeout` + `render_report`** were each one call;
  the report's mechanical sections needed no hand edits.

## Defects / friction, in impact order

1. **Panel lanes inherit a poisoned `NODE_OPTIONS` and die silently
   (cost: one full panel rerun, ~4 min, plus the ollama lane twice).** The
   terminal wrapper exports `NODE_OPTIONS=--require=/var/folders/…/cmux-
   claude-node-options/restore-node-options.cjs`; that file was gone, so
   the codex and gemini CLIs (both Node) failed at startup with "Cannot
   find module". `probe --smoke` had just said both lanes were ok (it
   checks auth, not that the CLI can launch); `run` reported
   `status: "error"` per lane but exited 0. Fixes: (a) launch lanes with a
   scrubbed environment (drop `NODE_OPTIONS`, or at least strip
   `--require` entries whose file is missing) — an agent CLI should never
   depend on the orchestrator's terminal wrapper; (b) probe should
   actually spawn each CLI once (`--version`) so a launch failure shows at
   the gate; (c) a non-zero exit, or at least a loud stderr summary, when
   any configured lane errors.
2. **No per-lane rerun.** `panel_review.py run <dir> <round>` has no
   `--lanes` filter, so recovering two failed lanes meant rerunning all
   three and overwriting the good ollama candidates. Add `--lanes a,b` and
   make `run` skip lanes whose candidates file already exists unless
   `--force`.
3. **iCloud minted `ledger 2.json` / `verdict 2.json` INSIDE the new
   archive AFTER `archive` reported `duplicates_detected: 0`, and
   `hygiene_check.sh` said "clean".** The plain names were missing, so
   the archived conclusions would have been untracked (the allowlist
   re-includes exact names only). Caught by an `ls` of the archive dir
   before the final commit. hygiene_check should scan `archive/*/` for
   space-suffixed names and for allowlisted names that are missing next to
   a suffixed twin, and `archive` should re-verify its own output a moment
   after the moves (the file provider re-stamps asynchronously).
4. **Phase-marker suffix vs. overlapping dispatches (recurring).** With
   the final panel-verifier and the closeout implementer running together,
   the `:dispatched` stamp is stripped when the first returns; I used
   `…:waiting:<reason>` throughout as the 2026-09-13 report suggested. The
   marker still needs to count live dispatches (or be keyed by agent).
5. **mutate.py has no per-mutant test command, so UI-killed mutants make
   every mutant pay the UI suite.** The closeout manifest (5 mutants, two
   only killable by XCUITests) takes ~25 min end-to-end; the implementer
   pre-flighted them as five single-mutant scratch copies to stay under
   the Bash cap, and the reviewer ran the manifest in the background for
   the whole verification. A per-mutant `test_cmd` override (unit mutants
   run the unit gate; UI mutants the UI gate) would cut this to ~8 min.
6. **The closeout reviewer's task notified twice** — the second was a
   "stale background waiter" from its own polling, repeating the result
   with a slightly different token figure (75,204 vs 75,551). Harmless
   here, but an orchestrator that `add-usage`s on every notification would
   double-count; the skill could say "record usage once per dispatch, from
   the first completion".
7. **The verifier's `kept` and the tally's `kept` disagree by one.** The
   final verifier reported gemini 1 confirmed-demoted; `panel-tally`
   recorded gemini kept 2 (it counts a demoted duplicate as kept). Define
   "kept" once — findings that reach the chair — and have both use it.

## Environment notes (not the plugin's fault, but they shaped the run)

- The iOS Simulator MCP tools were not loaded in this session, so the
  feature's simulator verification was done as a real XCUITest instead of
  a driven tap + screenshot — which then became the regression test. A
  better outcome than a screenshot, arguably; the skill could recommend it.
- UI tests still refuse to run on `-scheme WeatherTimeline` (use
  `WeatherTimelineUITests`); every dispatch carried the instruction and no
  agent tripped on it this run.
- 8 of the 13 UI tests in the touched classes are hard `XCTSkipIf(true,
  "verify selectors…")` — pre-existing. The closeout reviewer flagged that
  "UI suite green" means 5 of 13 ran; a Skipped column in the report's
  closeout section would make this visible without reading the note.

## Recommendations, ranked by expected savings

1. Scrub `NODE_OPTIONS` (and other `--require`-style env) when spawning
   lane CLIs; make `probe` actually launch each CLI; non-zero exit on lane
   errors.
2. `run --lanes a,b` and don't overwrite existing candidates without
   `--force`.
3. Drop the ollama lane from the default panel.json for this repo (0/40).
4. Per-mutant `test_cmd` in mutate.py manifests.
5. hygiene_check scans archives; archive re-verifies after a short delay.
6. Skill text: "the implementer's manifest is not evidence the call sites
   use the new code — mutate the call sites yourself" as a reviewer rule.
