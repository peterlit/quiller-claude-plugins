# Loop Controls

Every knob across **review-loop-tools** and **qa-loop-tools**, organized by
where it lives — and what to actually do with it. Tags: `[qa]` `[review]`
`[both]`.

## Starting a loop

*Surface: the Claude Code prompt.*

- **`/qa-loop-tools:qa-loop`** `[qa]` — kicks off the UX/QA loop on the
  current repo. Say a round count in the same message to override the
  default 5.
  *In practice:* "run the qa loop, max 3 rounds, use 2 testers" sets all
  three knobs in one line — the skill reads them into ledger.json.
- **`/review-loop-tools:review-loop`** `[review]` — starts the adversarial
  code-review loop. Three seed modes: name a **scope** (a sha range, diff
  file, or PR) to review just that change; a `REVIEW.md` at the repo root
  becomes the seed findings; otherwise a cold full review of HEAD.
  *In practice:* "review-loop the changes in main..feature-x" scopes the
  whole loop to one change; paste a human review into `REVIEW.md` to make
  the loop grind through *your* list.
- **`/model`** `[both]` — your main-session model *is* the implementer's
  model (and the orchestrator's): both implementers use `model: inherit`.
  *In practice:* strongest model for real hardening; a Sonnet session for a
  cheap pass. Never run the session on a model an agent is pinned to (see
  Model pins).

## Before you start

- **A fresh session** `[both]` — the single largest measured lever: the same
  plumbing request costs ~3.3× more in a large-context session (8.5M vs
  2.6M tokens over 22 rounds). A `UserPromptSubmit` hook reports the
  transcript size whenever a loop is invoked and warns above 2 MB.
  *In practice:* start loops in a new session. If you run one inside a long
  session anyway, say so at the gate — the loop will ask.

## Loop configuration

*Surface: `.qa-loop/ledger.json`, created on first run.*

- **`max_rounds`** `[both]` (default 5; **2 in review scope mode**, auto-
  escalating to 5 if a blocker appears) — the hard iteration backstop.
  Measured: every scoped review converged by round 2–3, and DIMINISHING
  cannot fire before round 3, so a higher cap never saved anything.
  *In practice:* leave the defaults; raise it only for cold full reviews of
  large trees.
- **`token_budget`** `[both]` (default null) — a hard ceiling on cumulative
  subagent tokens. The orchestrator records each dispatch's cost
  (`set-usage`) from the task results; `rounds.md` gains a Tokens column,
  and the BUDGET stop fires (closeout + report) when the sum crosses the
  ceiling.
  Scale caveat: the harness-reported figure is WORKLOAD-DEPENDENT below
  billed effective cost — measured ~4× for code loops and ~11× for
  simulator loops (mid-range confirmations: 5.9× on a code loop whose
  reviewers ran xcodebuild, 6.9× on a full simulator loop; the ratio grows
  with turns per dispatch). Budget on the reported scale for your loop
  type — the stop is a guardrail on runaway loops, NOT protection for a
  real dollar spend. `set-usage` REPLACES a (round, role)
  figure — corrections never inflate the feed; `add-usage` accumulates.
  CLOSEOUT shares the last round's number: record its usage with
  `add-usage`, never `set-usage`/`next-round --usage` (replace semantics
  would erase that round's figures).
  *In practice:* the qa gate now recommends a value (estimate × rounds
  +50%); accept it unless you have a reason not to.
- **`HARNESS_NOTES.md` policy** `[qa]` — byte ceiling, enforced: default
  10KB, raise with `QA_NOTES_CEILING_KB` env for driver-era rigs. The
  orchestrator rotates before EVERY dispatch batch
  (`notes-rotate <loop> --round N`). Rotation order: prior-round
  `## Chunk r<M>-<slug>` sections first, then general sections
  OLDEST-first; the preamble, `[pin]`-marked headings (mark Environment),
  and current-round chunk sections are never auto-archived. Sizes are
  measured in BYTES — a char-count compare against the byte ceiling once
  left an emoji-heavy 10.2-12.1KB file reporting over_ceiling with 0
  sections rotated; and largest-first rotation archived the freshly
  written Environment section three times in one run. Testers cap appends
  at ~15 lines per dispatch. Cutting 86KB→6.9KB once measured 34% of
  per-request cost.
- **`.qa-loop/tools/`** `[qa]` — the testers' reusable rigs (image diff,
  crop, save injection) live here, indexed in the notes, committed, never
  deleted by provisioning. Measured: without it, three image-diff tools were
  built independently in one round (est. 2–4M per full pass).
- **Turn budgets** `[qa]` — every chunk manifest carries `turn_budget`
  (default 40): at the budget the tester files what it has and returns; a
  continuation picks up the rest. Cost tracks turns × context, not test-case
  count (3 cases measured at 2.05M vs 3 other cases at 0.20M).
- **`parallel_testers`** `[qa]` (default 1, cap 3) — runs test passes across
  N isolated worker simulators. Functional checks parallelize; performance
  measurement always runs on one uncontended simulator (the perf lane). Cuts
  wall-clock roughly by N; token cost unchanged.
  *In practice:* reply "use 2 testers" at the workflow-approval gate. Use 3
  only on a beefy Mac — each simulator wants 2–6 GB of RAM.
- **Worker provisioning** `[qa]` — worker simulators are namespaced per
  repo (`qa-worker-<hash8>-N`; two sessions once deleted each other's
  un-namespaced workers the same minute) and REUSED across loops when
  healthy — reuse preserves the per-device MCP simulator grants that die
  with a recreated UDID (`--fresh` forces recreation). The manifest lands
  in `.qa-loop/scratch/workers.json` with a `reused` flag per worker.
  *In practice:* nothing to run by hand; if a parallel lane stalls with
  "awaiting a response" on taps, a device lost its grant — the Stage-0
  real-tap probe exists to catch that BEFORE the first wave.
- **`emit_regression_tests`** `[qa]` (default false) — when on, a dedicated
  regression-test-writer turns every verified-fixed bug into an XCUITest:
  real selectors mined from your source, `XCTSkip`-guarded so an unfinished
  test can't break CI, and it never touches `project.pbxproj`.
  *In practice:* turn on once the app is stabilizing and you want findings to
  become durable CI tripwires. Verify each test's selectors once, delete the
  skip line, done. The first regression dispatch of a loop also sweeps
  `.qa-loop/archive/*/ledger.json` for previously-fixed-but-unguarded bugs,
  so turning the flag on late still captures earlier loops' fixes.
- **`regression_test_arming`** `[qa]` (default `guard`) — what the writer
  does with the XCTSkip guard. `guard`: every test stays skip-guarded until
  a human verifies selectors (safe, but "automates nothing" in a fully
  autonomous run). `arm-when-green`: the writer runs each test on the
  loop-owned device and removes the guard only from tests that ran green
  there (measured: 49 armed, 0 flaky in one autonomous loop).
  *In practice:* set `arm-when-green` for unattended runs; keep `guard`
  when a human reviews tests anyway. Wiring is unchanged either way: the
  writer never touches project.pbxproj — project-file edits route through
  qa-implementer.

## Files that are controls

*Surface: the target repo — `.qa-loop/` and `.review-loop/`.*

- **`WORKFLOWS.md`** `[qa]` — the human-approved contract: personas,
  workflow IDs, per-workflow effort expectations ("≤3 taps for a power
  user"), the Fixture policy that pins app randomness, and persona labels.
  *In practice:* this is your main steering wheel — edit it directly at the
  gate. Effort expectations become severity calibration; the Fixture policy
  (a launch arg, a seed, a deal picker) makes repros replayable; mark a
  workflow single-persona to waive the both-personas test minimum.
- **`ledger.json` routing flip** `[qa]` — to accept a UX proposal, edit its
  finding: `"routing": "proposal"` → `"auto"`, then re-run. Acceptance
  automatically triggers a design-intent check that emits constraints the
  implementation must satisfy.
  *In practice:* the only ledger surgery you should ever do by hand;
  everything else merges through scripts.
- **`merge_ledger.py` verbs** `[both]` — the only sanctioned ledger
  mutations: `resolve <ledger> <id> <status> <round> "<note>"` records a
  human decision (close a finding you've already decided against so agents
  stop re-filing it); `set-round <ledger> <N> [sha]` does round bookkeeping;
  `open <ledger> [auto|proposal|all|closeout] [--region WF-n]` extracts
  open/partial findings as a JSON brief (`closeout` = the closeout-eligible
  set; `--region` = only one workflow's findings, for tester chunks);
  `archive <loop-dir> [name]` moves a finished run's state — including
  `evidence/round-*`, so a new loop's restarted round numbering never
  collides with stale screenshots — into `archive/<name>/` so the next
  loop starts clean (moves are per-file with a post-check, and a
  sync-conflict ` 2`-name appearing during the move fails loudly right
  there instead of at report time — iCloud/Dropbox repos do this; a second
  check runs after a 3 s settle, `REVIEW_LOOP_ARCHIVE_SETTLE_S` to tune,
  because the file provider re-stamps asynchronously and once minted
  `ledger 2.json` after both checks had passed — run `hygiene_check.sh`
  again right before the final commit, and keep the repo outside the
  synced tree if it recurs); `scope <ledger> <a..b>`
  records the change under review so the report's WATCH LIST leads with it;
  `diff <loop-dir> <N> <a..b> [pathspecs]` materializes the round diff once
  for subagents (the loop directory is always excluded — its state is never
  under review; `scope` and `diff` share one range parser, so a quoted
  single string and separate words both work; excluded-but-changed paths
  are listed in an `EXCLUDED` trailer of the `.stat` and in
  `briefs/round-N.files`; a failed git leaves no partial files); `set-usage`
  records token cost — and, with `add-usage`, carries the round's settled
  figure into `rounds.md` and `verdict.json` and prints `over_budget`, so
  a figure recorded after `next-round` (a dispatch's token count can
  arrive a turn after its hand-back) reaches the report and the budget at
  once instead of a round late; `next-round <loop-dir> <N> [--fragment F] [--usage
  role=tokens …]` folds merge + metrics + usage + advance into one
  orchestrator turn and records the round's END sha, so the report's
  watch list ends each round at its own commit and lists the closeout
  commit separately; `open <ledger> wontfix` `[review]` extracts the
  accepted-disagreement set for the final-pass verifier; every `open` and
  `next-round` brief carries a `tools` block with the absolute paths of
  THIS release's agent-facing scripts, so no agent searches the plugin
  cache for one. Archives are named by the ARCHIVED
  loop's scope sha, so old loops are findable without opening each one. An
  open blocker merged in review scope mode auto-escalates max_rounds 2→5.
  *In practice:* a finding's live status is `current_status` — a top-level
  `status` field doesn't exist, which is why extraction goes through the
  `open` verb instead of hand-parsing.
- **`HARNESS_NOTES.md`** `[qa]` — simulator interaction quirks the testers
  learn (dwell-tap toggles, swipe-only sliders, screenshot scale factors),
  carried into every dispatch.
  *In practice:* pre-seed it. If you already know "the radar slider needs a
  swipe," write it in before round 1 and no tester ever rediscovers it.
- **`.phase`** `[both]` — the stall-guard marker with three honest states:
  bare `round-N-…` (a dispatch is owed; the Stop hook blocks), `…:dispatched`
  (an agent is running; stripped automatically when it returns), and
  `…:waiting:<reason>` (the orchestrator is waiting on something that isn't
  a subagent — a 529 backoff, a background task, you; the hooks leave it
  alone). The hooks COUNT live dispatches in `briefs/.dispatched`, and
  the count — not the suffix — is what the Stop hook reads: every dispatch
  made while a phase is live is counted, under `:waiting:` too, so two
  agents running at once (a panel-verifier beside the closeout
  implementer) cannot unmark each other and a phase write cannot make a
  running agent look absent (measured: a closeout implementer dispatched
  under `:waiting:panel-final`, in the same batch as its own phase write,
  went uncounted and the Stop hook blocked a turn nine minutes before it
  returned). `:dispatched` is stripped when the last agent returns.
  `set-round` and `next-round` reset a count left above zero at the round
  boundary and record it (`dispatch-count-mismatch`). Each plugin's hooks
  guard only their own loop directory.
  *In practice:* write the phase in its own call before a dispatch, never
  in the same batch. Escape hatch — if a dead session leaves the guard
  armed, write `done` into the marker and the guard stands down. A count
  left high by a crashed agent makes the guard fail OPEN (it allows stops)
  until the next round boundary; delete `briefs/.dispatched` to clear it
  sooner.
- **Pausing and resuming** `[both]` — a loop whose marker ends
  `:waiting:<reason>` (or reads `awaiting-human`) is PAUSED, not finished
  and not abandoned: the next session resumes from the step the marker
  names and does not archive. The session-size gate produces this state
  when it sends a loop to a fresh session.
- **`thrashing_soft` remembers being answered** `[both]` — after a human
  approves a continuation the orchestrator records it (`consulted` verb);
  the next thrashing signal is hard automatically, and at max_rounds the
  soft question becomes the only honorable one: "abort, or raise max_rounds
  and continue". Rejection history also survives status changes now (a
  `rejections` array the merge unions), so the report's rejection section
  can no longer read "none" after seven real rejections.
- **Retry and fallback policy** `[both]` — a dispatch that dies with no
  fragment is retried up to 3× with in-turn backoff (60/180/300 s); agents
  write `<fragment>.partial` incrementally so a killed dispatch leaves its
  work, and the retry resumes from it. A pinned model is never swapped
  silently: fallback only after three failures, disclosed in the report.
  A result without its artifact (no CHANGES block, no fragment) is a pause —
  the same agent is resumed, never re-dispatched.
  *In practice:* nothing to configure; if you see "ran on <model>: outage"
  in a report, that round's adversarial diversity was reduced.
- **What to commit** `[both]` — conclusions in git, evidence and scratch on
  disk; the loop-dir `.gitignore` each loop writes is the definition. It is
  DEFAULT-CLOSED (`*`, `!*/`, then one negation per conclusion: REPORT,
  ledger, rounds, verdict, and the `feedback/` records — qa adds coverage,
  the three docs, `tools/`, `regression-tests/`), so anything unanticipated — a Finder-duplicated
  `fragments 2/`, a stray `.pyc`, a gigabyte of screenshots — stays out of
  the index by default (measured: the old denylist let all three into one
  host repo's history). Negations match at any depth, so conclusions inside
  `archive/<name>/` stay tracked while archived scratch does not. A
  pre-existing host `.gitignore` is never overwritten — the loop suggests
  the upgrade instead. While a loop is live, the commit guard denies
  `git add -A`/`--all`/`.`/`-f` and bare loop-dir adds: staging is by
  explicit file path. If your repo ignores the whole loop
  directory, the loop notices (`git check-ignore`) and says so rather than
  pretending — archives then live only on that machine.
  *In practice:* nothing to set; if `hygiene_check.sh` flags a violation at
  setup the loop fixes it (`git rm --cached`, duplicate renames — never
  disk deletes), and anything still standing at report time lands in the
  WATCH LIST.
- **Minors split by risk, not just cost** `[review]` — round briefs carry
  blockers, majors, and minors flagged `fix_risk` (their fix changes shipped
  behavior — measured: a deferred minor changed a shipped predicate on both
  platforms inside the no-iteration closeout); plain test/doc/polish minors
  wait for closeout. The closeout's verify_cmd must run every test target
  its diff touches (a build is not a test), and an introduced_by_fix
  BLOCKER there earns one extra scoped fix dispatch — otherwise the report
  headline is "done-but-red", never a buried open row. The closeout
  reviewer's fragment carries the suite counts as data (`suites`: target →
  executed / failed / skipped) and a hook refuses one without them; the
  report's Closeout section renders the table, or says the counts were
  not reported.
  *In practice:* nothing to set; `open --severity major` includes fix_risk
  minors automatically.
- **Read guard** `[both]` — while a loop phase is in flight, a `PreToolUse`
  hook denies the measured token sinks with the fix in its message: `cat` of
  a >200-line file, `head`/`sed` windows over 200 lines, unfiltered
  `xcodebuild test`/`swift test`, and re-pulling a whole diff that is already
  materialized in `briefs/round-N.diff`. Agents re-issue a windowed or
  filtered command; nothing is lost. Inactive outside loop phases. It
  matches command POSITIONS: a heredoc or quoted string that merely
  contains a test command (writing a `verify_cmd` into a brief) is not a
  test run.
- **Simulator discipline** `[both]` — every agent may touch only the device
  udid named in its dispatch, and never finds an app process by name
  (`pgrep -f`, `lldb -n`): other sessions' simulators share your Mac, and an
  unscoped attach once fired a memory warning into someone else's device.
  *In practice:* if you run several loops at once, this is the rule keeping
  them apart; the orchestrator names one booted device per dispatch.

- **Deterministic helpers** `[both]` — `render_report.py <loop-dir>` renders
  every mechanical REPORT.md section (trend incl. Promoted column, findings,
  proposals, rejections, persona matrix, coverage gaps, closeout); the model
  fills only the WATCH LIST. `[review]` `hotspots.py` maps git churn × size ×
  recency so cold reviews read where defects live; `mutate.py <manifest>`
  re-runs an implementer's mutation claims in an isolated worktree — "8/8
  killed" is now checkable (the implementer names its manifest in CHANGES as
  `mutations`; the runner runs each `test_cmd` unmutated first and refuses
  a red baseline — a filter that matched nothing once reported every
  mutant killed — refuses uncommitted changes to the manifest's files
  unless `--allow-dirty` — a pre-commit run once reported every mutant
  survived against the old code — and honors a per-mutant `test_cmd` so
  UI-only mutants alone pay the UI suite). `--only id1,id2` runs a subset
  of the named manifest with no scratch copy; `--detach` then
  `mutate.py wait <manifest>` runs a manifest longer than the 10-minute
  command ceiling (exit 3 = still running, call `wait` again; results
  accumulate in `<manifest>.results.json`); every result carries
  `elapsed_s`. A copy refuses to run when a HIGHER version of the plugin
  is installed beside it (`--allow-stale` overrides) — two implementers
  once searched for the script and ran a release-old copy. `[qa]` `plan_round.py` selects the targeted set and emits
  chunk manifests (≤5 cases, ≥3 after tiny-chunk coalescing — each dispatch
  pays ~40-60K fixed cost) from `paths(WF-n)` lines in WORKFLOWS.md and
  `TC-x.y [persona] [smoke] [perf]` lines in TESTCASES.md — workflow ids
  may carry a letter suffix (`WF-9b`/`TC-9b.1`); all of a workflow's chunks
  stay on one worker (split siblings filed duplicate findings); the perf
  lane runs only when a perf-relevant change or finding exists; open
  findings with screen-name regions get a `findings-misc` chunk; a
  selected case landing in no chunk is a HARD error (a silently unchunked
  workflow once nearly hid a blocker); `--summary` prints a human-readable
  digest; `nfr_analyze.py`
  turns sampler output plus the tester's `marks.jsonl` windows into numbers
  and candidate findings. `[both]` `hygiene_check.sh <loop-dir>` reports
  git-hygiene violations in the loop dir (tracked scratch, Finder-duplicate
  names, >256KB tracked files, denylist-style ignores, tracked files
  missing from disk) — advisory, run at setup and again before the report.
  `--restore` moves back every ` 2`-style duplicate whose plain name is
  missing and which is the only duplicate of that name; it never
  overwrites, never deletes, and leaves anything ambiguous alone. The
  archive's settle pass covers renames that follow a move by seconds.
  After a sync outage, a sync toggle, or a restore from backup, run
  `hygiene_check.sh <loop-dir> --restore` once per repo (measured: one
  accidental iCloud Drive off/on renamed 40 files across a source tree,
  committed archive conclusions among them, found a day later).
  *In practice:* you don't run these yourself — they are why the loops got
  cheaper. The two obligations they create: every workflow needs a
  `paths(WF-n): …` line (the orchestrator writes it at Stage 1), and every
  test case line must start `TC-x.y [persona]` with optional `[smoke]` /
  `[perf]` tags.

## Review panel (multi-provider)

*Surface: `.review-loop/panel.json` (lanes, tracked) + a machine-local
consent file under `$XDG_CONFIG_HOME`/`~/.config/review-loop-tools/consent/`
(`panel_review.py consent-path <loop-dir>` prints it), offered at Setup
when the CLIs exist.*

- **What it is** `[review]` — external models (OpenAI's codex CLI, Google's
  gemini CLI, a local ollama model) review the diff as extra skeptics. They
  are FINDERS only: candidates go to the blind `panel-verifier` agent
  (pinned `sonnet`), and only chair-verified findings reach the ledger, so
  metrics and convergence math are untouched. Runs on the seed diff (SCOPE
  mode) and once after any stop on the accumulated change (`seed+final`).
  *In practice:* ask for "a panel" when starting a loop; the setup gate
  probes which lanes are installed, authenticated AND consented
  (`panel_review.py probe --smoke` — its `gate_issues` list is the gate;
  the local lane is smoked too) and asks for consent. Long lanes: `run
  … --detach` then `wait <loop> <round>` (bounded under the Bash tool's
  10-minute ceiling; exit 3 = still running, call again). One lane again:
  `run … --lanes <name> --force` — without `--force` existing candidates
  are reported `cached` and never overwritten. A lane's `model` may be a
  list; on quota or model-unavailable errors the next entry is tried and
  `model_used` is recorded (free-tier gemini keys exhaust a daily quota
  after roughly one 32K-token prompt). Lane CLIs run with
  `NODE_OPTIONS`/`PYTHONPATH`/`DYLD_*`-style injection vars scrubbed — a
  terminal wrapper's stale preload once killed both Node lanes at startup.
- **Consent and privacy** `[review]` — codex/gemini lanes send the diff off
  the machine; the MACHINE-LOCAL consent file (outside the repo, keyed by
  the loop dir's path — `consent-path` prints it)
  records `remote_lanes_approved` (and, for `cmd` lanes, which execute a
  command from git-tracked panel.json, a `cmd_lanes_approved` LIST of the
  exact approved command strings or their sha256 digests — a pulled
  panel.json that changes the command fails the gate) and the script
  refuses those lanes without it. Nothing INSIDE the repo can grant
  consent: files under a checkout arrive with clones and unpacked
  ZIP/`git archive`/cp -r bundles, so an in-repo `panel-consent.json`
  (the pre-0.12 location) is ignored with a stderr hint — re-consent once
  at the machine-local path. Approval
  binds the command STRING, not the contents of any file it invokes
  (`bash tools/lane.sh` stays approved while lane.sh changes under a
  pull) — prefer self-contained commands.
  Gemini's free OAuth tier may train on inputs — use API keys
  (`OPENAI_API_KEY`, `GEMINI_API_KEY`, environment only, never in
  panel.json). Private repo → local lane only (ollama on a loopback
  `OLLAMA_HOST`, nothing leaves the machine, no account; a non-loopback
  `OLLAMA_HOST` is treated as a remote lane).
  Known residual: codex/gemini run in an empty scratch cwd with a scrubbed
  env (no workspace to discover), but codex's `--sandbox read-only` still
  permits absolute-path READS — a prompt injection in the reviewed diff
  that already names a path could read (never write) files outside the
  diff; no tighter codex sandbox flag exists today. gemini's
  `-s/--sandbox` flag was VERIFIED (2026-09-13, gemini-cli 0.59.0, macOS
  Seatbelt) not to help: an absolute-path read succeeded under the default
  `permissive-open` profile AND under `restrictive-open`, and
  `restrictive-closed` blocks the API egress the lane exists to make — so
  the flag is not adopted, and for both lanes the empty jail, not a vendor
  sandbox, is the isolation.
- **Flood control and measurement** `[review]` — each lane files at most 10
  candidates by confidence; candidates whose every citation lies outside
  the round's changed-file list are dropped before the verifier reads them
  (`dropped_no_evidence`); the report's Panel section shows per-lane
  filed/confirmed/demoted/duplicate/rejected, and "kept" (confirmed +
  demoted — duplicates of ledgered findings never count) is the
  drop-or-keep signal. Precision acts on it: a lane that kept 0 of >=5 at
  seed is capped at 3 candidates on the final pass (`cap` in its result),
  and a lane that was 0/N in each of the two most recent archived loops is
  `disabled-by-precision` until the lane sets `"precision_override": true`
  (measured: one local 30B model filed 40 candidates across four passes
  with 0 kept, ~140K verifier tokens per run). Lane failures (timeout, auth
  expiry, outage, quota, launch) are soft: skipped with disclosure — one
  stderr line per lane with the classified reason first, `failed`/`skipped`
  counts in the run JSON, exit code 0 — never blocking a round. Each lane
  result carries `elapsed_s` and whatever token counts the CLI or server
  exposes (`tokens`; nothing is estimated).
  *In practice:* confirmed findings appear in the report tagged
  `via panel:<lane>`; a finding tagged with several lanes is cross-family
  agreement — read it first. The verifier's `notes_for_chair` travel to the
  chair by file; the final-pass verifier gets the open ledger and the
  wontfix list so re-filed findings become `duplicate_of`.

## Driver backends (qa)

*Surface: `${CLAUDE_PLUGIN_ROOT}/drivers/<backend>/`, copied to
`.qa-loop/driver/` at Stage 0.*

- **The driver contract** `[qa]` — a platform-neutral verb set every
  backend serves against one device/session: `launch [K=V…]`,
  `activate`/`terminate`/`home`/`state`/`frame`, `tap`/`doubletap`/
  `press`/`drag`/`dragslow`/`swipe`, `type`/`key`/`selectall`,
  `shot <host-path>`, `find`/`findall`/`wait <id>`, `tapid`/`tapoffset`/
  `tapbtn`/`taptext`/`btn`/`text`, `labels [kind] [substring]`, `alert`,
  `tree [depth]`, `rotate`/`orientation`, `sleep`/`ping`/`quit`. Replies
  are `OK …`/`ERR …`; coordinates are device points; element queries use
  accessibility identifiers/labels. Tester prompts speak ONLY these verbs;
  everything platform-specific lives below the contract line.
- **`ios-xcuitest`** `[qa]` — the shipped backend: a scriptable XCUITest
  server + `qa.py` client, target app passed at start
  (`start.sh <udid> <bundle-id>`). Needs NO per-device MCP grant — the
  autonomous-run killer — and launches with a fixture environment,
  rotates, and dumps every visible label in one call (measured: 130
  screenshots in 3,161 requests vs 440 the loop before). Build cache
  (`dd/`) stays on disk, ignored by the allowlist.
  *In practice:* nothing to configure; Stage 0 copies and starts it. The
  MCP simulator tool is the fallback when the driver cannot build.
- **The seam** `[qa]` — `provision_workers.sh`, the
  regression-test-writer, and the `ios-xcuitest` backend are the iOS
  backend family. A future `android-appium/` or `web-playwright/` backend
  implements the same verb table in its own directory with its own
  provisioner/regression-writer equivalents; the skill text above the
  driver line does not change.

## Model pins

*Surface: `agents/*.md` frontmatter.*

- **ux-tester: `opus` · fix-reviewer: `sonnet` · implementer: `inherit`**
  `[qa]` — three seats, three models: the loop's guard against correlated
  blind spots. The review loop pins its skeptical-reviewer to `opus` against
  the inheriting implementer. `[review]`
  *In practice:* one rule — keep all pins distinct from each other **and**
  from your session model. Switch your session to Opus? Move the tester's
  pin. Fix-reviewer rejecting too much? Its pin is the tuning knob before
  you weaken the rejection policy.

## Commit guard

*Surface: environment variables, set in the session — not committed.*

- **Scope** `[both]` — the staging rules (`git add -A`/`--all`/`.`/`-f`
  and loop-dir directory adds denied) arm only while a loop is LIVE:
  `.phase` at round*/seed*/awaiting-human. A finished loop's `done` arms
  nothing (the guard once blocked a pre-loop commit for weeks with a
  message claiming a loop was running). Stage by explicit path anyway.

- **`REVIEW_LOOP_MAX_DIFF`** `[both]` (default unlimited) — blocks any
  implementer commit whose staged diff exceeds N lines.
  *In practice:* set ~400 for unattended runs — a runaway "fix" that
  rewrites half the app gets stopped at the commit, not discovered in the
  report.
- **`REVIEW_LOOP_TEST_CMD`** `[both]` (default off) — a command that must
  exit 0 before any commit is allowed.
  *In practice:* point it at your fast unit suite; keep it under a minute or
  every round crawls.
- **`REVIEW_LOOP_UNATTENDED`** / **`QA_LOOP_UNATTENDED`** `[both]` (default
  off; set to `1`) — declares nobody is at the keyboard. At an
  ask-the-human verdict (`thrashing_soft`) the orchestrator takes the
  documented default either way; with the knob set, `next-round` RECORDS
  the taken default in `rounds.md`, so the report explains itself instead
  of needing a hand-written note (a field run hand-edited the WATCH LIST
  for exactly this).
  *In practice:* set it whenever you walk away from a running loop.

## During a run

*Surface: the live session.*

- **The Stage-1 gate** `[qa]` — the loop's only blocking stop: it announces
  `max_rounds`, `parallel_testers`, and a cost estimate (recalibrated with
  actuals after round 1), then waits for your workflow sign-off.
  *In practice:* this is where you steer — edit WORKFLOWS.md, change
  settings, or trim rounds with real numbers in hand. After this it runs
  autonomously.
- **`FIX REJECTED: <id> — <reason>`** `[qa]` — the fix-reviewer found a fix
  that satisfies the finding but harms the product (gameable metric,
  corrupted state). The finding reverts to open; the implementer retries
  next round with the rejection as its brief.
  *In practice:* read these when they appear — a rejection often means the
  *finding* was a trap and belongs in proposals for a human decision.
- **`thrashing_soft`** `[both]` — thrashing signals with mitigating progress
  (0 open blockers, positive closes) now pause and ask you — abort with the
  report, or one more round? — instead of hard-aborting. A second thrashing
  signal after you approve a continuation is final.
  *In practice:* say "one more round" when the open findings are cheap and
  the trend is genuinely converging; take the abort when findings are
  reopening. Unattended runs don't wait: the default is abort-with-report,
  then closeout (set `REVIEW_LOOP_UNATTENDED=1` and the taken default is
  recorded in rounds.md). A converging series (every open finding
  introduced_by_fix, worst severity non-increasing over the rounds that
  exist — minimum two, so short scoped runs qualify — no reopens) no
  longer trips the churn signal at all. And when a run still stops
  `thrashing_soft`/backstop but closeout leaves 0 blockers/majors open,
  the report headline says `converged-in-closeout`, not "thrashing".
- **CLOSEOUT** `[review]` — after any stop, one mop-up cycle fixes and
  re-verifies the leftover cheap findings: open `introduced_by_fix` findings
  (any severity — the loop's own regressions never ship to BACKLOG
  unexamined) plus open minors. One implementer dispatch, one targeted
  reviewer verification, no iteration; failures land in BACKLOG.md with
  notes and the report gets a Closeout section.
  *In practice:* nothing to configure — it runs when eligible findings
  exist. Open majors that aren't introduced_by_fix are deliberately excluded:
  they stopped the loop for a reason you should read.
- **Interrupting** `[qa]` — killing a round is always safe. Durable state:
  ledger, merged fragments, coverage, docs. Resume restarts the round from
  its deterministic reset.
  *In practice:* Esc without fear. Also: a quiet transcript isn't a dead
  loop — check the background-task list before assuming a stall.

## Reading the report

*Surface: `.qa-loop/REPORT.md` — the parts a human must actually read.*

Skim in this order:

1. **WATCH LIST** — the most invasive diffs and every trap-flagged
   (`fix_risk`) finding.
2. **UX PROPOSALS** — behavior changes awaiting your call.
3. **FIX REVIEW REJECTIONS** — every fix the reviewer shot down.
4. **COVERAGE GAPS** — blocked/skipped test cases with reasons.
5. **PERSONA MATRIX** — the workflow × persona table, where a "both"
   workflow tested by one persona shows as a hole.

CONVERGED is only ever declared after a verified full pass — but the WATCH
LIST exists because decorrelated reviewers reduce, not eliminate, the chance
of agents agreeing on a bad fix. Ten minutes here is the human half of the
contract.

## Feedback for the plugin maintainer

*Surface: `/review-loop-tools:feedback`, `/qa-loop-tools:feedback`,
`/arch-docs-tools:feedback` — and `<loop-dir>/feedback/`.*

The report (`REPORT.md`) is for the owner of the repo the loop ran in.
Feedback is for the maintainer of the plugin. They are separate files with
separate readers, and filing feedback is always an invitation, never a gate.

- **`/<plugin>:feedback`** `[both]` — files a field report in one command.
  The script gathers the objective half (below), lays out a draft, and the
  agent fills in only what it observed: the maintainer's watch questions
  (`observed` / `not observed` / `n/a`), what to keep, defects in impact
  order (what happened, expected, smallest repro, evidence path, cost,
  suggested mechanism), friction, decisions taken without the human, items
  seen again, host-repo recommendations, environment artifacts, wishes.
  Every item gets an id — `<rl|qa|ad>-<version>-<yyyymmdd>-<host>-<n>` —
  that proposals and commit messages cite.
  *In practice:* run it right after a loop, in the same session, while the
  run is still in context. Empty sections are a good answer.
- **`--quick`** `[both]` — the objective bundle alone: no questions, no
  writing. Version, verdicts, anomalies and measured cost.
  *In practice:* the floor. File it even when you have nothing to say.
- **Where it goes** `[both]` — two places, both on this machine, nothing
  sent anywhere: the report is written to
  `<loop-dir>/feedback/<plugin>-<version>-<date>.md` (a conclusion:
  allowlisted, committed by explicit path with the run summary beside it),
  and the same file is copied to
  `${XDG_DATA_HOME:-~/.local/share}/quiller/inbox/<host>/` — the drop the
  maintainer's ingest reads. The drop is outside every repo by rule: a
  session in one repo never writes into another repo's tree. On another
  machine, send the one file by any means; it is self-contained.
  *In practice:* do not write reports to `docs/reports/` or anywhere else
  by hand — a file outside the drop is only found if someone goes looking.
- **`feedback/run-summary.json`** `[both]` — written by `render_report.py`
  at report time, whether or not anyone files feedback: the plugin version
  read from the code that ran (beside the `installed_plugins.json` entry —
  a mismatch means a symlinked or `--plugin-dir` install), platform,
  settings, the verdict row per round, finding COUNTS by severity and
  status, fix-review rejections, proposals, unattended defaults, hygiene
  violations, reported usage, panel tallies and lane telemetry, dispatch
  wall-clock, anomalies. Counts only — never a finding's claim, id or
  evidence, and paths are folded to `~`.
- **`feedback/dispatches.jsonl`** `[both]` — the Agent-tool hook records
  each dispatch's start (agent, label, session size) and the SubagentStop
  hook its return, so wall-clock per dispatch costs no tokens and nobody
  times dispatches by hand.
- **`feedback/anomalies.jsonl`** `[both]` — every place the run left the
  documented path. Scripts and hooks record their own: `lane-error`,
  `lane-timeout`, `lane-skipped`, `lane-cached`, `lane-capped`,
  `lane-disabled-by-precision` `[review]`; `mutate-baseline-red`,
  `mutate-dirty-refused`, `mutate-allow-dirty`, `mutate-stale-refused`
  `[review]`;
  `plan-lint-problem`, `plan-degenerated`, `plan-unchunked`,
  `notes-over-ceiling` `[qa]`; `dispatch-count-mismatch`,
  `session-gate-blocked`, `read-guard-denied`, `commit-guard-denied`,
  `commit-guard-no-jq`, `archive-duplicates`, `archive-late-duplicates`,
  `hygiene-violation` `[both]`. The orchestrator records the rest with
  `merge_ledger.py anomaly <loop-dir> "<one line>" [--code <code>]` — the
  moment it works around the plugin (`workaround`, the default), a worker
  fails the grant probe (`grant-probe-failed`), the driver does not answer
  (`driver-ping-failed`), a completion is notified twice
  (`usage-repeat-notification`), or a pinned agent falls back to another
  model (`model-fallback`). `FIELD_LOG_OFF=1` silences all of it.
  *In practice:* guard denials record WHICH rule fired, never the command.
- **`loop_usage.py`** `[both]` — effective tokens from this repo's session
  transcripts: `input×1 + cache_read×0.1 + cache_write×2 + output×5`,
  deduplicated by request id, images 1,600 flat — the accounting every
  prior measurement used, so figures compare across repos and versions.
  The project directory is derived from the repo path; `--since`/`--until`
  filter per record; output is per role and per dispatch. The feedback
  command runs it over the loop's own window (first dispatch to report).
  *In practice:* never re-derive token tables by hand or with a scratch
  script.
- **`FIELD-QUESTIONS.md`** `[both]` — ships at each plugin's root, versioned
  with the code: the watch items for this version, the settled decisions
  (report only NEW evidence against them), and what happened to earlier
  field items by id (shipped in which version, declined and why, backlog).
  *In practice:* read the last two sections before writing a defect; an
  item already listed goes under "Seen again" by id.
- **Archive** `[both]` — `feedback/` moves with its loop into
  `archive/<name>/`. Feedback filed after a loop was archived reports on
  the newest archive and says so.

## Playbooks

- **First run on a new app** — all defaults. Spend your effort at the gate:
  fix workflow effort expectations, pin the Fixture policy, pre-seed
  HARNESS_NOTES. Check the cost estimate before saying go.
- **Cheap smoke pass** — `max_rounds 2`, Sonnet session, no regression
  tests. The opus tester still finds real issues; you're trading implementer
  depth for cost.
- **Pre-release deep audit** — "use 3 testers", `max_rounds 5`,
  `emit_regression_tests true`, `REVIEW_LOOP_TEST_CMD` set. Budget a workday
  of wall-clock and read every report section.
- **Accepting a proposal** — flip its `routing` to `"auto"` in ledger.json,
  re-run. Intent check emits constraints → implementer must satisfy them →
  fix review verifies each one. Check the next report's rejection section.
