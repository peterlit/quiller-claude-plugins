# Proposal: qa-loop-tools 0.13.0 + review-loop-tools 0.13.0 — 2026-09-09 field reports

Sources (committed in `docs/inbox/`):

- `loop-tooling-feedback-2026-09-09.md` — agent 1 (weatherapp), qa-loop-tools **0.12.0**: 85 cases, 42 findings, 1 blocker found+fix-verified, parallel lane dead on arrival.
- `qa-loop-0.12.0-feedback.md` — agent 2 (Causeway), qa-loop-tools **0.12.0**: 90 cases, 37 findings, 24 fixed-verified, 49 armed XCUITests, 40.1M effective tokens measured.
- `review-loop-0.10.0-feedback.md` — agent 2 (Causeway), review-loop-tools **0.10.0**: scoped 2-round loop, 12 findings, ended `thrashing_soft` on a run that was actually converging.

Version check: both qa reports ran the **current** qa-loop-tools version (0.12.0). The review report ran 0.10.0; the 0.11.0/0.12.0 releases since were multi-provider-panel work only, and I verified each review complaint against current code — all still stand.

Code verification done before proposing (all confirmed in the working tree):

- `plan_round.py:29` — `PATHS_RE` is `WF-\d+`, no letter suffix; `plan_round.py:146` sorts workflows with `int(w.split("-")[1])`, which cannot survive `WF-9b` either.
- `provision_workers.sh:26-39` — `up` deletes every `qa-worker-*` on the host, unconditionally.
- `merge_ledger.py archive` keep-list (`qa:444`) — `evidence` stays in place across loops.
- `notes_rotate` second pass (`qa merge_ledger.py:270-287`) — archives the **largest** sections, and compares the ceiling against a **character** count (`sum(len(k))`) while reporting `over_ceiling` from `os.path.getsize` **bytes**. With emoji-heavy notes (⏰🌟 workflow names) the char count can sit under 10240 while the file is 10.2–12.1KB — exactly agent 1's "over_ceiling:true, rotated 0, repeatedly".
- `plan_round.py:110` — an open finding with no `test_case` and a non-`WF-` region (`Main`, `DailyView`) is silently dropped from targeting.
- `plan_round.py:151` — chunks round-robin across workers (`k % workers`), so sibling chunks of one workflow land on different workers (agent 2's duplicate-id source).
- `mutate.py:71` — `if not m.get(k)` rejects `"replacement": ""` as *missing*.
- `SKILL.md:322` (review) — the CONVERGING SERIES exemption hard-requires "non-increasing over three rounds"; a `max_rounds=2` scoped run can never qualify.

---

## Part A — qa-loop-tools 0.13.0

Ordered by impact. A1/A2 are the two items that threatened run integrity (parallelism silently dead; a workflow silently untested); both agents independently hit A3.

### A1. Worker provisioning: reuse, namespace, own-manifest-only deletion, real grant probe

Both agents lost the parallel lane to the same root cause from two directions: agent 1's fresh UDIDs had no per-device MCP grants (all three wave-1 testers refused every tap, user away); agent 2's workers were **deleted by another session** running the same script the same minute.

Mechanism, all in `provision_workers.sh` + Stage 0 skill text:

1. **Namespace workers per repo**: `qa-worker-<hash8>-N` where `hash8` is the first 8 hex of `shasum` of the loop dir's absolute path. Printed in the manifest as today.
2. **Delete only from our own manifest**: `up` and `down` delete only UDIDs listed in the existing `workers.json` (plus name-matched `qa-worker-<hash8>-*` leftovers of *this* repo). Never touch other prefixes.
3. **Reuse over recreate**: if a manifest device exists, is the right devtype/runtime, and boots, keep it — this is what preserves per-device MCP grants across loops. `up --fresh` forces the old delete/recreate behavior.
4. **Stage 0 real grant probe**: the skill's Stage 0 check changes from "verify the control tools reach subagents" (tool availability) to a **real tap on every worker UDID before the first dispatch wave** — one micro-dispatch per worker that taps the springboard and reports success. The docs currently conflate availability with per-device grants; say so explicitly, and instruct: any worker failing the probe → drop to the granted subset (or sequential) *before* wave 1, and tell the user which UDIDs need a grant.

### A2. Chunker: letter-suffixed workflow ids + selected⊆chunks lint

Agent 1's blocker lived in `WF-9b`; its TCs appeared in `selected` and in open-findings targeting but no chunk ever contained them, across all three rounds, and lint passed. Mechanism:

1. Accept `WF-\d+[a-z]?` everywhere in `plan_round.py`: `PATHS_RE`, TC→WF derivation, region matching, and the sort key (numeric part then suffix — replace the bare `int()`).
2. **Lint asserts every selected TC lands in exactly one chunk** (and no chunk contains an unselected TC). Violation is a hard error naming the orphaned TCs. This catches any future parser drift, not just this one.
3. Smoke test: a fixture TESTCASES/WORKFLOWS pair with `WF-9`/`WF-9b` side by side; assert both chunk and both sort.

### A3. Archive moves evidence with the loop

Both agents hit stale-evidence collisions (35 and 1,117 prior-loop files respectively; three testers each burned turns discovering it). Mechanism: `merge_ledger.py archive` moves `evidence/round-*` into the archive dir alongside fragments/briefs; `evidence/` itself (and `tools/`, `driver/`) stays. Update the KEEP comment to say evidence *contents* ride with the archived loop. Shared-script sync to review copy (review has no evidence dir; the move loop is a no-op there — verify with `diff -q` per ritual).

### A4. notes-rotate: byte-accurate ceiling, age-ordered rotation, protected sections, configurable ceiling

Three intertwined defects (agents 1+2) plus a doc contradiction:

1. **Measure in bytes**: compare `len(section.encode("utf-8"))` sums against the ceiling — fixes "over_ceiling:true, rotated 0 sections" (char/byte mismatch, verified above).
2. **Round-stamped chunk sections**: the skill instructs testers to head per-chunk notes `## Chunk r<round>-<slug>`; `notes-rotate` gains a `--round N` argument and archives chunk sections with round < N. This resolves the tester/orchestrator contradiction agent 2 hit (fresh chunk notes archived before the next chunk read them): the orchestrator keeps rotating before every batch, but current-round chunk notes now survive it by construction.
3. **Second pass rotates oldest-first, never the first section**: replace largest-first with bottom-up file order among non-preamble general sections (append-mostly files ⇒ position approximates age poorly in the other direction; oldest content sits nearest the top *after* the preamble, so archive from the section just after the preamble downward). A section whose heading contains `[pin]` is never auto-archived (testers/orchestrators mark the Environment section). If pins alone exceed the ceiling, report `over_ceiling` honestly and rotate nothing pinned.
4. **Configurable ceiling**: `QA_NOTES_CEILING_KB` env (default 10) — agent 2's driver-era rig legitimately needs more. Document in CONTROLS.md.

### A5. Targeted-pass economics: minimum chunk size + workflow-worker affinity

Agent 2: 23 chunks per full pass, seven of 1–2 cases, ~40–60K fixed cost each; plus three duplicate finding pairs from sibling chunks of one workflow on different workers. Mechanism, both in the chunk builder:

1. **Workflow affinity**: all chunks of one workflow go to the same worker (assign workers per *workflow*, round-robin by workflow weight, not per chunk).
2. **Tiny-chunk coalescing**: after per-WF splitting, merge adjacent same-worker chunks until each has ≥3 TCs (or is the only chunk of its workflow and the workflow only has 1–2 TCs — then merge into the smallest same-worker neighbor, keeping `region_filter` a list of the covered WFs, which the schema already allows).

### A6. Non-WF-region findings must reach a tester

Agent 2: identifier findings filed with screen-name regions (`Main`, `ContentView`) only ever reach the implementer; no tester chunk verifies them. Mechanism: in `plan_round.py`, an open/partial auto finding with no `test_case` and a non-`WF-` region goes into a catch-all `findings-misc` chunk (smoke-persona, region_filter = the literal regions) instead of being dropped; lint counts them so nothing is silent.

### A7. Minors-only endgame: allow one implementer dispatch under `full_pass_required`

Agent 2's round 3 stranded two one-line fixes because `full_pass_required` forbids an implementer dispatch. Mechanism (SKILL.md policy change only): when the verdict is `full_pass_required` **and** open auto-routed findings are all minor, the orchestrator may dispatch one implementer for those minors before the confirmation pass; the confirmation pass then also re-runs those findings' TCs. Blockers/majors keep the current strict behavior.

### A8. Regression writer: arming policy setting + documented wiring hand-off

Agent 2's arm-when-green policy produced 49 armed, 0-flaky tests; the default skip guard "automates nothing" in autonomous runs. Agent 1's writer refused pbxproj edits even with relayed user authorization, orphaning good tests. Mechanism:

1. New setting `regression_test_arming: guard | arm-when-green` (default `guard`, documented in CONTROLS.md). `arm-when-green`: the writer arms a test only after a green run on a named loop-owned device.
2. **Keep the writer's pbxproj boundary** (see Declined D2) and document the intended path in the skill + agent prompt: project-file wiring is routed through `qa-implementer`; the writer's job ends at committed guarded tests + a wiring note in its fragment.
3. Skill note (agent 2's judgment call, worth codifying): run the writer sequentially after the implementer unless the implementer's scope is known-tiny — the concurrent worktree run cost a 66K repair dispatch for six tests written against pre-fix copy.

### A9. Perf lane gating

Agent 2: `[perf]` TCs re-ran all four rounds, all clean, ~90K/round. Mechanism: in `plan_round.py`, populate the perf lane only when (a) pass_type is full, or (b) a perf finding is open, or (c) the diff touches a workflow containing a `[perf]` TC. Otherwise emit the lane with empty `tcs` and a `why` note.

### A10. Small fixes batch

1. `set-usage`/`add-usage` output: rename `round_tokens` → `round_total_tokens` in the printed JSON (it is the round total; agent 1 misread it next to a per-role call).
2. Stop-condition vocabulary: `qa_metrics.py`/`render_report.py` accept and render a `user-abort` stop reason; the trend row for an aborted full pass reads `full (aborted N/M)` (both agents hand-edited reports for this).
3. `render_report.py` watch-list: exclude findings resolved as duplicates from "proposal awaiting decision".
4. `plan_round.py --summary`: human-readable plan digest (pass type, why, chunk table with worker/TC counts, perf lane, estimate) — both orchestrators re-parsed the JSON by hand.
5. MCP `build` tool targets "first booted device" (agent 2 #14): not our tool; add one skill line — always pass the loop-owned UDID explicitly to build/install steps.
6. CONTROLS.md budget note: agent 2 measured 6.9× reported→effective (inside the documented 4–11×); add his sentence — the budget stop is a warning on the reported scale and "cannot protect a real spend". No behavior change (settled decision).

---

## Part B — review-loop-tools 0.13.0

### B1. Converging-series exemption must fit scoped runs; closeout can relabel the stop

The headline defect: a 2-round scoped run ended `thrashing_soft` while every open finding was `introduced_by_fix`, nothing reopened, worst severity major→major→(closeout) minor — because the exemption requires three rounds of non-increasing severity, which `max_rounds=2` can never produce. Mechanism:

1. SKILL.md: the exemption evaluates "non-increasing over the rounds that exist (minimum two)" instead of a hard three.
2. Closeout relabel: when a loop stops `thrashing_soft`/`at-cap` and closeout ends with 0 blockers/majors open, the closeout verdict records `converged-in-closeout`; `render_report.py` headlines that instead of "thrashing". The original stop stays in `rounds.md` for the record.

### B2. Unattended defaults: an env knob that self-documents

The verdict text says "ask the user"; the skill body says "unattended, take the default"; the report can't tell which happened. Mechanism: `REVIEW_LOOP_UNATTENDED=1` env (read the same way `commit_guard.sh` reads its knobs, documented in CONTROLS.md). When set, `merge_ledger.py next-round` appends "(unattended default: <choice>)" to the `rounds.md` entry it writes at any ask-the-user decision point, and the verdict text mentions the knob. No flag on individual verbs — one knob, recorded where it acts.

### B3. Archive integrity under iCloud/Dropbox

macOS sync produced `ledger 2.json`-style Finder duplicates during `archive`'s directory `mv`, unnoticed for 3 hours because hygiene runs at report time and the allowlist is exact-name. Mechanism (shared `merge_ledger.py`, synced to qa):

1. `archive` moves per **file** with `os.replace` (walk `fragments/`, `briefs/` trees) and verifies after each move that the source is gone and the destination exists.
2. `archive` finishes by scanning loop dir + archive dir for ` 2.`-pattern names and re-running `hygiene_check.sh` immediately, failing loudly on either.
3. One skill line: "repos under iCloud/Dropbox can grow ` 2` duplicates during moves; archive now detects them — if it fires, resolve the sync conflict before the next round."

### B4. mutate.py: empty replacement = delete the line; implementers self-run manifests

1. `mutate.py`: `"replacement": ""` becomes valid and means "delete the matched line" (`original` + `line` still locate it). Validation distinguishes *missing key* (error) from *empty string* (deletion). This is the most natural mutant and round 1's implementer reached for it unprompted.
2. Implementer agent prompt: before returning, RUN `mutate.py` on any manifest you wrote; a manifest that cannot run is an unfinished deliverable. Also strike literal placeholders (`<scratch>`) — the prompt shows a concrete `test_cmd` example.

### B5. Closeout punt sketches get a file

The closeout implementer may not touch BACKLOG.md, so its punt sketch lived only in a commit message until the reviewer flagged "ACTION OUTSTANDING". Mechanism: closeout brief says "write punt sketches to `.review-loop/briefs/closeout-punts.md`"; the orchestrator copies them into BACKLOG.md at record time. Add the filename to the allowlist template? No — briefs are already evidence-on-disk, and the sketch reaches git via BACKLOG.md; no template change needed.

### B6. Seed-cost discipline: diff-first reading

1.25M effective on a clean 3,173-line scope, dominated by re-reading the same 200-line windows (8.2M cache-read). `read_guard` can't track windows cheaply, so this is prompt discipline: the reviewer prompt gets a "(measured: …)" rule — read the scoped diff first; open a file only to adjudicate a specific suspicion; before re-reading a window, state what you expect it to show that you didn't extract last time. Watch item, not a guard.

### B7. Sanctioned long-run pattern for the 10-minute Bash ceiling

Round 2's implementer invented a manifest split; the reviewer re-ran it whole anyway. Codify what actually worked: implementers MAY split a long mutation manifest into scratch copies for their own pre-flight, but must say so and must leave the manifest intact; reviewers run the manifest verbatim (splitting is fine if each part is verbatim rows) and may use foreground `timeout` per part. Background runs stay forbidden for agents.

### B8. Usage-verb doc line for closeout

One CONTROLS.md + SKILL.md sentence: closeout shares the last round's number — record its usage with `add-usage` (accumulate); `next-round --usage` (replace) would erase the round's figures.

---

## Part C — declined or deferred, with reasons

- **D1. Symbol/hunk-level diff→workflow mapping** (agent 2 qa #7): design-sized; `--allow-wide` already exists as the escape hatch and A9+A5 recover most of the wasted cost. → BACKLOG with the sketch. The degeneration guard itself is a settled, measured decision.
- **D2. Bending the regression writer's pbxproj boundary to relayed authorization** (agent 1 #5): declined. "The dispatch relays user authorization" is exactly the prompt-injection shape the agent boundaries exist to resist; the writer can't verify the relay. The documented implementer hand-off (A8.2) gets the same outcome inside the trust model.
- **D3. qa_metrics reopen/churn semantics** (agent 1 #6): declined. fixed→partial-as-refinement and reopen=fixed→open are settled with field evidence (HANDOFF §3); a tester-reported still-open finding being neither reopened nor new is correct. The trend under-read is cosmetic; A10.2's honest stop rows cover the report side.
- **D4. Budget stop on the effective scale** (agent 2 qa #12): declined per settled cost doctrine — budgets are deliberately on the reported scale; A10.6 documents the caveat.
- **D5. Tier 2 (sonnet ux-verifier + sonnet-pinned regression writer)**: not in this release, but note — the prerequisite ("one measured qa-loop run on the current version") is now satisfied by agent 2's 40.1M measured 0.12.0 run, and the regression writer just became the #2 cost center (7.2M). I'd write Tier 2 up as its own proposal next.
- **D6. Shipping the XCUITest driver** (agent 2 qa #2): deferred to 0.14.0, not declined — see judgment call J1. 0.13.0 ships the grant probe (A1.4) which makes the failure loud and early, and documents the driver fallback pattern.

## Part D — judgment calls flagged for Peter

- **J1. The generic XCUITest driver.** Agent 2 built a working generic driver in Causeway (`.qa-loop/driver/`: launch-with-env, tap/drag/type, rotate, identifier queries, label dumps, host-path screenshots) and reports it removed the grant problem *and* cut screenshot volume 3.4×. Shipping it with the plugin is the single highest-leverage item in either report, but I can't build it from here — the source lives in the cardgame repo. **Ask: deliver `.qa-loop/driver/` into `docs/inbox/` (or point me at the path) and I'll generalize + ship it as qa-loop-tools 0.14.0.** It's also the stepping stone HANDOFF already names for Tier 3.
- **J2. notes-rotate pin marker.** A4.3 introduces `[pin]` headings that rotation never archives. Alternative: hard-code "never archive a section named Environment". I prefer the general marker; hard-coded names rot.
- **J3. Worker names change** (A1.1: `qa-worker-<hash8>-N`). Any muscle memory / external scripts keyed on `qa-worker-N` break. The manifest remains the source of truth, and the skill already says to read it, so I think this is safe.
- **J4. `docs/inbox/loop-usage.py`.** HANDOFF says measurement scripts live in the field repos; agent 2 delivered a copy here. I propose committing it where it sits (inbox is the record of what was delivered) and NOT maintaining it — the field copies stay canonical.

## Part E — build order and validation

1. **review-loop-tools 0.13.0 first** (smaller, self-contained): B1–B8. Shared-script changes (`merge_ledger.py` archive integrity) sync to qa in the same commit per ritual §2.
2. **qa-loop-tools 0.13.0**: A1–A10. A1/A2/A4 each get scratch-dir smoke tests against the exact reported failure (per ritual §5): a two-session provision collision, a `WF-9b` fixture plan, an emoji-heavy 11KB notes file.
3. Version bumps in both `plugin.json`s; `.gitignore` allowlist template stamps only if a new durable output name appears (none currently planned — `closeout-punts.md` lives under briefs/, `findings-misc` fragments match existing patterns).
4. Standard sweep: `json.tool`, `ast.parse`, `bash -n`, no `/Users/` paths; CONTROLS.md root copy updated and re-synced to both plugins (A4.4, A8.1, A10.6, B2, B8).
5. Watch items for the next field reports: grant probe catching an ungranted worker before wave 1; a `WF-<n><letter>` workflow chunking cleanly; notes ceiling holding in bytes; `converged-in-closeout` appearing on a scoped run; archive integrity check on an iCloud repo.
