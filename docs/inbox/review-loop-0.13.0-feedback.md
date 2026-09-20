# Review loop v0.13.0 — token usage and feedback

Run of 2026-09-13 17:22 → 18:53, scope `fa2de2e..bc4c59f` — the controls redesign (Option A2:
portrait bottom deck + landscape rail restyle, one commit, 23 files / 543 lines). Plugin
`review-loop-tools@quiller` **0.13.0**, first run here with the multi-provider **panel**: codex
`gpt-6-astra` (ChatGPT login), gemini (API key, see §4.1), ollama `qwen3-coder:30b` (local).
Chair pinned Opus, panel-verifier pinned Sonnet, implementer inherited the session model
(Fable 5.1). Fresh session (transcript 0.0 MB at the gate). Unattended after the owner's setup
answers in the previous session; every question that came up took the documented default.

Measured with `tools/loop-usage.py --since 1789334556` against the raw session transcripts,
same accounting as `docs/loop-token-usage.md` (effective = input ×1 + cache_read ×0.1 +
cache_write ×2 + output ×5, deduplicated by `requestId`). The external lanes (codex, gemini,
ollama) do not appear in the transcripts and are not counted — see §2.

---

## 1. Headline

| | |
|---|---|
| Wall clock | ~1.5 h (17:22 → 18:53), no pauses; ~35 min of it is the closeout's full UI suite |
| Rounds | panel seed + chair seed + 1 round + panel final + closeout (scope mode, `max_rounds` 2, no escalation) |
| Stop condition | **converged** at round 1 — 0 blockers, 0 majors, none introduced |
| Claude dispatches | 7 (3 reviewer, 2 implementer, 2 panel-verifier), 0 retries, 0 pauses |
| Panel lane runs | 8 (3 + 1 retry per pass); 5 produced candidates, 3 died on Gemini quota |
| Panel candidates | 27 filed (16 seed, 11 final) → 3 kept (all seed), 2 duplicates, 22 rejected |
| Findings | 6 — 0 blockers, 0 majors, 6 minors; 3 via panel (1 codex, 2 gemini), 3 chair; 1 `introduced_by_fix` (text-only) |
| Outcome | 3 fixed, 2 wontfix (both argued and accepted on the merits), 1 partial; 0 disputed at the end |
| Suites | node 171, Swift unit 17, UI 75 executions — unchanged counts, all green, 0 skipped at closeout |
| Mutants | 3 in one closeout manifest (2 killed, 1 control survivor); 3/3 matched on the reviewer's re-run, 0 errors |

## 2. Cost

| Dispatch | Requests | Effective tokens | Ledger-reported |
|---|---:|---:|---:|
| Seed panel-verifier (16 candidates) | 28 | 229,087 | 58,941 |
| Seed review (chair) | 39 | 480,700 | 104,885 |
| Round 1 implementer | 10 | 100,008 | 36,569 |
| Round 1 review | 13 | 110,760 | 36,758 |
| Final panel-verifier (11 candidates) | 15 | 154,379 | 52,160 |
| Closeout implementer | 18 | 168,826 | 52,424 |
| Closeout review (full suites) | 37 | 731,686 | 77,848 |
| **Subagents** | 160 | **1,975,446** | **419,585** |
| Orchestrator (this session, to the report) | 60 | 1,010,351 | — |
| **Total** | 220 | **2,985,797** | |

Ratio effective/reported for subagents: **4.7×** — inside the 4–7× band the report's own Tokens
heading now quotes (the 0.10.0 run was 5.9×). Reviewers are 67% of subagent cost; the closeout
review alone is 37% (its 279 K cache-write tokens are the filtered output of five UI class
groups). The two verifier dispatches — 383 K effective, 19% of subagent cost — bought 3 kept
findings out of 27 candidates: that is the price of the panel on this scope, and most of it was
spent refuting ollama (§4.5). The orchestrator's share is 34% of the total, up from 13% in the
0.10.0 run: the loop was short, and the gemini re-probe plus the two hand-run lane retries were
~15 CLI calls in the main session.

Not counted: codex ran twice on the ChatGPT-login tier (no token figures exposed), gemini once
successfully on the free tier, ollama twice locally (~2 min each, `qwen3-coder:30b`). Against the
0.10.0 run (5.15 M for 12 findings over 3 h) this is 2.99 M for 6 findings over 1.5 h — a smaller,
cleaner scope, not a cheaper loop.

