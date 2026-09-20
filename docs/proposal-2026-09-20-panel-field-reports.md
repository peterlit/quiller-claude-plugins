# Proposal: review-loop-tools 0.14.0 (+ qa-loop-tools 0.15.0 mirror) — 2026-09-13/19 panel field reports

Written 2026-09-20. Status: **proposed, awaiting approval; nothing built.**

Sources (committed in `docs/inbox/`), with item IDs in the scheme from
`docs/proposal-agent-feedback-process.md` (`<plugin>-<version>-<date>-<host>-<n>`,
numbered in each report's own impact order):

- `loop-tooling-feedback-2026-09-13.md` — agent 1 (weatherapp), review-loop-tools
  **0.13.0**, first three-lane panel run. Converged r2, 1 blocker + 4 majors
  device-verified. 660,723 reported tokens. Items `rl-0.13.0-20260913-weatherapp-1..10`.
- `review-loop-0.13.0-feedback.md` — agent 2 (cardgame), review-loop-tools
  **0.13.0**, first panel run. Converged r1, 6 minors. 2.99M effective measured
  (4.7× reported). Items `rl-0.13.0-20260913-cardgame-1..10`.
- `loop-tooling-feedback-2026-09-19.md` — agent 1 (weatherapp), review-loop-tools
  **0.13.0**, second panel run. Converged r1, 7 minors. 391,849 reported.
  Items `rl-0.13.0-20260919-weatherapp-1..7`.
- `qa-loop-decisions-2026-09-09.md` — agent 1's decision record for the qa
  0.12.0 run already digested in 0.13.0. No new plugin defects; D5 (workers
  ungranted) and D7 (budget raised mid-run) confirm A1 and the budget doctrine.
  Relevant to the feedback-process proposal (it arrived eleven days after the
  run it records).

**Version check:** all three review reports ran 0.13.0, the current release.
`installed_plugins.json` on this machine agrees (0.13.0, updated 2026-09-13).

**Code verification** (all confirmed in the working tree unless marked):

- `dispatch_stamp.sh:17-18,40` writes a single `:dispatched` suffix and exits
  early if one exists; `subagent_guard.sh:16-23` strips it on ANY SubagentStop.
  Two live dispatches → the first return unmarks the second. (three reports)
- `session_guard.sh:17` fires on any prompt matching `review[- ]loop|qa[- ]loop`
  — which, once a loop is running, is most prompts and every task
  notification — and never consults `briefs/.session-ok`. Agent 1's "every
  turn" is the practical effect, not the literal rule.
- `read_guard.sh:57` matches `xcodebuild … test` anywhere in the command text,
  heredoc bodies included.
- `panel_review.py`: `probe()` never calls `load_consent()`; `run()` has no
  lane filter and always rewrites candidates; `run_lane()` returns no timing
  and discards ollama's `prompt_eval_count`/`eval_count`; `jail_env()` drops
  only `CLAUDE_*` so `NODE_OPTIONS` passes through to the Node CLIs; `run()`
  exits 0 whatever the lane statuses; the local lane's probe lists models
  only (no smoke); error `note`s are `stderr.strip()[:200]` with the
  quota/404/module line usually past the cut.
  **Correction to `rl-0.13.0-20260919-weatherapp-1`:** `smoke_lane()`
  (l.265-281) does launch the real CLI with the configured model, so the
  probe checked launch as well as auth; the `NODE_OPTIONS` file vanished
  between probe and run. The scrub is still the right fix.
- `merge_ledger.py panel_tally` (l.593-640): `ledger["panel"][key] = tallies`
  — replaces. `kept` is printed as `confirmed + demoted`, which counts a
  demoted duplicate of a ledgered finding.
- `merge_ledger.py set_scope` (l.203) normalizes via `shlex.split`;
  `write_diff` (l.352-353) takes `args[2]` verbatim as the range and
  `args[3:]` as pathspecs — a single quoted string fails with "bad revision".
  `render_report.numstat` (l.303) shlex-splits the stored scope, so only
  `diff` is inconsistent.
- `merge_ledger.py archive` re-runs the duplicate scan synchronously after the
  moves (l.575-586); iCloud re-stamps asynchronously. `hygiene_check.sh:42`
  does scan `archive/` on disk (only `evidence`/`scratch` are pruned), so
  agent 1's "hygiene should scan archives" is already true — the dupes
  appeared after both checks ran.
- `render_report.py:342` ends the last round's diff candidate at `HEAD`,
  lumping the closeout commit into it. The closeout section (l.246-262)
  lists finding lines only; suite counts live in prose notes.
- `mutate.py`: worktree from `HEAD` (l.104), no baseline run, no dirty-tree
  check, one `test_cmd` for all mutants (l.74, 130).
- `panel-verifier.md`: no `duplicate_of` field; side-observations go "in one
  line of your summary" (l.46-48), i.e. prose the chair never sees.
  `skills/review-loop/SKILL.md:236-254`: the final-pass verifier dispatch
  carries candidates and diff paths, not the open ledger or wontfix list.
- `implementer.md` never mentions BACKLOG.md; the closeout brief (SKILL.md
  l.267-270) forbids it. Two rules, as agent 2 said.
- `skeptical-reviewer.md:108-115` covers re-running the manifest; nothing
  says to write call-site mutants — the behavior both runs praised was
  unprompted.
- Consent key change (`rl-0.13.0-20260913-weatherapp-1`): plausible, not
  reproduced. Commit `907074b` (0.13.0 hardening) changed `consent_path` to
  realpath on both sides; a loop dir reached through any symlinked component
  hashes differently than under 0.12.0. The fix below does not depend on the
  cause.
- Mirrors: `dispatch_stamp`, `read_guard`, `session_guard`, `loop_guard`,
  `commit_guard`, `hygiene_check` are byte-identical in qa; `subagent_guard`
  differs by the panel-namespace comment only (HANDOFF §2.2 caveat).

---

## Part A — review-loop-tools 0.14.0

Ordered by impact. A1–A3 are the items that silently degraded a run (a
one-lane panel nobody was told about; a full rerun to recover two lanes; a
stall guard blocking ordinary turns). Every panel item was filed
independently by both agents.

### A1. The panel gate tells the truth: consent, launch, local smoke, loud failures

`rl-0.13.0-20260913-weatherapp-1,7,10`, `rl-0.13.0-20260919-weatherapp-1`,
`rl-0.13.0-20260913-cardgame-1`. Mechanism, all in `panel_review.py`:

1. **`probe` loads consent** (`load_consent(loop)`, loop dir from the
   panel.json path) and reports per configured lane
   `consent: ok | MISSING (path)`. A remote lane configured without consent
   makes the probe's summary line say so first — the gate can no longer read
   "smoke: ok" while `run` will skip the lane.
2. **`jail_env` scrubs Node and Python injection vars**: drop `NODE_OPTIONS`,
   `NODE_PATH`, `PYTHONPATH`, `PYTHONSTARTUP`, `DYLD_*`/`LD_PRELOAD`. An agent
   CLI must never inherit the orchestrator's terminal wrapper. Selftest
   asserts the codex/gemini env lacks them.
3. **Local lane smoke**: `probe --smoke` runs `run_ollama` with the
   configured model on the one-word prompt (same path as codex/gemini). A
   model that OOMs or clamps context fails at the gate, not in round 0.
4. **Error classification**: `run_lane` maps the failure text to
   `error_kind ∈ {quota, model-unavailable, auth, launch (module/command not
   found), timeout, no-json, other}` from the CLI's stderr/stdout, puts the
   matching line FIRST in `note`, and keeps the 200-char cap after it.
5. **Loud summary, soft semantics**: `run` prints one stderr line per
   non-`ok` lane (`panel_review: lane gemini FAILED (quota): …`) and adds
   `failed: <n>` and `skipped: <n>` to its JSON. Exit code stays 0 — lane
   failures are soft by settled design (CONTROLS "Flood control"); see J2.

### A2. Operational reruns without touching tracked config or reinventing process control

`rl-0.13.0-20260919-weatherapp-2`, `rl-0.13.0-20260913-cardgame-2,3`.

1. `run <loop> <round> [--lanes a,b]` runs only the named lanes.
2. `run` skips a lane whose `.candidates.json` for that round already exists
   (status `cached`, path returned) unless `--force`; a rerun to recover two
   failed lanes can no longer overwrite the good one.
3. `run … --detach` forks, returns immediately with the pid and the summary
   path `fragments/panel/round-<N>.run.json`; `wait <loop> <round>
   [--timeout s]` blocks (bounded under the Bash ceiling) and prints the
   summary when it lands. Lane `timeout_s` above 600 no longer needs
   `nohup … & disown` invented per session. SKILL.md's two `run` calls
   become `run --detach` + `wait`. See J5.

### A3. Live-dispatch counting for the phase marker

`rl-0.13.0-20260913-weatherapp-2`, `rl-0.13.0-20260919-weatherapp-4`
(recurring; agent 1 worked around it with `:waiting:` both runs).
Mechanism: `dispatch_stamp.sh` increments `briefs/.dispatched` (an integer
file, scratch) on every Agent/Task PreToolUse in a loop phase — including
when the suffix is already present — and writes `:dispatched`;
`subagent_guard.sh` decrements and strips the suffix only when the count
reaches 0 (floor at 0; a missing file means 1). Both use a
`python3`+`fcntl.flock` critical section. `loop_guard` is unchanged: the
suffix's meaning is preserved, it just becomes true for the whole time any
dispatch is live. Mirrored to qa (identical hooks). See J1.

### A4. Ledger and verifier contracts for the panel: merge tallies, define "kept", carry duplicates and notes

`rl-0.13.0-20260913-weatherapp-4,8`, `rl-0.13.0-20260919-weatherapp-7`,
`rl-0.13.0-20260913-cardgame-6,7`.

1. `panel-tally` MERGES per lane into `ledger["panel"][key]` (a second batch
   after re-consent adds lanes, never erases the first). `--replace` restores
   the old behavior for a deliberate redo.
2. Verified schema gains two fields: per finding `duplicate_of: "<ledger
   id>"` (optional), and top-level `notes_for_chair: ["…"]` for the
   side-observations the verifier today buries in prose. Tallies gain a
   `duplicate` column. **Kept is defined once**: `confirmed + demoted`
   excluding entries carrying `duplicate_of`. `panel-tally` prints it; the
   report's Panel section renders `kept` and `duplicate` columns.
3. The final-pass verifier dispatch (SKILL.md "Panel final pass" step 2)
   carries the output of `merge_ledger.py open … all` plus the wontfix ids
   (new `open … wontfix` selector), so re-filed findings are marked
   `duplicate_of` instead of re-confirmed.
4. One line for the chair (seed dispatch text + `skeptical-reviewer.md`):
   a verified panel finding that restates one of yours keeps YOUR id; append
   its lanes to that finding's `sources`.

### A5. Lane quality controls from measured kept-rates

`rl-0.13.0-20260913-cardgame-5`, both agents' "drop the qwen3-coder lane"
(0/40 kept across four passes), `rl-0.13.0-20260913-cardgame-1(c)`.

1. **Evidence-path pre-filter in `sanitize`**: a candidate whose every
   `evidence` entry names a path absent from the round's `.stat` file list
   is dropped and counted as `dropped_no_evidence` in the lane's result. The
   lanes saw only the diff; a citation outside it is noise by construction.
   Line-number and identifier checks are declined (C5).
2. **Kept-rate cap on the final pass**: when `ledger["panel"]["0"]` shows a
   lane with `filed ≥ 5` and `kept = 0`, `run … final` caps that lane at 3
   candidates and says so in its result (`cap: 3, reason: "seed kept 0/10"`).
   CONTROLS documents the rule and recommends disabling a lane that is 0/N
   over two runs. See J3.
3. **Model fallback list**: a lane's `model` may be a list; on
   `error_kind ∈ {quota, model-unavailable}` the runner tries the next entry
   and records `model_used`. Gemini tiers stop needing a hand-run smoke loop.

### A6. `session_guard` acknowledges a confirmed session

`rl-0.13.0-20260913-weatherapp-9`. If any guarded loop dir holds
`briefs/.session-ok`, the guard prints nothing. The `.session-ok` file is
the acknowledgment the report asked for; it already exists.

### A7. `read_guard` matches command position, not command text

`rl-0.13.0-20260913-cardgame-4`. Before matching, strip heredoc bodies
(`<<['"]?TAG['"]?` through the terminator line) and single-quoted strings;
anchor the test-run pattern at a command position
(`(^|[;&|(]\s*|\$\(\s*)(xcodebuild|swift\s+test)`). The `cat`/`head`/`sed`
patterns get the same stripped text. Mirrored to qa.

### A8. `mutate.py`: baseline run, dirty-tree refusal, per-mutant `test_cmd`; prompts codify the two disciplines that worked

`rl-0.13.0-20260913-weatherapp-6`, `rl-0.13.0-20260919-weatherapp-5`, agent
2's "control mutant" praise, both agents' "call-site mutants" praise.

1. **Baseline**: before any mutant, run each distinct `test_cmd` unmutated
   in the worktree; non-zero exit → `die("baseline red or matches nothing;
   the kill count would be meaningless")`. This catches the `-quiet` filter
   that matched nothing (grep exits 1 → pipefail → red baseline).
2. **Dirty-tree refusal**: if `git status --porcelain -- <manifest files>`
   is non-empty, refuse with "commit first: the worktree is cut from HEAD
   and would test the OLD code" unless `--allow-dirty`. This catches the
   pre-commit "every mutant survived" run. See J4.
3. **Per-mutant `test_cmd`** (`m.get("test_cmd", manifest["test_cmd"])`), so
   UI-only mutants pay the UI gate and unit mutants do not (agent 1: ~25 →
   ~8 min on a five-mutant manifest). Baseline runs once per distinct
   command.
4. `implementer.md`: "commit before you run `mutate.py`" and "include one
   CONTROL mutant (`expect: killed` on a line the tests certainly cover) —
   it proves the test_cmd can fail". `skeptical-reviewer.md`: "an
   implementer manifest that mutates only the bodies it wrote is not
   evidence the view calls them — write one or two CALL-SITE mutants of your
   own (measured: 2026-09-13 and 2026-09-19, both survived, both became
   findings)".

### A9. Archive integrity on synced volumes: re-verify after the provider settles; hygiene before the final commit

`rl-0.13.0-20260919-weatherapp-3`. `archive` repeats its duplicate scan
after a 3-second settle (a second pass, same diff-against-pre-dups logic,
reported as `duplicates_detected_late`). SKILL.md's report stage says: run
`hygiene_check.sh` immediately before the final commit, after the report
render, not only after it — and CONTROLS gains a line: on iCloud/Dropbox
volumes duplicates can appear seconds after a move; if they recur, keep the
repo outside the synced tree. No stronger guarantee is possible from
inside the script (C3).

### A10. One range parser for `scope` and `diff`

`rl-0.13.0-20260913-weatherapp-5`. A shared `split_range(args)` (shlex
over the joined args) feeds both verbs; `diff` accepts the single-string
form `scope` already accepts. SKILL.md's "UNQUOTED" note becomes "either
form; `diff` and `scope` take the same string".

### A11. Report: the closeout diff is its own watch candidate; suite counts are structured

`rl-0.13.0-20260913-cardgame-9`, `rl-0.13.0-20260919-weatherapp` environment
note. `merge_ledger.py open <ledger> closeout` records
`ledger["closeout_start_sha"] = HEAD`; `render_report` ends the last round's
candidate there and adds `closeout diff <sha>..HEAD` as a candidate. The
closeout reviewer's fragment may carry an optional top-level `suites:
{"<target>": {"executed": n, "failed": n, "skipped": n}}`; the Closeout
section renders it as a table when present, so "green" cannot hide 8 of 13
skipped.

### A12. Lane telemetry

`rl-0.13.0-20260913-weatherapp-3`, `rl-0.13.0-20260913-cardgame-10`.
`run_lane` records `elapsed_s` for every lane, ollama's `prompt_eval_count`
and `eval_count`, and whatever token fields the codex/gemini CLIs emit in
their JSON output when a documented flag exposes them (captured as
`tokens: {…}` or absent — never estimated). Feeds the feedback bundle's
run summary.

### A13. Skill and prompt lines

- One BACKLOG rule (`rl-0.13.0-20260913-cardgame-8`): implementers never
  touch BACKLOG.md; round sketches go to `briefs/round-<N>-punts.md`,
  closeout sketches to `briefs/closeout-punts.md`; the orchestrator copies
  at record time. Added to `implementer.md` and the round-dispatch text.
- Usage once per dispatch (`rl-0.13.0-20260919-weatherapp-6`): "record a
  dispatch's tokens from its FIRST completion notification; a repeated
  notification for the same dispatch is not a second cost".
- Reviewer verification without simulator tools
  (`rl-0.13.0-20260919-weatherapp` environment note): "if no simulator
  control tool is loaded, a scoped XCUITest is an acceptable — often
  better — device verification, and doubles as the regression test".

## Part B — qa-loop-tools 0.15.0 (mirror release, no qa-specific behavior)

A3, A6, A7 (hook scripts, byte-identical), A9 and A10 (`merge_ledger.py`
common regions), A11's `closeout_start_sha` only if the qa verb set gains
closeout (it does not; skip). `subagent_guard.sh` keeps its panel-namespace
comment divergence. Diff between the copies must still show panel-only
code (HANDOFF §2.2).

## Part C — declined or deferred, with reasons

- **C1. Non-zero exit from `run` when a lane fails** (agent 1 09-19 #1c).
  Declined: "lane failures are soft, never blocking a round" is settled
  (CONTROLS). A1.5's stderr banner and `failed` count make it loud without
  turning the orchestrator's `&&` chains into panel-dependent aborts.
- **C2. A deliberately-broken sentinel in `mutate.py`** (agent 1 09-13 #6).
  Declined: no language-agnostic way to break a build; the baseline run
  (A8.1) plus the control mutant (A8.4) cover the same failure.
- **C3. Gemini tier detection by calling Google's models endpoint from the
  script** (agent 2 #1a-b). Declined: a new egress path from
  `panel_review.py` itself, outside the CLI the consent names. A1.4's
  quota classification plus A5.3's fallback list give the same practical
  outcome (the run says "quota" first and moves on).
- **C4. Dropping the ollama lane from the shipped defaults.** Not ours:
  `panel.json` is host config; the plugin ships no default lanes. CONTROLS
  gets the 0/40 measurement and the A5.2 rule instead.
- **C5. Claim-identifier pre-filter for candidates** (agent 2 #5). Declined
  as fuzzy: "contains at least one identifier from the claim" false-negatives
  on prose claims. The path filter (A5.1) is exact and catches the observed
  failure (citations at unrelated files).
- **C6. Keying the dispatch marker by agent name** (agent 1's alternative).
  Declined in favor of a counter (A3): SubagentStop payloads do not
  reliably name the agent type, and the `.phase` grammar stays a suffix.
- **C7. Archive-time guarantee against provider re-stamping.** Deferred:
  the settle re-check (A9) is best-effort by nature. If duplicates recur
  after 0.14.0, the next step is a `.nosync`-suffixed scratch area for
  `evidence/`, `fragments/` and `briefs/` — design-sized, BACKLOG.
- **C8. Recording panel lane cost as tokens when the CLI exposes none.**
  Declined: never estimate. `elapsed_s` is always recorded; tokens only
  when the CLI reports them (A12).

## Part D — judgment calls flagged for Peter

- **J1. Dispatch tracking: counter file vs. keyed suffix.** A3 proposes an
  integer in `briefs/.dispatched` behind the existing `:dispatched` suffix.
  Alternative: `:dispatched:<n>` inside `.phase` itself (no second file,
  but every hook and the skill's grammar change). Recommend the counter.
- **J2. Lane failure signaling: soft with a loud banner, or non-zero exit
  when EVERY configured lane fails.** Recommend soft (C1); the all-failed
  case is rare and the banner plus `failed: n` is unambiguous.
- **J3. Kept-rate cap on the final pass: automatic or advisory.**
  Automatic (A5.2) changes a lane's behavior from measured data without a
  human; advisory (CONTROLS text only) leaves the ~140K-token verifier cost
  of a 0/10 lane to be paid until someone edits panel.json. Recommend
  automatic, disclosed in the run JSON.
- **J4. Dirty-tree handling in `mutate.py`: hard refuse or warn.** Refusing
  forces the commit-then-mutate order the field learned the hard way; a
  warning lets "every mutant survived" through with a line nobody reads.
  Recommend refuse with `--allow-dirty`.
- **J5. `--detach`/`wait` verbs vs. documenting `nohup`.** Verbs cost ~40
  lines and a selftest; documentation costs a paragraph and leaves process
  management to each orchestrator. Recommend the verbs.

## Part E — build order and validation

1. **review-loop-tools 0.14.0**: A1–A13 in that order; `panel_selftest.py`
   gains checks for env scrub, consent-in-probe, `--lanes`, cached
   candidates, error classification, tally merge, kept definition, evidence
   pre-filter, fallback list, `--detach`/`wait`. Scratch smoke tests per
   ritual §5: two concurrent fake dispatches against the counter hooks; a
   heredoc containing `xcodebuild test` through `read_guard`; a manifest
   with a red baseline and one with a dirty file; an archive on a directory
   where a background job plants `ledger 2.json` two seconds after the move.
2. **qa-loop-tools 0.15.0**: mirror A3, A6, A7, A9, A10 (Part B), `diff -q`
   per ritual.
3. CONTROLS.md root copy: panel section (consent in probe, `--lanes`,
   `--detach`/`wait`, error kinds, kept definition, cap rule, fallback
   list, iCloud settle note, `--allow-dirty`), synced to both plugins.
4. HANDOFF: state line, §2.2 mirror list unchanged, §5 watch items replaced
   by: counter hooks under overlapping dispatches; a quota lane failing over
   to its fallback model; the cap firing on a 0/N lane; late-appearing
   iCloud duplicates caught by the settle pass; `suites` rendering in a
   closeout.
5. Standard sweep: `json.tool`, `ast.parse`, `bash -n`, no `/Users/` paths.
