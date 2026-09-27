# review-loop-tools 0.14.0 — field report, 2026-09-20 run (Timeline header streamlining)

For the plugin maintainer. Written 2026-09-26 from the run's on-disk state
(`.review-loop/ledger.json`, `rounds.md`, `verdict.json`, `REPORT.md`,
fragments, task notifications) and the `loop-usage.py` measurement — not
from memory. Empty sections mean nothing was observed.

## Header

| | |
|---|---|
| Plugin | review-loop-tools |
| Installed version | 0.14.0 (`~/.claude/plugins/installed_plugins.json`: installPath `…/cache/quiller/review-loop-tools/0.14.0`, gitCommitSha `949110b4…`, lastUpdated 2026-09-20T22:35:43Z) |
| Running version | 0.14.0 (`…/0.14.0/.claude-plugin/plugin.json`). No mismatch. Older caches 0.10.0 / 0.12.0 / 0.13.0 still present on disk — see defect -3. |
| Run date | 2026-09-20, 19:05–20:51 local (seed panel lanes ran in the previous session 19:05–19:14; everything else in this session from ~19:15) |
| Host repo | `weatherapp` (WeatherTimeline, iOS/Swift, Xcode project; checkout on an iCloud-synced volume) |
| Platform | macOS 26.4.1 (25E253); Claude Code 2.1.283; orchestrating session on Fable 5.1 |
| Settings | SCOPE mode, `scope: f044c29^..f044c29 -- :!prompts.md`; `max_rounds: 2` (SCOPE default, never escalated — no blocker); `token_budget: null`; `REVIEW_LOOP_UNATTENDED` not set (human present); panel `rounds: seed+final`, lanes codex (`gpt-6-astra`, timeout 900 s, max_diff_tokens 32000) and gemini (`gemini-3.5-flash`, 600 s, 32000) — ollama lane removed before this run; standing machine-local consent from 2026-09-13/19 |
| Resume | Loop was paused at seed by the previous session (session guard: transcript > 2 MB) with `.phase = seed-review:waiting:fresh-session-restart` and `briefs/HANDOFF.md`; resumed here, not archived |
| Rounds | seed (round 0) + 2 rounds + panel final pass + closeout |
| Stop condition | `diminishing` after round 2 — "net <= 1 for two rounds, no open blockers, no new blockers/majors" |
| Verdict per round | round 1: `continue` (net +1, closed 1, new 0); round 2: `diminishing` (net 0, closed 0, new 0) |
| Findings at end | 14 total: **by severity** 1 major, 13 minors, 0 blockers; **by status** 5 fixed, 2 partial (the major + 1 minor), 7 open (all minor; 3 opened by the closeout reviewer, 4 folded from the panel final pass); 1 `introduced_by_fix` (minor, drift-risk only); 0 disputed, 0 wontfix |
| Closeout full suite | unit `-scheme WeatherTimeline`: 297 executed, 0 failures; UI `-scheme WeatherTimelineUITests`: 29 executed, 14 skipped (pre-existing `XCTSkipIf` files this loop never touched), 0 failures. Tree green. |
| Mutation | implementer manifests re-run by the reviewer: round 1 6/6 killed, round 2 7/7, closeout 4/4 (0 errors, 0 mismatches each). Reviewer-authored call-site mutants survived in seed, round 1, round 2 and closeout — that is what kept the major `partial`. |
| Commits | a6493b9 (round 1), 8b5aed0 (round 2), e0890ec (closeout), c2dba3a (conclusions + BACKLOG) |

## Usage

