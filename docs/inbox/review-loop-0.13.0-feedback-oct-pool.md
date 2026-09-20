# Review loop v0.13.0 — second run: the October pool extension (usage and feedback)

Run of 2026-09-20 12:33 → 13:43, scope `026fff0..e409698` — the daily-pool extension to 92 days
(one commit, 15 files; the review scope excluded `prompts.md`, the two baked-solution files and the
flawless-certificate cache by pathspec, so the reviewed diff was 11 files / 274 lines). Plugin
`review-loop-tools@quiller` **0.13.0**, same panel as the 2026-09-13 run
([`review-loop-0.13.0-feedback.md`](review-loop-0.13.0-feedback.md)): codex `gpt-6-astra`, gemini
`gemini-3.7-flash` (free-tier API key), ollama `qwen3-coder:30b`. Chair pinned Opus, panel-verifier
pinned Sonnet, implementer inherited the session model (Fable 5.1). Same session as the extension
itself, but the transcript was 1.0 MB at the gate (the hook said "fine for a loop"); unattended
throughout, every question took the documented default.

Measured with `tools/loop-usage.py --since 1789921980` (12:33, the extension commit) against the raw
session transcripts — effective = input ×1 + cache_read ×0.1 + cache_write ×2 + output ×5,
deduplicated by `requestId`. External lanes are not in the transcripts and are not counted.

---

## 1. Headline

| | |
|---|---|
| Wall clock | ~1 h 10 min (12:33 → 13:43); 33 min of it is the closeout reviewer's full iOS suite |
| Rounds | panel seed + chair seed + 1 round + panel final + closeout (scope mode, `max_rounds` 2, no escalation) |
| Stop condition | **converged** at round 1 — 0 blockers, 0 majors, none introduced |
| Claude dispatches | 7 (3 reviewer, 2 implementer, 2 panel-verifier), 0 retries, 0 pauses, 0 model fallbacks |
| Panel lane runs | 6 (3 per pass), all `ok` — gemini answered both times (fresh daily quota) |
| Panel candidates | 32 filed (17 seed, 15 final) → **0 kept**, 32 rejected with citations |
| Findings | 9 — 0 blockers, 1 major, 8 minors; 0 via panel; 2 `introduced_by_fix` (both doc-only) |
| Outcome | 9 fixed, 0 wontfix, 0 disputed, 0 open; one shipped behavior change (the within-run pair ban, `07aa37c`) |
| Suites at closeout | node 173 (+2), Swift unit 17, UI 75 executions — all green, 0 skipped |
| Mutants | 5 in one round-1 manifest (4 killed, 1 declared survivor); 5/5 matched on the reviewer's re-run |

## 2. Cost

| Dispatch | Requests | Effective tokens | Ledger-reported |
|---|---:|---:|---:|
| Seed panel-verifier (17 candidates) | 21 | 175,765 | 50,070 |
| Seed review (chair) | 35 | 411,052 | 99,320 |
| Round 1 implementer | 20 | 210,443 | 60,340 |
| Round 1 review (+ mutation re-run) | 27 | 241,788 | 59,207 |
| Closeout implementer (7 minors) | 10 | 106,112 | 40,396 |
| Final panel-verifier (15 candidates) | 25 | 199,773 | 56,395 |
| Closeout review (full suites) | 45 | 773,032 | 76,711 |
| **Subagents** | 183 | **2,117,965** | **442,439** |
| Orchestrator (loop only, 12:33 → report) | 47 | 1,105,908 | — |
| **Loop total** | 230 | **3,223,873** | |
| *(For scale: the October extension itself, before the loop)* | *27* | *529,313* | |

Effective/reported for subagents: **4.8×** (4.7× last run). Reviewers are 67% of subagent cost
again; the closeout review alone is 36% — its 280 K cache-write tokens are the filtered output of
six UI class groups. The two verifier dispatches cost 375 K effective (18% of subagent cost) and
kept **nothing**: 32 candidates, 0 confirmed. Against the 2026-09-13 run (2.99 M for 6 findings in
1.5 h) this is 3.22 M for 9 findings in 1 h 10 min — a comparable loop on a smaller diff; the
extra cost is the full iOS suite, which this scope genuinely needed (bundled data changed).

## 3. What the loop got right

- **The chair found the one real major that neither the author nor 17 panel candidates saw.**
  Nothing tested that the iOS bundle copies of the pool and solutions equal `data/`; both suites
  would have stayed green with a stale 61-day bundle. Latent today, live at the November append —
  exactly the class of defect a scoped review exists for. Fixed with a byte-identity test and two
  mutants that drift each copy.
- **The reviewer verified by doing, not by reading.** Round 1 re-ran the mutation manifest
  (5/5 matched), and rather than accept "no starvation" it ran the builder at `--days 154` against
  the tracked cache to prove the new pair ban still fills 62 days. Closeout recounted every figure
  the docs now claim (92/69/23, the family frequencies, the 23 universal-Silver indices) from the
  data files, and ran the month-boundary assertion against synthetic lengths 61/62/91/92/100/122.
