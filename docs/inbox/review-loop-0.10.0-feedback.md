# Review loop v0.10.0 — token usage and feedback

Run of 2026-09-09 18:49 → 21:50, scope `1a63ce2..836434d` — the qa-loop rounds 1–2 app
commits (22 fixes + their XCUITests + parity pins). Plugin `review-loop-tools@quiller` **0.10.0**.
Fully unattended: the owner was not at the keyboard, so every question took the documented default.

Measured with `tools/loop-usage.py --since 1788993925` against the raw session transcripts, same
accounting as `docs/loop-token-usage.md` (effective = input ×1 + cache_read ×0.1 + cache_write ×2 +
output ×5, deduplicated by `requestId`).

---

## 1. Headline

| | |
|---|---|
| Wall clock | ~3 h (18:49 → 21:50), no pauses |
| Rounds | seed + 2 rounds + closeout (scope mode, `max_rounds` 2, no escalation) |
| Stop condition | **thrashing_soft** at the cap → unattended default: abort + closeout |
| Subagent dispatches | 7 (4 reviewer, 3 implementer), 0 retries, 0 pauses |
| Findings | 12 — 0 blockers, 3 majors, 9 minors; 8 of 12 `introduced_by_fix` |
| Outcome | 9 fixed, 2 partial, 1 open; 0 disputed |
| Suites | node 167 → 171, Swift unit 14 → 17, UI 70 → 75 executions; all green at closeout |
| Mutants | 7 + 3 + 6 across three manifests; 15 killed, 1 expected survivor, 0 errors on re-run |

## 2. Cost

| Dispatch | Requests | Effective tokens | Ledger-reported |
|---|---:|---:|---:|
| Seed review | 64 | 1,249,196 | 200,853 |
| Round 1 implementer | 23 | 270,729 | 75,017 |
| Round 1 review | 62 | 797,434 | 101,862 |
| Round 2 implementer | 36 | 509,063 | 120,169 |
| Round 2 review | 32 | 518,000 | 90,772 |
| Closeout implementer | 30 | 314,632 | 81,614 |
| Closeout review (full suites) | 49 | 818,271 | 86,218 |
| **Subagents** | 296 | **4,477,325** | **756,505** |
| Orchestrator (this session) | 28 | 669,292 | — |
| **Total** | 324 | **5,146,617** | |

Ratio effective/reported for subagents: **5.9×** — between the 4× (code) and 11× (simulator)
figures the skill quotes, which fits: this was a code loop whose reviewers ran xcodebuild on a
simulator. Reviewers cost 2.5× implementers per dispatch; the seed alone was 24% of the run.

## 3. What the loop got right

- **The seed was honest about a clean scope.** 0 majors on 22 commits, after actually running
  parity, unit and five UI classes — not a reviewer inventing severity to look busy. The four seed
  minors were all real (one was a genuine `DateFormatter` locale bug on the backup path).
- **The regression chain was caught inside the loop.** Round 1's unrequested `HudBarHeightKey`
  re-introduced the exact WF-12 bug the scope had just fixed; round 1's reviewer found it, round 2
  latched it, round 2's reviewer found the latch survived a Dynamic Type change, closeout fixed
  that. None of it shipped. That is the loop's whole value proposition and it delivered.
- **`introduced_by_fix` routing into closeout** meant the major found in the last iterated round
  still got fixed and re-verified instead of being dumped in BACKLOG.
- **The mutation manifest as a claim, not a number.** Round 1's reviewer refused to accept "6/7
  killed" from a manifest that could not run and re-ran a repaired copy; the round-2 reviewer then
  ran the repaired file verbatim. Both counts held. Good discipline, worth keeping.
- **`next-round` / `diff` / `open closeout` verbs** kept the orchestrator to 28 requests. The
  bookkeeping is genuinely one call per phase now.
- **The `dispatch_stamp` / SubagentStop hooks** worked silently; I never had to touch `:dispatched`.

## 4. What cost time or nearly went wrong