`loop-usage.py --since 1789945700` (= 2026-09-20 19:08:20 local, the seed
diff's mtime) `--dir ~/.claude/projects/-Users-plit-Documents-src-weatherapp`.
Effective = input + 0.1·cache_read + 2·cache_write + 5·output.

| Role | Dispatch | Requests | Effective | Harness-reported | Wall clock |
|---|---|---:|---:|---:|---:|
| panel-verifier (sonnet) | seed | 14 | 141,763 | 49,603 | 133 s |
| skeptical-reviewer (opus) | seed | 42 | 388,270 | 80,183 | 470 s |
| implementer (inherit = Fable) | round 1 | 31 | 258,333 | 66,819 | 761 s |
| skeptical-reviewer | round 1 | 26 | 246,700 | 67,515 | 697 s |
| implementer | round 2 | 26 | 208,745 | 53,736 | 432 s |
| skeptical-reviewer | round 2 | 23 | 207,526 | 59,248 | 604 s |
| panel-verifier | final | 23 | 223,085 | 66,611 | 250 s |
| implementer | closeout | 41 | 314,089 | 67,095 | 1,052 s |
| skeptical-reviewer | closeout | 44 | 458,917 | 89,138 | 1,320 s |
| **subagents total** | | 270 | **2,447,428** | **599,948** | ratio 4.08× |
| orchestrator, this session | 57 | | 1,178,406 | — | includes ~5 post-loop Q&A turns and this report's research; the loop itself ended at 20:51 |
| orchestrator, previous session tail | 9 | | 174,274 | — | the pause/HANDOFF turns after 19:08 |
| **grand total in window** | | | **3,800,108** | | |

Per role: reviewer 1,301,413 effective vs 296,084 reported (4.4×);
implementer 781,167 vs 187,650 (4.2×); panel-verifier 364,848 vs 116,214
(3.1×). Subagent effective per finding: 2.45M / 14 ≈ 175K — inside the
HANDOFF's 165–197K scoped-run band.

External lanes: codex reported `total_tokens` 11,756 (seed, 72.8 s) and
16,707 (final, 95.9 s); gemini reported no token figure (seed 225.2 s,
final 207.0 s). Both lanes `status: ok` both passes; 0 failed, 0 skipped,
0 overflow-dropped.

Loop wall clock in this session: ~96 min from the first dispatch to
`REPORT.md`, plus ~9 min of seed panel lanes in the previous session.

## Watch items (post-0.14.0/0.15.0, review)

| Item | Result | Evidence |
|---|---|---|
| Dispatch counter under overlapping dispatches, no hand `:waiting:` | **observed failing once** | With the closeout implementer live and no SubagentStop in between, `.phase` read `round-2-implementing` (no suffix) and `briefs/.dispatched` read `0`. When the final panel-verifier then returned, the stop hook took the count 1→0 and stripped the mark while the implementer was still running. I bridged with `:waiting:closeout-implementer-running`. See defect -1 for the suspected trigger. |
| Quota lane failing over with `model_used` recorded | not applicable | Each lane had a single model string; no quota error. `model_used` is recorded in both `round-0.run.json` and `round-final.run.json`. |
| Final-pass cap on a 0/N lane; cross-loop `disabled-by-precision` | not applicable | The 0/40 ollama lane was removed from `panel.json` before this run, so no lane qualified. |
| EXCLUDED stat trailer ending "was not updated" candidates | observed (positive) | Trailer present in `round-0.stat` and `round-final.stat` (`prompts.md … excluded from this view`); 0 of 13 candidates across both passes mentioned prompts.md. |
| `run` refusing an empty diff | not observed | No empty diff occurred. |
| `duplicate_of` / `notes_for_chair` used by the verifier | observed | Final pass: gemini's re-file of the vacuous-ordering assertions marked `duplicate_of: tests/RegressionTimelineHeaderTests.swift:vacuous-in-slot-ordering`; one `notes_for_chair` entry (the Spacer/jitter layout reasoning behind a rejection). Seed pass: `notes_for_chair` empty, no ledger to dedupe against. The chair honored the duplicate (appended `panel:gemini` to the existing id's sources, minted no second id). |
| Late iCloud duplicates caught by the settle pass | **observed — and the settle pass cannot catch this one** | No `archive` ran this loop, and `find .review-loop -name '* 2*'` was empty at the conclusions commit (2026-09-20 20:51). On 2026-09-26, while committing this report, `git status` showed `archive/20260920-190516-bd73178/{ledger.json,rounds.md,verdict.json}` DELETED: iCloud had renamed the previous loop's archived conclusions to `ledger 2.json` / `rounds 2.md` / `verdict 2.json` (file mtimes unchanged, Sep 19) some time in the six days after the archive was made and committed. Plain names missing ⇒ moved the ` 2` files back. See defect -0. |
| `suites` table appearing in a closeout | **not observed** | `fragments/round-2-closeout.json` has no top-level key besides `findings`; the report's Closeout section has no suites table. The reviewer put the counts (297/0, 29/14/0) in its prose hand-back and in finding notes only. |
| `mutate.py` baseline-red / dirty refusals; `--allow-dirty` abuse | not observed | Transcript grep: every `--allow-dirty` occurrence is agents reading the script's docstring; no invocation used it. No refusal was reported. |
| Token counts for any CLI lane | observed (codex only) | codex `total_tokens` 11,756 / 16,707; gemini none. |