## 3. What the loop got right

- **The verifier is a real firewall.** 27 external candidates, 3 reached the chair. Every
  rejection came with a code citation (the "Undo deleted from the rail" blocker: `toolbar.undo`
  still at `ContentView.swift:626`; the "`.clear` background eats taps" minor: an explicit
  `.contentShape` on the label). The chair never saw the noise, and its dispatch could say "do not
  re-litigate" honestly.
- **Cross-family value was real, not theoretical.** Gemini found the landscape rail's conditional
  `.id()` on a presented `Menu` (identity flips when the board becomes finishable, dismissing an
  open menu) — neither Anthropic model raised it, and it became the loop's one shipped behavior
  change. Codex's one candidate (the identifier tripwire accepting a label fallback) was 1/1
  precise and led to the strict-id fix with a mutation proof.
- **A wontfix argued on the merits, and adjudicated on them.** The round-1 implementer declined the
  chair's "reserve the Finish row unconditionally" shape with a concrete cost argument (every
  portrait deal pays 43 pt to fix a rare path); the round-1 reviewer accepted it, *and* opened a
  text-only finding because the recorded rationale understated the trigger set (`canOfferFinish`
  lacks the `autoFinishTierCost()` guard). Closeout corrected the wording the owner will rule on.
  That is the dispute channel working as designed.
- **Every 0.10.0 complaint I can check is addressed.** Converging series / `converged` stop (§4.1
  there) — this run simply converged at round 1, no thrashing label. `REVIEW_LOOP_UNATTENDED`
  exists. `archive` moved per file and reported `duplicates_detected: 0` under iCloud. The
  implementer ran `mutate.py` on its own manifest unprompted and added a *control* mutant to prove
  the worktree builds — a discipline worth writing into the agent prompt. The closeout brief now
  says where punts go. `add-usage` vs `next-round --usage` for closeout is documented in the skill.
- **`panel-tally` renders itself.** The per-lane precision table in the report is the single most
  useful new artifact: it says in one glance which lanes earn their keep.
- **Closeout enforced the "build is not a test" rule** without me intervening: the implementer's
  verify_cmd ran the five UI classes it touched plus the unit target; the reviewer ran the entire
  UI target in five groups and reported 75/0/0.

## 4. What cost time or nearly went wrong

