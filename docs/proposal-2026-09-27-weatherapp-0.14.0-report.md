# Proposal: review-loop-tools 0.16.0 (+ qa-loop-tools 0.17.0 mirror) — the 2026-09-20 weatherapp report

Written 2026-09-27. Status: **BUILT 2026-09-27** as review-loop-tools 0.16.0 /
qa-loop-tools 0.17.0 (Peter: "go", after answering J3). arch-docs-tools
went to 0.3.1 for a shared-script sync only. The text below is the proposal
as approved; "As built" at the end lists where the build departs from it.

## Source

- `docs/inbox/weatherapp/review-loop-tools-0.14.0-2026-09-20.md` — agent 1
  (weatherapp), review-loop-tools **0.14.0**, a scoped run with a two-lane
  panel (codex, gemini), resumed from a pause. Seed + 2 rounds + panel final
  pass + closeout; stopped `diminishing`; 14 findings (1 major left
  `partial`, 13 minors); tree green at closeout. 2,447,428 effective
  subagent tokens (4.08× the 599,948 reported). Written 2026-09-26 from the
  hand-pasted prompt, before the feedback command existed.
  Items `rl-0.14.0-20260920-weatherapp-0..5` (the report numbers from 0),
  all `new` in `docs/inbox/dispositions.json`. Its friction items and
  wishes carry no ids; Part B takes them.

**Version check.** The report states installed and running 0.14.0 with no
mismatch, and names the install path and commit (`949110b`). The run's
transcript confirms it: every script call uses
`~/.claude/plugins/cache/quiller/review-loop-tools/0.14.0/scripts`. 0.14.0
was the current release on the day of the run. 0.15.0 (the feedback
process) changed none of the code these six items concern, so each was
checked against the 0.15.0 tree.

## What I verified, and how

| Item | Verdict | How |
|---|---|---|
| -0 archive conclusions renamed to ` 2` | **Happened; the report's diagnosis is wrong, and so is its cause.** `hygiene_check.sh` DOES scan `archive/`, and the rename was a one-off machine event, not routine re-stamping. | Reproduced: three committed conclusions renamed inside an archive → hygiene prints three "duplicate name … MISSING" lines with the `mv` advice. Cause: see "The iCloud toggle" below. |
| -1 counter read 0 with an agent live | **Confirmed, root cause found.** | Reproduced to the exact reported state with the real hooks; the transcript confirms the precondition. |
| -2 trend tokens miss late usage | **Confirmed, and it is worse than reported.** | Reproduced. The BUDGET stop reads the same stale figure. |
| -3 implementers ran the 0.13.0 `mutate.py` | **Confirmed.** | `implementer.md` names `mutate.py` twice with no path; the skill passes the path to the reviewer only; the cache holds 0.10.0, 0.12.0, 0.13.0 and 0.14.0. |
| -4 manifests exceed the Bash ceiling | **Confirmed.** | The run's manifests hold 6, 7 and 4 mutants at ~2 min each; `mutate.py` has no subset or detach mode. |
| -5 no closeout `suites` table | **Confirmed — only half of 0.14.0's A11 shipped.** | `suites` appears in `render_report.py` (the reader) and nowhere in `skeptical-reviewer.md` or the skill. Nothing ever asks a reviewer to write it. |

Details of the three reproductions:

**-1.** The transcript shows, at 00:09:54, the orchestrator writing
`round-2-review:waiting:…` for the detached panel final lanes, and three
seconds later ONE request carrying both `printf 'round-2-implementing' >
.review-loop/.phase` and the closeout-implementer dispatch. Run against the
real hooks in that order:

| Step | `.phase` | `briefs/.dispatched` |
|---|---|---|
| panel lanes detached | `round-2-review:waiting:panel-final` | 0 |
| hook for the implementer dispatch | unchanged | **0** — `dispatch_stamp.sh` exits at `*:waiting:*` without counting |
| the same-batch Bash write lands | `round-2-implementing` | 0 |
| panel-verifier dispatched | `round-2-implementing:dispatched` | 1 |
| verifier returns, implementer still live | `round-2-implementing` | 0 |