## Keep

- **Reviewer-authored call-site mutants.** Every implementer manifest was
  re-run and killed in full (6/6, 7/7, 4/4), and the major still stayed
  `partial` in seed, round 1, round 2 and closeout because the reviewer
  wrote its own mutant each time (`linksAppleWeather: false`,
  `showsAppleWeatherLink: … == .weatherKit → false`, a rewrite back to the
  memberwise init with a literal `false`, and a class-gated UI probe). The
  manifest kill rate was never accepted as closure. This is the loop's
  value; do not trade it for cheaper verification.
- **Rejection recorded, not just status.** The report's "Fix review
  rejections" section shows the round-1 `fixed` claim overturned with the
  surviving mutant named, and the round-2 reviewer withdrew its own
  round-1 suggested close in writing ("a named model member passed at the
  call site would survive the same mutant") — the ledger carried both.
- **The blind verifier's demotions and rejections were checkable.** Each
  rejection named a code fact (the link's `.underlineStyle = .single`;
  `LegendColumn`'s tide chip; the `Spacer` before the conditional button)
  and the chair spot-checked rather than re-litigated. gemini filed every
  one of its rejected/demoted claims as a major at 0.7–1.0 confidence;
  the verifier is what kept those out of the ledger.
- **Per-mutant `test_cmd`** (new in 0.14.0): the round-1 mutant that only
  a UI test could kill ran the UI gate alone; the unit mutants did not
  pay for it.
- **`next-round`, `open closeout`, `panel-tally` (merge semantics),
  `render_report`** each did the whole bookkeeping in one call. The
  `diff` verb's EXCLUDED trailer did its job (see watch items).
- **Resume via `:waiting:<reason>` + HANDOFF.md.** The previous session's
  pause marker and note were sufficient to continue in a fresh session
  with nothing lost; no `resume` verb was needed.
- **Closeout punts file + orchestrator-copies-to-BACKLOG.** No implementer
  touched BACKLOG.md; three punt sketches reached BACKLOG intact,
  including one observation ("WeatherKit does load on this simulator")
  that contradicts a premise recorded in round 1.

## Defects, in impact order

**rl-0.14.0-20260920-weatherapp-0 — iCloud renamed three committed archive conclusions to ` 2` names DAYS after the archive and its commit; nothing in the plugin can see it.**
- What happened: the archive `20260920-190516-bd73178` (made 2026-09-20 19:05 by the previous session, its `ledger.json`/`rounds.md`/`verdict.json` committed in 60511ba) was clean at this loop's final hygiene check and conclusions commit (20:51, `find` empty). On 2026-09-26 `git status` listed those three files as deleted and the directory held `ledger 2.json`, `rounds 2.md`, `verdict 2.json` with their original Sep 19 mtimes. `REPORT.md` and `.phase` in the same directory were untouched.
- Expected: a committed archive stays byte-identical on disk; at minimum, a later loop's Setup hygiene check notices that an allowlisted name is missing next to a ` 2` twin.
- Smallest repro: not reproducible on demand — it is the iCloud file provider re-stamping a directory it synced. The 2026-09-19 report saw the same rename minutes after `archive`; this run shows the window is at least days, so `archive`'s settle re-check bounds nothing.
- Evidence: `git status` at the report commit; `ls -la .review-loop/archive/20260920-190516-bd73178/` before the fix; `git status` clean for those paths after `mv`.
- Cost: one mv and this paragraph — but only because a commit happened to touch the tree six days later. In a repo where nobody commits for a while the archived conclusions silently become untracked deletions.
- Mechanism: `hygiene_check.sh` should scan `archive/*/` (the 2026-09-19 report asked for this and it is still not scanned — the check said "clean" at 20:51 and would say "clean" now only because I fixed it by hand); Setup step 1 could run `git status --porcelain .review-loop/archive` and report any ` D` there as "iCloud rename — mv back". Longer term the HANDOFF's deferred `.nosync` scratch isolation is the real fix for the loop dir on synced volumes.

**rl-0.14.0-20260920-weatherapp-1 — `.dispatched` counter read 0 with one agent live; the `:dispatched` mark was then stripped by an unrelated return.**
- What happened: I issued `printf 'round-2-implementing' > .review-loop/.phase`
  (Bash) and the closeout-implementer `Agent` call in the SAME turn, in
  parallel. Two turns later (a `panel_review.py wait` in between, no
  subagent had stopped), `.phase` read `round-2-implementing` with no
  suffix and `briefs/.dispatched` read `0`. I then dispatched the final
  panel-verifier (counter → 1, mark stamped); when it returned, the
  SubagentStop hook decremented to 0 and stripped the mark while the
  closeout implementer was still running (it returned ~9 minutes later).
- Expected: counter 1 after the implementer dispatch, 2 after the verifier
  dispatch, 1 after the verifier's return, mark intact throughout.
- Smallest repro (suspected): a Bash phase write and an Agent dispatch in
  one parallel tool-call batch. Not re-run in isolation; the ordering
  between my `printf` and the PreToolUse stamp is the only difference from
  the dispatches that stamped correctly (all six single-call dispatches in
  this run stamped and counted as documented).
- Evidence: this session's transcript at the closeout-implementer dispatch
  and the following `cat .review-loop/.phase; cat briefs/.dispatched` turn;
  `.phase` afterwards held `round-2-implementing:waiting:closeout-implementer-running`.
- Cost: one extra Bash turn; no stall (the `:waiting:` marker bridged it).
- Mechanism: have the stamp hook re-apply the suffix on PostToolUse of the
  Agent call (after any same-batch Bash has run), or have the skill say
  "write the phase in its own turn before the dispatch, never in the same
  batch". Also worth checking whether the counter file is written with the
  same race.

**rl-0.14.0-20260920-weatherapp-2 — rounds.md / verdict.json token figures miss usage recorded after `next-round`; the report's trend table shows implementer-only tokens.**
- What happened: `rounds.md` rows say Tokens 66,819 (round 1) and 53,736
  (round 2) — the implementer figures only; `verdict.json`
  `cumulative_tokens` is 317,856 while the ledger's `usage` (and the
  report header, which reads it) totals 599,948. The reviewer's tokens
  were recorded with `set-usage` AFTER each `next-round` because the
  harness delivers the reviewer's hand-back message (the fragment is
  ready, the round can close) BEFORE the task-notification that carries
  the token count. The skill's "note the task result's token count — pass
  it to next-round" assumes both arrive together.