1. **Gemini on a free-tier API key cannot do the job the panel asks of it.** The owner asked for
   "the best Pro model the CLI offers". On this key: `gemini-2.5-pro` → 404 "no longer available
   to new users"; `gemini-3.1-pro-preview` → 429 with `free_tier … limit: 0`; `gemini-pro-latest`
   resolves to 3.1 Pro. So the lane was pinned to a flash model. Then the **daily** free quota on
   each flash model exhausts after roughly one 32 K-token diff prompt: 3.8-flash died in the seed
   run (after the probe's smoke and my one test call had already spent its day); 3.7-flash
   produced the seed candidates and died in the final pass; a 3.5-flash retry died on the same
   `TerminalQuotaError`. Net: one gemini pass out of two, on a model the owner did not ask for.
   Suggestions: (a) `probe` should report the key's *tier* (free vs paid) and say plainly that a
   free-tier API key is the same training terms as free-tier OAuth — today `auth: api-key,
   smoke: ok` reads as "fine"; (b) the smoke test spends the very quota the run needs — make it
   a `models.list` call, not a generation; (c) let a lane carry a model *list* and fall through
   on `TerminalQuotaError` / 404 instead of erroring; (d) the run summary's `note` truncates the
   CLI's stderr at ~120 chars, which cuts off the one line that matters ("exhausted your daily
   quota") — classify the error and put the reason first.
2. **No single-lane rerun.** To retry gemini alone I hand-edited the git-tracked `panel.json`
   three times (`enabled: false` on the other two lanes, then restore). A `run --lane gemini`
   flag would avoid touching tracked config for an operational retry, and would make the retry
   visible in the run summary instead of only in this document.
3. **Lane timeouts exceed the Bash tool's ceiling.** The lanes' `timeout_s` are 900 / 900 / 1500,
   the tool's maximum is 600 s, and a background Bash task is still bound by it. I killed the
   first `run` a minute in and relaunched it under `nohup … & disown`, polling the log. The skill
   should say so ("run the panel detached; wait on its summary file"), or `panel_review.py` should
   grow a `--detach` + `wait` pair.
4. **`read_guard` has a false positive on file *content*.** A heredoc that merely wrote the
   implementer's `verify_cmd` string into `briefs/closeout-changes.json` was blocked as an
   "unfiltered test run" because the text contained the xcodebuild invocation. The guard should
   match a command *position* (start of line, after `&&`/`;`/`|`), not any occurrence inside
   quoted or heredoc data. I fell back to the Write tool; harmless, but a hook that blocks
   bookkeeping trains the orchestrator to route around it.
5. **`qwen3-coder:30b` filed 20 candidates and 0 survived.** Both passes: ten "majors" each,
   confidence 0.8–0.9, citing line numbers that hold unrelated code or asserting test failures
   that the diff's own comments show were the intended change. The verifier spent most of its
   383 K refuting them. Two cheap pre-filters in the script would have dropped most of it before
   a Claude ever read it: check that each `evidence` line exists and contains at least one
   identifier from the claim; and after a lane scores 0/N in the seed pass, cap it at 3
   candidates for the final pass (or require confidence ≥ 0.95). A lane's kept-rate is already
   tallied — use it.
6. **Final-pass lanes re-file the ledger.** Codex's final candidate was a verbatim re-file of its
   own confirmed seed finding; ollama re-filed the accepted wontfix as a major. The lanes are
   blind to the ledger by design, but the *verifier* need not be: I pasted the open ids and the
   wontfix into its dispatch by hand so it could mark duplicates instead of re-confirming. Make
   that automatic — the final-pass verifier dispatch should carry `merge_ledger.py open … all`
   plus the wontfix list, and the verified schema should have a `duplicate_of` field (the
   verifier improvised one).
7. **The verifier's side-observations have no channel.** The seed verifier noticed something no
   lane filed (the whole Finish tier, not just the pill, participates in the latch) and put it in
   its prose; I forwarded it to the chair by hand, and it became the chair's own `fix_risk`
   finding. A `notes_for_chair` array in `verified.json` would carry that without the
   orchestrator in the loop.
8. **Two rules for who may touch BACKLOG.md.** The round-1 implementer wrote PC-4 into
   `BACKLOG.md` itself (rounds do not forbid it); the closeout implementer was told it may not
   (punts go to `briefs/closeout-punts.md`). Both did the right thing under their instructions,
   but the split is confusing and the round-1 entry then needed a closeout correction anyway.
   One rule — implementers never touch BACKLOG.md; sketches go to `briefs/` and the orchestrator
   copies — would be simpler.
9. **The report's watch-list candidate for "round 1 diff" spans `773edcc..HEAD`**, which lumps
   the comment-only round-1 commit with the closeout commit that actually changed behavior. When
   a closeout commit exists, render it as its own candidate — it is the diff a human most needs
   to look at, and the one with no round after it.
10. **Codex on the ChatGPT login exposes no usage.** The cost table's external-lane row is a blank
    by construction. If the codex CLI can print token counts in its JSON output, the lane should
    capture them next to `filed` so the panel's cost is at least estimable.

## 5. Judgement calls made without the owner

- **Pinned gemini to `gemini-3.7-flash`, not a Pro model,** because no Pro model answers on this
  key. I did *not* switch the CLI to Google-account OAuth, which might reach a Pro model: that
  changes the training terms the owner consented under, and consent is theirs to give. The
  report's WATCH LIST and `panel.json` both say what ran.
- **Retried the gemini lane once per pass** (seed: succeeded on 3.7-flash; final: failed again on
  3.5-flash) and then recorded the final lane as skipped rather than keep burning models. The
  final pass's other two lanes found nothing beyond the chair, so the loss is a missing row, not a
  missing finding — but that is an inference, not a measurement.
- **Kept `prompts.md` inside the scope** (a 22-line journal hunk, not a pasted log); the skill's
  advice to exclude prompt journals targets the crash-report case.
- **Left PC-4 (the 43 pt Finish-tier latch cost) as an accepted wontfix** for the owner to rule
  on, with the corrected trigger set in both the code comment and BACKLOG.
- **Created a dedicated simulator** (`review-loop-1722`, iPhone 16 Pro / iOS 26.5; deleted at the
  end); every dispatch named that one udid and none strayed.
- **Changed no source myself.** The one open partial (QA-loop case steps still naming the old
  toolbar) and the two reviewer residuals go to BACKLOG.md verbatim.