That is the report's state exactly, and the Stop hook then blocks the turn
(exit 2) while an agent is running. The other ordering (hook first on a
bare phase, then the write) leaves the counter at 1, which the report did
not see — so the cause is the uncounted dispatch during `:waiting:`, not
hook ordering. It matters that the skill PRESCRIBES this situation: the
panel final pass runs under `…:waiting:panel-final` and "the closeout
implementer may run alongside — the dispatch counter keeps the marker
honest". In 0.14.0 and 0.15.0 it does not.

**-2.** `next-round … --usage implementer=100` followed by
`set-usage … reviewer 200`, with `token_budget: 250`:

| Where | Tokens |
|---|---|
| `rounds.md` round-1 row | 100 |
| `verdict.json` `tokens` / `cumulative_tokens` | 100 / 100 |
| `ledger.json` usage, and the report header | 300 |
| Decision | `continue` — with 300 spent against a budget of 250 |

The budget stop lags by whatever is recorded after `next-round`. On the
reported run that was every reviewer figure.

**The iCloud toggle (-0).** Peter turned iCloud Drive off by accident on
2026-09-25 (the `~/iCloud Drive (Archive)` folder is stamped 22:52) and
back on afterwards. A scan of `~/Documents/src` (five levels, build
directories pruned) finds 40 Finder-duplicate names, and every one has an
inode change time of 2026-09-25 or 2026-09-26 — none older. They sit in
repos the loops never touched (`railsone`, `commute-bites`,
`spend_analysis`, `youtube_transcripts`) as well as in the two field
repos. The re-sync after the toggle renamed them; the weatherapp archive
was one of many casualties, found on the 26th because a commit happened to
touch that tree. This is a different thing from the renames in the
2026-09-09 and 2026-09-19 reports, which appeared seconds to minutes after
`archive` moved files and are what the settle pass addresses.

Still standing from the same event, as of this writing: cardgame's
`.review-loop/archive/20260920-123339-fa2de2e/` holds `ledger 2.json`,
`REPORT 2.md`, `rounds 2.md`, `verdict 2.json` and `.phase 2` with every
plain name missing. `hygiene_check.sh` reports all five.

**Not reproduced here:** the report's cause for -2 — the agent's hand-back
arriving one turn before the task notification that carries its token
count. In this session the two arrived together for a background agent. I
treat the ordering as harness-dependent and fix the scripts so either
order gives one number.

## What the report confirms as fixed

Worth recording before the defects: nine 0.14.0 changes were exercised
and held. The EXCLUDED stat trailer (0 of 13 candidates mentioned the
hidden file), `duplicate_of` and `notes_for_chair` (both used; the chair
appended a source instead of minting a second id), one definition of
"kept", `commit_guard` standing down at `done`, the closeout diff as its
own watch candidate, `run --detach` + `wait`, per-mutant `test_cmd`, the
single BACKLOG rule, and codex token counts. Not exercised: per-lane rerun,
the empty-diff refusal, model failover, the precision cap.

---

## Part A — review-loop-tools 0.16.0

Ordered by impact on run integrity.

### A1. The dispatch counter is the source of truth; the suffix is its display

`rl-0.14.0-20260920-weatherapp-1`. Fourth report of a marker stripped while
an agent is live (`rl-0.13.0-20260913-weatherapp-2`,
`rl-0.13.0-20260919-weatherapp-4`, `rl-0.13.0-20260920-cardgame-4`); 0.14.0's
counter fixed overlapping dispatches but left two holes. Mechanism:

1. `dispatch_stamp.sh` counts EVERY dispatch made while a loop phase is
   live, including under `:waiting:`. It still never rewrites a `:waiting:`
   marker.
2. `subagent_guard.sh` decrements whenever the counter is above zero and a
   loop phase is live — today it decrements only when the phase ends
   `:dispatched`, so a suffix erased by a phase write also strands the
   count.