- Expected: one number for a round's tokens everywhere in the report.
- Repro: close a round with `next-round … --usage implementer=N`, then
  `set-usage <ledger> N reviewer M`; the trend row is not updated.
- Evidence: `.review-loop/rounds.md`, `verdict.json`, `REPORT.md` lines
  13–14 vs 20–22.
- Cost: report inconsistency only (the Tokens section is right).
- Mechanism: render the trend table's Tokens column from `ledger.usage`
  at `render_report` time (the Tokens section already does), or have
  `set-usage`/`add-usage` rewrite the affected `rounds.md` row.

**rl-0.14.0-20260920-weatherapp-3 — implementers resolved `mutate.py` themselves and ran the stale 0.13.0 copy.**
- What happened: the skill has the orchestrator pass the mutate.py path to
  the REVIEWER only; `agents/implementer.md` says "RUN `mutate.py` on your
  own manifest" with no path. Both the round-2 and the closeout
  implementer found the script by searching the plugin cache and ran
  `…/0.13.0/scripts/mutate.py` (round 2 reported "I ran it with mutate.py
  0.13.0"; closeout: "I first ran on it by mistake … the 0.13.0 copy has no
  unmutated baseline and ignores per-mutant `test_cmd`"). The claimed kills
  happened to hold when the reviewer re-ran on 0.14.0, so no wrong verdict
  resulted.
- Expected: every agent runs the installed version's script.
- Repro: any implementer dispatch without an explicit path, on a machine
  where `~/.claude/plugins/cache/quiller/review-loop-tools/` still holds
  older versions (0.10.0, 0.12.0, 0.13.0 here).
- Evidence: implementer hand-backs for round 2 and closeout; transcript
  grep for `0.13.0/scripts/mutate.py` hits the round-2 (7) and closeout (8)
  implementer transcripts only.
- Cost: one wasted manifest run (~2–3 min) at closeout; a silent risk in
  round 2.
- Mechanism: put `${CLAUDE_PLUGIN_ROOT}/scripts/mutate.py` (or the resolved
  absolute path) in `implementer.md`, and have the skill's implementer
  dispatch template name it the way the reviewer's does. Optionally have
  the plugin prune or warn about stale cache versions.

**rl-0.14.0-20260920-weatherapp-4 — manifests over ~4 mutants cannot run under the Bash tool's 10-minute ceiling; every agent split them into scratch copies.**
- What happened: with ~2 min per xcodebuild mutant, the round-2 reviewer
  ran the 7-mutant manifest "in two VERBATIM parts (4+3)", the closeout
  implementer pre-flighted "as three scratch splits", the closeout
  reviewer "re-run verbatim in 3 splits". Each split is a hand-made copy
  of the manifest in the scratchpad plus extra turns.
- Expected: one command per manifest.
- Repro: a manifest whose mutants sum to > 600 s of test time.
- Evidence: hand-backs for round 2 reviewer, closeout implementer,
  closeout reviewer; scratch manifests under the session scratchpad
  (`mut/part-e.json`, `mut2/part-c.json`, …).
- Cost: roughly 2–4 extra turns per mutation run × 5 runs; not measured
  separately.
- Mechanism: `mutate.py --detach` + `mutate.py wait` mirroring
  `panel_review.py`, or a `--mutants a,b,c` selector so a split needs no
  scratch copy and the named manifest stays the artifact of record.

**rl-0.14.0-20260920-weatherapp-5 — the closeout `suites` table did not appear.**
- What happened: the closeout reviewer ran both full suites and reported
  the counts in prose and in finding notes; the fragment has no `suites`
  key and the report has no table (watch item above).
- Expected: per the watch item, a `suites` table in the Closeout section.
- Repro: closeout reviewer dispatch as the skill words it (my dispatch said
  "report the tree green or red explicitly" and named the filtered grep;
  it did not name a `suites` field — I do not know whether the agent
  definition asks for one).
- Evidence: `fragments/round-2-closeout.json` top-level keys = `findings`.
- Cost: none this run; the numbers reached BACKLOG by hand.
- Mechanism: if the field is meant to exist, `skeptical-reviewer.md` or the
  skill's closeout dispatch text should name it and `render_report` should
  show a placeholder when it is missing so the omission is visible.

## Friction

- **Hand-back before token count.** Every dispatch's result arrived as two
  messages: the agent's hand-back (actionable) and then, one turn later,
  the task-notification with `subagent_tokens`. Acting on the first means
  a separate `set-usage`/`add-usage` call per dispatch (9 this run) and
  causes defect -2. The skill text could say to expect the two messages
  and record usage from the notification.
- **Nine WATCH LIST placeholders filled by string substitution.** Fine, but
  the "closeout diff" placeholder came pre-filled with "the commit with no
  round after it" AND the `<!-- orchestrator fills -->` marker, so the
  substitution had to special-case it.
- **Nothing in the skill covers resuming a paused loop.** The previous
  session improvised HANDOFF.md and a `:waiting:fresh-session-restart`
  marker; Setup step 1 only knows FINISHED or ABANDONED. It worked, but a
  third state ("paused: resume from `.phase`") would have saved reading.
- **`rounds.md` carries no timestamps**, so "epoch of the loop's first
  rounds.md entry" (this report's instructions) had to be reconstructed
  from fragment mtimes.
- **The report's Panel section needs a `Kept` definition beside it.** The
  table says gemini final 1 confirmed / 2 demoted / 1 duplicate / 2
  rejected, kept 3/6 — consistent with the verifier this run (the
  2026-09-19 disagreement did not recur), but a reader still has to know
  kept = confirmed + demoted.

## Decisions taken without the human

- **Ran the panel final pass on standing consent.** The contract wants
  remote lanes stated plainly and consented; the machine-local consent
  from 2026-09-13/19 existed and the seed pass had already run under it
  in the previous session with the human present. I did not re-ask.
- **Resumed the paused loop instead of archiving.** HANDOFF.md, written in
  the previous session with the human, said "resume, do not archive"; I
  treated that as the human's answer to Setup step 1.
- **Ran the closeout implementer concurrently with the panel final lanes
  and verifier** (the skill allows it). The verifier was told to read
  `git show 8b5aed0:` rather than the working tree, and not to build.
- **Left the open major to the human.** `diminishing` needed no question;
  the major is not `introduced_by_fix`, so closeout could not take it. I
  did not raise `max_rounds` for a round 3 — the contract does not offer
  that at a `diminishing` stop, and the human was reachable. It is the
  first item in BACKLOG's new section and the second WATCH LIST line.
- **Chose the usage window start** (`--since 1789945700`, the seed diff's
  mtime) so the previous session's seed panel is in the window; that also
  admits 9 requests / 174K of that session's pause turns.
- **Did not write a `docs/reports` feedback file at loop end** (the
  previous two runs had one). Written now, on request.

## Seen again

Earlier reports in `~/.claude/plugins/marketplaces/quiller/docs/inbox/`.

| Earlier item | Status this run |
|---|---|
| loop-tooling-feedback-2026-09-19 #1 — lanes inherit poisoned `NODE_OPTIONS` | worked around pre-emptively (`env -u NODE_OPTIONS` on every `run`); not re-tested |
| 2026-09-19 #2 — no per-lane rerun | fixed per the 0.14.0 skill text (`--lanes`, `--force`); not exercised — no lane failed |
| 2026-09-19 #3 — iCloud `ledger 2.json` inside a fresh archive | **still happens, worse** — the rename hit a six-day-old, already-committed archive (defect -0); `hygiene_check.sh` still does not scan `archive/` |
| 2026-09-19 #4 / oct-pool #4 — phase marker vs overlapping dispatches | **still happens** — see defect -1 (counter present in 0.14.0 but read 0 with one agent live) |
| 2026-09-19 #5 — mutate.py has no per-mutant test command | **fixed for us** — round-1 mutant (b) carried its own UI `test_cmd`, honored by the reviewer's re-run |
| 2026-09-19 #6 — a dispatch notified twice | not observed — each of the 9 dispatches notified once |
| 2026-09-19 #7 — verifier `kept` ≠ tally `kept` | fixed for us — consistent in both passes |
| review-loop-0.13.0-feedback-oct-pool #1 — pathspec excludes blind the panel | **fixed for us** — EXCLUDED trailer present; 0/13 candidates about the hidden file |
| oct-pool #2 — `run` accepted an empty diff | not exercised |
| oct-pool #5 — `commit_guard` fires when no loop is live | fixed for us — the conclusions commit after `.phase = done` went through |
| oct-pool #8 / 0.13.0 #9 — WATCH LIST "round 1 diff" lumps in the closeout | **fixed for us** — candidates are `60511ba..a6493b9`, `a6493b9..8b5aed0`, closeout `8b5aed0..HEAD` |
| 0.13.0 #3 / oct-pool #7 — lane timeouts vs the Bash ceiling | fixed for us — `run --detach` + `wait` returned within one call both passes |
| 0.13.0 #7 — verifier side-observations have no channel | fixed for us — `notes_for_chair` used once (final pass) |
| 0.13.0 #8 — two rules for BACKLOG.md | fixed for us — punts file used; no implementer touched BACKLOG |
| 0.13.0 #10 — codex exposes no usage | fixed for us — codex `total_tokens` recorded both passes; gemini still exposes none |
| 0.13.0 #4 — `read_guard` false positive on heredoc content | not observed |

## Host-repo recommendations

- **Close the open major** (`tests/TimelineScreen.swift:meta-line-call-site-untested`)
  with the reviewer's structural fix: store `loadedSourceKind` on
  `TimelineHeader`, compute `showsAppleWeatherLink` from it (three test
  call sites in `CompactWidthLayoutTests.swift`), then make the
  attribution UI test's missing-mark branch fail rather than skip
  (`missing-mark-skips-instead-of-failing`, fix_risk). Needs its own
  round or a small scoped loop.
- **Fix the wrong premise** in the comment above
  `testMetaLineNamesTheLoadedSource` ("a simulator build cannot load
  WeatherKit") — WeatherKit loads on `WeatherTimeline-Claude` in ~21 s.
  The premise steered round 2's approach.
- **`weatherkit-restore-window`**: register the Open-Meteo restore
  teardown immediately after the WeatherKit tap and assert it, or a
  failed run leaves the shared simulator on WeatherKit for the next loop.
- **`.qa-loop/TESTCASES.md`** still scripts against the deleted "N km to
  tide station" header clause (~77, ~177, ~263–269).
- **Two product calls** need a yes/no: the Apple Weather link outside
  VoiceOver's Links rotor (reachable via the explicit action), and the
  removed subtitle-tap tide shortcut (legend chip still works). Both are
  shipped behaviour from f044c29; wontfix if intentional.
- **Anchor `.gitignore`'s `REVIEW-*` to the root** (`/REVIEW-*`) so `docs/reports/review-loop-tools-*.md` is not ignored on a case-insensitive checkout.
- 14 of 29 UI tests skip in files this loop never touched
  (RegressionMapTests, RegressionPlacesSearchTests,
  MapRegistrationHarnessUITests) — the same `XCTSkipIf(true)` convention.

## Environment and harness artifacts

- **`.gitignore:18: REVIEW-*`** (case-insensitively, via macOS `core.ignorecase`) matches this report's mandated filename `review-loop-tools-…md`, so `git add` by explicit path refused it; the previous two reports were named `loop-tooling-feedback-*` and dodged the rule. Committed with `git add -f <path>` (the loop is `done`, so `commit_guard` is not armed). The rule is presumably meant for root-level `REVIEW-*.md` seed files; anchoring it (`/REVIEW-*`) is the host-repo fix.
- **Task-notification `output-file` paths pointed at the PREVIOUS session's
  directory** (`…/87ef1cd1-…/tasks/<id>.output`) although this session is
  `a47e3cef-…` and `loop-usage.py` finds the subagent transcripts under
  `a47e3cef-…/subagents/`. Harmless, but the report's transcript grep had
  to look in both.
- The checkout is on iCloud: every build needs `-derivedDataPath` in the
  session scratchpad; all agents complied.
- One shared Mac, one dedicated simulator (`C6BAB203-…`); every dispatch
  named it; no cross-session interference observed.
- `NODE_OPTIONS` from the terminal wrapper (see Seen again) — pre-empted.
- The orchestrating session was fresh (0.4 MB at invocation per the
  session guard); the previous session's guard warning is what caused the
  pause/resume.

## Wishes

- `hygiene_check.sh` scans `archive/*/` for ` 2` twins with the plain name missing, and Setup reports ` D` paths under `archive/`.
- `render_report` derives the trend table's Tokens column from the ledger.
- Implementer agent definition names the installed `mutate.py` path.
- `mutate.py --detach`/`wait`, or `--mutants` selection, for manifests longer than the Bash ceiling.
- A "paused" state in Setup step 1 that resumes from `.phase` and a HANDOFF note.
- Timestamps in `rounds.md` rows.
- Skill text: "the hand-back arrives before the token notification; record usage from the notification".
- Prune (or at least warn about) stale plugin versions in the cache.
- A `suites` field named in the closeout dispatch and rendered (with a "missing" placeholder) in the report.

## Appendix

Run summary:

```json
{
  "plugin": "review-loop-tools",
  "version_installed": "0.14.0",
  "version_running": "0.14.0",
  "date": "2026-09-20",
  "repo": "weatherapp",
  "platform": {"macos": "26.4.1 (25E253)", "claude_code": "2.1.283", "session_model": "claude-fable-5-1"},
  "settings": {
    "mode": "scope",
    "scope": "f044c29^..f044c29 -- :!prompts.md",
    "max_rounds": 2,
    "token_budget": null,
    "unattended": false,
    "panel": {"rounds": "seed+final", "lanes": [
      {"name": "codex", "model": "gpt-6-astra", "timeout_s": 900, "max_diff_tokens": 32000},
      {"name": "gemini", "model": "gemini-3.5-flash", "timeout_s": 600, "max_diff_tokens": 32000}
    ]}
  },
  "resumed_from_pause": true,
  "rounds": [
    {"round": 1, "sha_start": "60511ba", "sha_end": "a6493b9", "blockers": 0, "majors": 1, "minors": 5, "closed": 1, "new": 0, "reopened": 0, "promoted": 0, "net": 1, "decision": "continue"},
    {"round": 2, "sha_start": "a6493b9", "sha_end": "8b5aed0", "blockers": 0, "majors": 1, "minors": 5, "closed": 0, "new": 0, "reopened": 0, "promoted": 0, "net": 0, "decision": "diminishing"}
  ],
  "closeout": {"sha": "e0890ec", "eligible": 5, "fixed": 4, "partial": 1, "new_minors": 7, "suites": {"unit": {"executed": 297, "failures": 0}, "ui": {"executed": 29, "skipped": 14, "failures": 0}}},
  "stop": {"condition": "diminishing", "reason": "net <= 1 for two rounds, no open blockers, no new blockers/majors"},
  "findings": {"total": 14, "by_severity": {"blocker": 0, "major": 1, "minor": 13}, "by_status": {"fixed": 5, "partial": 2, "open": 7, "disputed": 0, "wontfix": 0}, "introduced_by_fix": 1},
  "mutation": {"round1": "6/6", "round2": "7/7", "closeout": "4/4", "reviewer_survivors": 4},
  "panel": {
    "0": {"codex": {"filed": 1, "confirmed": 1, "demoted": 0, "duplicate": 0, "rejected": 0}, "gemini": {"filed": 5, "confirmed": 2, "demoted": 1, "duplicate": 0, "rejected": 2}},
    "final": {"codex": {"filed": 1, "confirmed": 1, "demoted": 0, "duplicate": 0, "rejected": 0}, "gemini": {"filed": 6, "confirmed": 1, "demoted": 2, "duplicate": 1, "rejected": 2}},
    "lane_runs": {"0": {"codex": {"elapsed_s": 72.8, "total_tokens": 11756}, "gemini": {"elapsed_s": 225.2}}, "final": {"codex": {"elapsed_s": 95.9, "total_tokens": 16707}, "gemini": {"elapsed_s": 207.0}}}
  },
  "commits": ["a6493b9", "8b5aed0", "e0890ec", "c2dba3a"]
}
```

Usage table (`loop-usage.py --since 1789945700`, effective tokens):

```json
{
  "since_epoch": 1789945700,
  "dispatches": [
    {"role": "panel-verifier", "label": "Verify seed panel candidates", "requests": 14, "effective": 141763, "reported": 49603, "wall_s": 133},
    {"role": "skeptical-reviewer", "label": "Seed review of scope f044c29", "requests": 42, "effective": 388270, "reported": 80183, "wall_s": 470},
    {"role": "implementer", "label": "Round 1 implementer", "requests": 31, "effective": 258333, "reported": 66819, "wall_s": 761},
    {"role": "skeptical-reviewer", "label": "Round 1 reviewer", "requests": 26, "effective": 246700, "reported": 67515, "wall_s": 697},
    {"role": "implementer", "label": "Round 2 implementer", "requests": 26, "effective": 208745, "reported": 53736, "wall_s": 432},
    {"role": "skeptical-reviewer", "label": "Round 2 reviewer", "requests": 23, "effective": 207526, "reported": 59248, "wall_s": 604},
    {"role": "panel-verifier", "label": "Verify final panel candidates", "requests": 23, "effective": 223085, "reported": 66611, "wall_s": 250},
    {"role": "implementer", "label": "Closeout implementer", "requests": 41, "effective": 314089, "reported": 67095, "wall_s": 1052},
    {"role": "skeptical-reviewer", "label": "Closeout reviewer", "requests": 44, "effective": 458917, "reported": 89138, "wall_s": 1320}
  ],
  "per_role": {
    "skeptical-reviewer": {"effective": 1301413, "reported": 296084, "ratio": 4.4},
    "implementer": {"effective": 781167, "reported": 187650, "ratio": 4.2},
    "panel-verifier": {"effective": 364848, "reported": 116214, "ratio": 3.1}
  },
  "subagents_total": {"effective": 2447428, "reported": 599948, "ratio": 4.08},
  "orchestrator": {"this_session": {"requests": 57, "effective": 1178406, "note": "includes post-loop turns through 2026-09-26"}, "previous_session_tail": {"requests": 9, "effective": 174274}},
  "grand_total_effective": 3800108,
  "ledger_usage": {"0": {"panel-verifier": 49603, "reviewer": 80183}, "1": {"implementer": 66819, "reviewer": 67515}, "2": {"implementer": 120831, "reviewer": 148386, "panel-verifier": 66611}}
}
```