1. **thrashing_soft at the cap is the wrong signal for a converging series.** Round 2 closed 3 and
   opened 3 (net 0), round 1 net −2 — but every open finding was `introduced_by_fix`, nothing
   reopened, and the worst severity went major → major → (closeout) minor. The skill's own
   "CONVERGING SERIES" exemption should have applied; it evidently requires three rounds of
   non-increasing severity, which a 2-round scoped run can never satisfy. Suggest: in scope mode,
   evaluate the exemption over the rounds that exist, or let the closeout verdict re-label the stop
   as `converged-in-closeout` when closeout leaves 0 majors. The report headline currently says
   "thrashing" about a run that ended green with three minors.
2. **The unattended default is undocumented at the verdict.** The verdict text says "ask: abort,
   or raise max_rounds"; the skill body says "running unattended, take the default". A `--unattended`
   flag on `next-round` (or an env knob the commit_guard already reads) that records the default in
   `rounds.md` would make the report self-explaining. I had to write it into the WATCH LIST by hand.
3. **`merge_ledger.py archive` produced Finder-duplicate names.** Right after archiving,
   `.phase 2`, `briefs 2/` and `ledger 2.json` existed in the archive dir with the plain names
   missing. The repo lives under `~/Documents` (iCloud-synced), so this is macOS renaming on a
   sync conflict during the `mv` — but the plugin's own hygiene check only caught it at *report*
   time, 3 hours later, by which point the archived `ledger.json` had been sitting ignored (the
   allowlist is exact-name). Suggest: run `hygiene_check.sh` inside `archive` immediately after the
   moves, and have `archive` use `os.replace` per file with a post-check rather than a directory
   `mv`. Also worth a line in the skill: "if the host repo is under iCloud/Dropbox, expect ` 2`
   duplicates".
4. **Implementers write manifests that cannot run.** Round 1's manifest had `"replacement": ""`
   (rejected as missing) and a literal `<scratch>` placeholder in `test_cmd`. `mutate.py` should
   accept an empty replacement as "delete the line" (that is the most natural mutant), and the
   implementer agent's prompt should require it to *run* `mutate.py` on its own manifest before
   returning — the round-2 implementer did, unprompted, and its manifest was clean.
5. **The closeout implementer's BACKLOG punt existed only in its CHANGES block.** It is told not
   to touch BACKLOG.md (the orchestrator does), so the sketch lived nowhere on disk until the
   record commit. The closeout reviewer flagged this as "ACTION OUTSTANDING". Suggest the closeout
   brief say explicitly: "write punt sketches to `.review-loop/briefs/closeout-punts.md`; the
   orchestrator copies them into BACKLOG".
6. **Seed cost.** 1.25 M effective for a 3,173-line scope is the single biggest line. 64 requests,
   8.2 M cache-read tokens: the reviewer re-read large files repeatedly. `read_guard` blocks
   whole-file dumps but not the same 200-line window five times. A per-dispatch "files you have
   already read" hint, or a scoped-diff-first instruction with file reads only on demand, would
   likely halve it.
7. **The 10-minute Bash ceiling shapes what agents will verify.** The round-2 implementer split
   the 7-mutant manifest into three scratch copies rather than run it verbatim, and said so
   honestly; the reviewer then had to re-run it whole. The skill already forbids background runs
   for agents; a sanctioned pattern ("run with `timeout 3000 … &`, poll with Monitor") would stop
   agents inventing their own.
8. **`add-usage` vs `next-round --usage` for closeout** is easy to get wrong: closeout shares the
   round number with the last round, so `--usage` (replace semantics) would have silently erased
   round 2's figures. I used `add-usage`; the skill text does not say which to use for closeout.

## 5. Judgement calls made without the owner

- Took the thrashing_soft default (abort + closeout) rather than raising `max_rounds`. The closeout
  fixed the remaining major, so nothing above minor is open; if the owner wants the landscape HUD
  work iterated further, a fresh scoped loop on `f72bf7c..HEAD` is the way.
- Created a dedicated simulator (`review-loop-1849`, deleted at the end) rather than reuse the
  qa-loop driver rig; every dispatch named that one udid and none strayed.
- Fixed the last stale HANDOFF count (npm 167 → 171) in the record commit myself: it is a doc
  count, not source, and CLAUDE.md requires HANDOFF to be right in the same commit.