3. `loop_guard.sh` allows a stop when the counter is above zero, whatever
   the suffix says. A phase write can then erase the suffix without erasing
   the fact that an agent is running.
4. `next-round` resets the counter to 0 after recording
   `dispatch-count-mismatch` (it records it since 0.15.0 and then leaves
   the stale value in place).
5. Skill text, one sentence in the hard rules: write the phase in its own
   call BEFORE the dispatch; never in the same batch as an Agent call.
6. `hooks_selftest.py` gains both sequences from the table above.

### A2. Late usage reaches the trend table, the verdict, and the budget

`rl-0.14.0-20260920-weatherapp-2`. `set-usage` and `add-usage` become the
single place a round's token figure is settled:

1. After updating the ledger, they rewrite that round's Tokens cell in
   `rounds.md` (located by column name — the qa table has two more columns)
   and, when `verdict.json` is for that round, its `tokens` and
   `cumulative_tokens`.
2. Their output gains `over_budget: true|false`. When a late figure crosses
   `token_budget` the orchestrator is told at that moment and takes the
   BUDGET path (stop, closeout, report) — it does not wait a round.
3. Skill text: "a dispatch's hand-back can arrive before the notification
   carrying its token count. Close the round on the hand-back; record the
   figure with `set-usage` when the notification arrives."

The stop DECISION already written for a round is not rewritten (C4).

### A3. Every agent runs this release's scripts

`rl-0.14.0-20260920-weatherapp-3`. No wrong verdict resulted, but only
because the reviewer re-ran on 0.14.0; the 0.13.0 copy has no baseline run
and ignores per-mutant `test_cmd`, so a round-2 "7/7 killed" from it was
never evidence.

1. `next-round` and `open` add a `tools` block to the brief they write:
   `{"mutate": "<absolute path to this release's mutate.py>"}`. The path
   reaches the implementer in the file it already reads, with no reliance
   on the orchestrator remembering a line.
2. Skill text names `${CLAUDE_PLUGIN_ROOT}/scripts/mutate.py` in the round
   implementer dispatch and the closeout implementer dispatch, as it
   already does for the reviewer.
3. `implementer.md` and `skeptical-reviewer.md`: "run the `mutate.py` named
   in your brief or dispatch. Never search for it — older copies sit in the
   plugin cache."
4. `mutate.py` refuses to run when a HIGHER version of the plugin sits in a
   sibling directory of its own (`…/review-loop-tools/<version>/`), naming
   the newer path; `--allow-stale` overrides. This protects every release
   from this one on. The 0.13.0 and 0.14.0 copies already in caches cannot
   be changed — items 1 to 3 are what keep agents off them.
5. qa mirror: `ux-tester.md` names `nfr_analyze.py` without a path in the
   same way. The qa skill already passes the path in every dispatch; the
   agent text gets the same "never search" sentence.

### A4. Closeout suite counts: ship the writer

`rl-0.14.0-20260920-weatherapp-5`. 0.14.0 shipped the table's renderer and
never asked anyone for the data. The reported run's counts (unit 297 / 0,
UI 29 executed / 14 skipped / 0 failed) reached BACKLOG by hand — and 14 of
29 skipped is precisely what the table exists to show.

1. `skeptical-reviewer.md` (closeout mode) and the skill's closeout step 3
   name the field: top-level `"suites": {"<target>": {"executed": n,
   "failed": n, "skipped": n}}` in the closeout fragment, one entry per
   suite run.
2. The skill names the closeout reviewer's phase (`round-<N>-review`). It
   is unstated today, and `subagent_guard.sh` validates fragments only
   while the phase says review or testing.
3. `subagent_guard.sh` validates a `round-*-closeout.json` fragment: it
   must carry `suites`, an object of integer triples. An empty object is
   accepted only beside a `suites_note` string ("no test targets"). A
   reviewer that omits it is told so before it can finish, as with any
   malformed fragment.
4. `render_report.py`: when a closeout ran and no fragment carries
   `suites`, the Closeout section says so in one line instead of showing
   nothing.