- **An honest declared survivor.** The implementer's manifest declared one mutant `expect:
  survived` (the validator's pair check is shielded by the selector ban — defense in depth), and the
  reviewer judged it honest rather than a hole. That is the manifest format being used as intended.
- **Closeout measured instead of copying.** The closeout brief carried the reviewer's figures; the
  implementer recounted them from the data before writing them into four docs and the QA
  contract, and said so.
- **`next-round`, `add-usage`, `panel-tally`, `render_report`** all did what the skill says; the
  one-call round close and the rendered report needed no hand edits beyond the WATCH LIST.
- **`notes_for_chair` works when asked for.** Both verifier dispatches were told to include it;
  the seed note (the `calMonthRange` test never loads the real pool) became a chair finding and was
  fixed. Last run the verifier improvised the field; it should be schema.

## 4. What cost time or nearly went wrong

1. **Pathspec excludes blind the panel — 5 of 32 candidates were that one misreading.** The
   skill recommends excluding journals and large files from the scope, and I excluded the two
   220 KB solution files and the certificate cache. Every lane then saw a pool that grew by 31
   days and *no* change to the solutions, and filed exactly that: codex's only candidate in BOTH
   passes, and three of gemini's (two of them "blocker, confidence 1.0"). The verifier refuted
   each with `git show --stat`, but that is 5 refutations paid for by a view the tooling itself
   produced. Fix in the `diff` verb: always emit the *unfiltered* `--stat` alongside the filtered
   diff, with excluded-but-changed paths marked "(changed in range; excluded from this view)",
   and put that line in the lane prompt and the verifier dispatch. A lane that knows a file
   changed but is hidden will not file "was not updated".
2. **`panel_review.py run` accepted an empty diff and reported success.** My first `diff` call
   passed the range and its excludes as ONE quoted argument (the skill's UNQUOTED warning is
   there; I missed it once), so `git diff` failed with "bad revision", `round-0.diff` was 0 lines
   — and the panel run I had already launched executed against it and printed `status: ok,
   filed: 0` for all three lanes. A no-op that looks like a clean pass. `run` should refuse a
   zero-line diff, and `diff` should exit non-zero on git failure so a chained `&&` stops.
3. **`qwen3-coder:30b` is now 0 for 40.** Ten candidates per pass, confidence 0.6–0.9, both passes,
   same failure modes as last run: tests that "still say 61" in a diff whose hunks show 92;
   a byte-compare test described as "only compares file sizes"; a `version` field "missing" from a
   file whose line 2 is `"version": 4`. The verifier's two dispatches spent most of their 375 K on
   it. The 2026-09-13 report asked for a kept-rate cap; nothing changed in 0.13.0 between the runs,
   so this is a repeat with a larger sample. Concretely: after a lane scores 0/N in a pass, cap it
   at 3 candidates for the next pass; after 0/N in two consecutive runs, `probe` should say
   "disabled by precision" and require an explicit re-enable.
4. **The phase marker is a single slot but the skill encourages two live dispatches.** I ran the
   panel final pass and the closeout implementer in parallel (nothing in the skill forbids it and
   it saved ~3 min). When the implementer returned, the SubagentStop hook stripped `:dispatched`
   while the panel-verifier was still running; the Stop hook then blocked my turn end twice with
   "round in flight — dispatch now or say you are waiting". I wrote `:waiting:<reason>` by hand
   each time. Either the strip should happen only when no other dispatched agent is live, or the
   skill should say "one dispatch at a time" plainly.
5. **`commit_guard` fires when no loop is live.** The extension's own commit (before the loop was
   invoked, with the previous loop's `.phase` at `done`) was blocked on `git add -A` with
   "blocked during a loop". Staging by path is the right habit and I did it, but the message is
   false and the guard's scope is undocumented — say "while `.review-loop/` exists" if that is the
   rule.
6. **Gemini's free tier worked twice today — which confirms the previous diagnosis.** Both passes
   answered on `gemini-3.7-flash` because the daily quota was fresh; it filed 10 candidates, kept
   0. Nothing to fix in the plugin beyond §4.1 of the previous report (tier in `probe`, model
   fallthrough); recording the data point.
7. **Lane timeouts vs the Bash ceiling, again.** Ran detached from the start because HANDOFF
   says to; the skill still does not. Two sentences in the skill would spare every new
   orchestrator the discovery.
8. **The WATCH LIST's "round 1 diff" candidate still lumps round 1 with the closeout commit**
   (`e409698..HEAD`) — repeat of the previous report's item 9. Render the closeout commit as its
   own candidate; here it is the commit whose doc figures the next QA loop drives against.
9. **`NODE_OPTIONS` was the environment's trap, not the plugin's — but it reached the panel.** The
   shell exports a `--require` preload that no longer exists on disk; every `node` dies before
   `main` unless `NODE_OPTIONS=` is cleared. I put the clearing into every dispatch; gemini and
   ollama still filed the HANDOFF note that documents it as a "misleading" finding. Not actionable
   for the plugin; noted so the next run's orchestrator sees it in one place.

## 5. Judgement calls made without the owner

- **Excluded the two solution files and the certificate cache from the scope by pathspec** (large
  generated data; the reviewer was told to open them on disk). Correct for the chair, and the
  cause of §4.1 for the panel.
- **Ran the panel** on the standing consent of 2026-09-13 (remote lanes approved by the owner,
  codex/gemini may receive the diff, ollama local). Kept ollama enabled despite its 0/20 history so
  the run is comparable with the last one; the next orchestrator should consider disabling it.
- **Ran the closeout implementer concurrently with the panel final pass** (§4.4). The panel's
  materialized diff predates the closeout commit by design; the closeout reviewer verified that
  commit separately.
- **Kept the within-run pair ban** (the loop's one behavior change) rather than punt it as
  design-sized: 18 lines in the selector/validator, forward-looking only, published bytes
  untouched, starvation disproved by the reviewer. It is the first item on the report's WATCH LIST.
- **Took unattended defaults everywhere** (`REVIEW_LOOP_UNATTENDED=1`); no question actually
  arose — the loop converged at round 1.
- **Created a dedicated simulator** (iPhone 16 Pro / iOS 26.5; deleted at the end); every dispatch
  named that one udid.
- **Changed no source myself.** All nine findings were fixed by the implementer dispatches
  (`07aa37c`, `4f4e7fb`).