### A5. `mutate.py`: subsets and long runs

`rl-0.14.0-20260920-weatherapp-4`. Five mutation runs in one loop were each
split by hand into scratch copies of the manifest.

1. `--only id1,id2` runs a subset of the NAMED manifest. No copy is made;
   the manifest stays the artifact of record. An id not in the manifest is
   an error before anything runs.
2. `--detach` and `mutate.py wait <manifest>`, mirroring `panel_review.py`:
   results are written to `<manifest>.results.json` as each mutant
   finishes; `wait` blocks up to 540 s and exits 3 while the run is still
   going. The agent stays in its turn, so the "never background the run"
   rule in `implementer.md` is reworded, not dropped: detach + wait is the
   sanctioned form; an unattended background task is still forbidden.
3. Each result carries `elapsed_s`; the summary carries the total.
4. `implementer.md`'s paragraph permitting scratch splits is replaced by
   these two.

### A6. Renamed conclusions: detect sooner, fix by verb

`rl-0.14.0-20260920-weatherapp-0`. The plugin cannot stop a file provider
renaming files. It can notice sooner and make the repair one command.

1. `hygiene_check.sh` gains a fourth check: tracked files missing from
   disk (`git ls-files --deleted -- <loop-dir>`). It catches a conclusion
   that vanished under ANY name — a Dropbox "conflicted copy" does not
   match the ` 2` pattern — and names the likely twin when one exists.
2. `hygiene_check.sh --restore`: for each duplicate whose plain name is
   missing and which is the only candidate, `mv` it back. It never
   deletes, never overwrites, and prints each move. This is what both
   agents have done by hand in three separate runs.
3. CONTROLS gains two sentences: the settle pass covers renames that
   follow a move by seconds; after a sync outage, a toggle, or a restore,
   run `hygiene_check.sh <loop-dir> --restore` once per repo.

A `SessionStart` hook that runs the scan in every session was in the first
draft of this item. It is dropped (C6): its case rested on a rename that
"sat for six days", and that rename is now explained by a single event.

---

## Part B — the report's unnumbered friction items and wishes

| Item | Proposed |
|---|---|
| Hand-back arrives before the token count | Covered by A2.3. |
| The closeout watch candidate is pre-filled AND carries the fill marker | Build. `render_report.py:391`: move "the commit with no round after it" into the candidate's label so its slot has the same shape as every other. |
| Nothing covers resuming a paused loop | Build, skill text only. Setup step 1 gains a third state beside FINISHED and ABANDONED: PAUSED — `.phase` ends `:waiting:<reason>` or reads `awaiting-human`. Resume from the phase; do not archive. The plugin creates this state itself: the session-size gate tells the orchestrator to restart in a fresh session and says nothing about how to continue. |
| The Panel section needs a definition of Kept | Build. One sentence in the section's intro: kept = confirmed + demoted. |
| `rounds.md` carries no timestamps | Decline (C2). |
| Prune stale plugin versions | Decline (C1). |
| Host `.gitignore` rule `REVIEW-*` swallowed the report's filename | No plugin change. Verified: on a case-insensitive checkout the rule ignores `docs/reports/review-loop-tools-….md`, and does NOT ignore `.review-loop/feedback/review-loop-tools-….md` — the loop-dir allowlist's negation wins. Reports filed by the 0.15.0 command are unaffected. |
| Task-notification `output-file` paths named the previous session | Harness artifact. No action. |

## Part C — declined or deferred, with reasons

- **C1. Pruning the plugin cache.** The cache is the harness's: sessions in
  flight pin a version (the `.in_use` markers in a version directory),
  and a plugin deleting its siblings could remove code a running session
  depends on. A3 keeps agents off stale copies without touching them.
- **C2. Timestamps in `rounds.md`.** The need was a usage window. Since
  0.15.0 the run summary carries one (ledger creation and the first
  recorded dispatch, to the report) and `dispatches.jsonl` times every
  dispatch. A new column would change a committed table that
  `run_summary.py` and the ingest parse.
- **C3. Re-stamping the suffix on PostToolUse** (the report's mechanism for
  -1). PostToolUse on the Agent tool fires when the agent has RETURNED, not
  after the batch's other calls; re-stamping `:dispatched` then would mark
  a finished agent as live. A1 removes the dependence on the suffix
  instead.
- **C4. Rewriting a round's stop decision when late usage crosses the
  budget.** `set-usage` reports `over_budget`; it does not edit the verdict
  or `rounds.md`'s Decision cell. A decision the metrics script made stays
  the metrics script's; the orchestrator acts on the flag.
- **C5. A guarantee that archived conclusions stay put.** Still not ours to
  give. A6 detects and repairs; the `.nosync` scratch isolation in BACKLOG
  would not help here in any case — the files renamed were conclusions,
  which must stay at known names inside git.
- **C6. A `SessionStart` hook running the duplicate scan.** A hook in every
  session of every repo with the plugin installed, to catch an event that
  has happened once and that Setup's hygiene preflight catches at the next
  loop anyway. If days-later renames are reported again WITHOUT a machine
  event behind them, this comes back with that evidence.

## Part D — judgment calls

- **J1. A stale counter fails open.** With A1, a crashed agent that never
  fires SubagentStop leaves the counter above zero and the Stop hook allows
  every stop until `next-round` resets it. That is today's behavior with a
  stuck suffix, so nothing regresses, and the alternative (expire a count
  after N minutes) would block legitimate 20-minute closeout reviews. I
  recommend fail-open with the reset at round close.
- **J2. `suites` enforced by the guard, or requested only.** A4.3 blocks a
  closeout reviewer from finishing without it. Text alone is cheaper and
  can be ignored, which is how the field ended up empty. I recommend the
  guard.
- **J3. The iCloud question — RESOLVED 2026-09-27.** Peter: iCloud Drive
  was turned off by accident on the evening of 2026-09-25 and turned back
  on. The scan above ties the rename to that event. Consequences: the
  field repos are still on a synced volume, so the move-time renames of
  the earlier reports remain possible and A6.1 and A6.2 are worth
  building; the SessionStart hook is dropped (C6); and the report's
  "the window is at least days, so the settle re-check bounds nothing" is
  not supported — the settle pass was never meant for this.
- **J4. `mutate.py` refusing on a newer sibling: refuse, or warn.** A
  warning is what the closeout implementer effectively had (it noticed by
  itself, after a wasted run). I recommend refusing, with `--allow-stale`.
- **J5. Both `--only` and `--detach`/`wait`, or one.** `--only` is ten
  lines and ends the scratch copies; detach + wait is about forty and ends
  the splitting altogether. I recommend both: a reviewer re-running two
  disputed mutants wants `--only` even when the whole manifest would fit.
- **J6. The `tools` block puts an absolute path in a brief.** Briefs are
  scratch (ignored by the allowlist, never committed), so the no-absolute-
  paths rule for shipped files is not broken. Flagged because it is the
  first time a script writes one.

## Part E — build order and validation

1. **A1**, then `hooks_selftest.py` with both reproduction sequences,
   before anything else touches the hooks. Apply identically to the qa
   copies (`dispatch_stamp.sh`, `subagent_guard.sh`, `loop_guard.sh` are
   byte-identical shared scripts).
2. **A2** in `merge_ledger.py` (both copies, common region), tested against
   the review table and the qa table, and against the -2 reproduction:
   after the late `set-usage`, all four places read 300 and the output says
   `over_budget: true`.
3. **A4**: guard, renderer, prompt and skill text together. Smoke test: a
   closeout fragment without `suites` blocks; with it, the table renders;
   an empty object with a note passes.
4. **A3** and **A5** in `mutate.py`, then the brief's `tools` block. Smoke
   tests in a scratch repo with a fake version tree: the refusal, the
   override, `--only` with a bad id, a detached run read back by `wait`,
   and a wait that exits 3.
5. **A6** (two script changes and the CONTROLS sentences), then **Part
   B**'s three small builds. Smoke test A6 against the -0 reproduction and
   against a Dropbox-style "conflicted copy" name: the deleted-tracked
   check reports both; `--restore` moves back only the unambiguous one.
6. Mirror release `qa-loop-tools 0.17.0`: the shared hooks, `merge_ledger.py`,
   `render_report.py`, `hygiene_check.sh`, the `ux-tester.md` sentence. No
   qa-specific behavior.
7. Same commit: CONTROLS (synced), both READMEs, HANDOFF's state line,
   each plugin's FIELD-QUESTIONS — new watch items for the counter under
   `:waiting:`, the suites table actually appearing, `mutate.py` refusals
   and `--only`/detach use, late-usage `over_budget` — then
   `docs/inbox/dispositions.json` and `tools/render_field_questions.py`.
8. Standard sweep and all three selftests (`feedback_selftest.py` twice).

Expected dispositions if approved as written: -0 shipped in part (detection
by a second route and a repair verb; no guarantee — C5; the reported cause
was a machine event), -1 to -5 shipped.

---

## As built — 2026-09-27

Parts A and B were built in full, on the recommended side of every
judgment call. Where the build departs from the text above:

| Proposal | As built | Why |
|---|---|---|
| A1.4: `next-round` resets the counter | `set-round` resets it too (one helper, `settle_dispatch_counter`) | The qa skill never calls `next-round`; without this the qa loop had no reset point and a stale count would fail open until archive. |
| A1.1: count every dispatch | The bare-phase branch ADDS to the count; it used to write `1` | A reset to 1 would discard an agent counted under `:waiting:` — the reported sequence exactly. |
| A4.2: closeout reviewer phase `round-<N>-review` | `round-<N>-closeout-review` | The guard must require `suites` only during the closeout review. With one phase name for both, a closeout fragment left by an earlier pass would block every later reviewer. |
| A3.4: refuse on a newer sibling | Also records anomaly `mutate-stale-refused`; the check runs before `--detach` | So the refusal reaches the run summary, and a detached run never starts from a stale copy. |
| A5.2: results written as each mutant finishes | Only for detached runs; a foreground run writes no file | A foreground run's contract is stdout. A refusal or crash in a detached run still ENDS the results file, so `wait` never spins on a run that is over. |
| A6.1: names the likely twin | The missing-tracked check skips files whose ` N` twin the duplicate check already reported | One line per problem. |
| — | `arch-docs-tools 0.3.1` | `field_log.py` and `run_summary.py` are mirrored into it byte-identical (ritual 2) and both changed: a new anomaly code, two new hygiene kinds. No arch-docs behavior changed. |
| — | `feedback_selftest.py` no longer requires the allowlist stamp to equal the plugin version | The template did not change in this release; the stamp names the release that last changed it (HANDOFF ritual 1 foresaw this). |

Validation as executed:

- `hooks_selftest.py` 19 → 51 checks. It replays the reported -1 sequence
  in both orders, the round-boundary reset, late usage against the review
  table and the qa table (Tokens located by column name), the `suites`
  guard in six cases, and hygiene detection and `--restore` on renamed
  archive conclusions including a "conflicted copy" name.
- `mutate_selftest.py`, new, 19 checks: `--only`, `--detach` + `wait`
  (finished, still running, mismatch, refusal, no run, stale results
  file), and the stale-copy refusal against a fake version tree.
- `feedback_selftest.py` 94, against both loop plugins; `panel_selftest.py`
  137.
- The three reproductions from "What I verified" were re-run against the
  new code: the counter reads 1, 2, 1, 0 through the reported sequence and
  the Stop hook allows the wait; after the late `set-usage` all four places
  read 300 and the output says `over_budget: true`; hygiene reports the
  renamed conclusions and `--restore` moves them back.

Not verified, because it cannot be from here: the order in which the
harness runs the dispatch hook and a same-batch Bash call. The fix does
not depend on it — both orders are tested — but the report's hand-back-
before-notification ordering (A2) and the hook ordering (A1) remain
observations from one field run each.
