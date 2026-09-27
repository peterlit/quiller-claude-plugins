# Proposal: a frictionless feedback path from field agents to the maintainer

Written 2026-09-13. Status: **BUILT 2026-09-26** as review-loop-tools 0.15.0 /
qa-loop-tools 0.16.0 / arch-docs-tools 0.3.0 (Peter: "Go"). The text below is
the proposal as approved; "As built" at the end lists every place the build
departs from it.

## The problem, measured against the current cycle

HANDOFF §1 describes the cycle: field agents run the plugins in their own
repos, write memos, Peter delivers copies to `docs/inbox/`, the maintainer
digests them into a numbered proposal. It works — the 0.13.0 pair came out of
it — but every step costs the field agent or Peter effort that the plugin
could absorb. Evidence from the two field repos and this one:

| Friction | Evidence |
|---|---|
| No fixed shape or name for a report | Causeway holds 10 feedback files under 6 naming schemes (`qa-loop-0.12.0-feedback.md`, `review-loop-orchestrator-feedback.md`, `qa-loop-2026-09-09-decisions.md`, …); weatherapp uses `loop-tooling-feedback-<date>.md` plus separate `token-usage-<date>.md`. The digest step normalizes by hand. |
| Token accounting is re-derived per repo | `docs/inbox/loop-usage.py` docstring: "the previous two measurements were made with throwaway scratchpad scripts that did not survive the session". It hard-codes `~/.claude/projects/-Users-plit-Documents-src-cardgame`. Both agents spend a section of every report on tables this script produces. |
| Version of the running plugin is unverified | HANDOFF §1: one entire cycle was spent on "0.4.0 features are absent" from a stale install. Reports state the version from memory; `installed_plugins.json` is the ground truth nobody reads first. |
| Settled decisions get re-reported | Proposal 2026-09-09 Part C declined D3 (reopen semantics) and D4 (budget scale) against HANDOFF §3 — both were already settled with field evidence the field agents never saw. |
| Watch items never reach the field | HANDOFF §5 lists ten things "for the next field reports" to check. They live only in this repo; a field agent finds out by accident. |
| Delivery is manual | HANDOFF: "Peter delivers feedback". The field repos are on the same Mac. |
| Autonomous decisions are a separate genre | Both agents wrote a `decisions` file (HANDOFF §7 wants human-flags on autonomous choices). Nothing prompts for it or carries it with the report. |
| arch-docs-tools has no path at all | This session found three script defects in it (coverage skips `.sh`, lint rejects crow's-foot `erDiagram`, survey ignores `.md`) with nowhere to file them but the conversation. |

The precedent for the fix is `docs/plugin-feedback-conclusions-in-git.md`:
the plugin, not the host repo, owns the vocabulary of its outputs. Apply the
same rule to feedback. The design goal is that **an agent who has just
finished a loop can file a complete, versioned, measured report in one
command and under a minute of its own effort**, and that the maintainer's
first two diagnostics run before a human reads a word.

## The proposed cycle

```mermaid
sequenceDiagram
    participant L as Loop skill (report stage)
    participant F as /<plugin>:feedback
    participant Q as FIELD-QUESTIONS.md (shipped)
    participant U as loop_usage.py (shipped)
    participant H as Host repo .<loop>/feedback/
    participant D as ~/.local/share/quiller/inbox/
    participant I as tools/ingest_feedback.py (this repo)
    participant M as Maintainer session
    L->>H: run-summary.json (automatic, F1)
    L-->>F: one-line invitation, never a gate
    F->>U: effective tokens per role (--since loop start)
    F->>Q: watch questions + settled list + shipped IDs
    F->>F: ask the fixed schema, mint item IDs
    F->>H: <plugin>-<version>-<date>.md (allowlisted, committed)
    F->>D: copy of the same file
    M->>I: ingest
    I->>D: scan for new bundles
    I->>M: docs/inbox/ copies + triage digest
    M->>M: numbered proposal, Peter approves, build, release
    M->>Q: next version updates watch items + "shipped from field" IDs
```

## Part A — what ships in the plugins

### A1. The loop writes the objective half itself

At report time, `render_report.py` (shared; authored in review, mirrored to
qa per ritual §2.2) additionally writes `<loopdir>/feedback/run-summary.json`:

- `plugin`, `version` read from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`
  — the code that actually ran, not what the report author remembers — and
  the matching entry from `~/.claude/plugins/installed_plugins.json` when
  present (a mismatch means a symlinked or `--plugin-dir` install; recorded,
  not judged).
- Platform: `sw_vers`, `xcodebuild -version` (qa only), `claude --version`
  if the binary answers; every field is "unknown" rather than absent when a
  probe fails.
- Settings used, rounds, stop condition and verdict per round (from
  `verdict.json` and `rounds.md`), finding counts by severity and
  `current_status`, fix-review rejections, proposals, `(unattended default:
  …)` markers (review B2), hygiene violations, archive events, the usage
  table from `set-usage`.
- Anomalies: a new shared verb `merge_ledger.py anomaly <loopdir> "<one
  line>"` appends to `<loopdir>/feedback/anomalies.jsonl`. Scripts call it
  where they already detect a deviation and today only print: grant-probe
  failure and driver `ping` failure (Stage 0), `plan_round.py` lint
  warnings and DEGENERATED reductions, `notes-rotate` `over_ceiling`,
  `commit_guard.sh` running without `jq`, archive duplicate-name detection,
  `hygiene_check.sh` violations. Skill text tells the orchestrator to call
  it whenever it works around the plugin ("hand-built a chunk", "abandoned
  the provisioner") — the two things field reports are made of, captured at
  the moment they happen instead of reconstructed eight hours later.

`feedback/` joins the loop-dir allowlist template (`!feedback/`,
`!feedback/*.json`, `!feedback/*.jsonl`, `!feedback/*.md`) with the template
stamp bumped per ritual §2.1. It is a conclusion: small, and it is the
evidence every memo cites.

### A2. One command: `/<plugin>:feedback`

A `feedback` skill in each loop plugin (and arch-docs-tools, A6). It is the
only thing a field agent needs to know, and the loop skill's report stage
ends with the invitation: "Feedback for the plugin maintainer: run
`/qa-loop-tools:feedback` — the objective bundle takes seconds; answer only
what you observed." Not a hook, not a gate (see D2).

What it does, in order:

1. Reads `feedback/run-summary.json` and `anomalies.jsonl`. If the loop dir
   has no summary (older plugin, aborted run), it builds what it can from
   `ledger.json` and says which fields are missing.
2. Runs the shipped `loop_usage.py` (A4) with `--since` taken from the
   loop's first `rounds.md` entry and `--dir` derived from the cwd. The
   agent gets the effective-token table without writing a line.
3. Reads the shipped `FIELD-QUESTIONS.md` (A3) and asks the agent each
   watch item as a closed question: `observed / not observed / not
   applicable`, plus one line of evidence if observed.
4. Asks the fixed subjective schema, every section optional:
   - **Keep**: what worked and should not be "simplified" away.
   - **Defects**, in impact order. Each: what happened, what was expected,
     smallest repro, evidence path in the loop dir, cost (turns, tokens, or
     wall clock if known), a suggested mechanism if the agent has one.
   - **Friction**: not a defect, but cost effort (docs conflated two things,
     a verb's output was misread, a default was wrong for this repo).
   - **Decisions taken without the human**: the `decisions` genre, folded in
     — what the contract wanted a human for, what was chosen, why.
   - **Seen again**: items already listed as open or shipped in
     `FIELD-QUESTIONS.md`, by ID, with "still happens / fixed for us".
   - **Wishes**: one line each.
5. Mints an ID per item: `<plugin-short>-<version>-<yyyymmdd>-<host>-<n>`,
   e.g. `qa-0.15.0-20260920-weatherapp-3`. `<host>` is the host repo's
   directory name. Proposals and commit messages cite these instead of
   "agent 2 #7".
6. Writes one file, `<loopdir>/feedback/<plugin>-<version>-<date>.md`:
   the answers, then the run summary and usage table as fenced JSON at the
   end. Self-contained, so it survives any delivery channel. Staged by
   explicit path and committed in the host repo (conclusions in git).
7. Copies the same file to `${XDG_DATA_HOME:-~/.local/share}/quiller/inbox/<host>/`
   — the delivery step, on the same machine the maintainer works on. The
   consent store already uses the XDG family under `XDG_CONFIG_HOME`, so
   this adds no new convention. Nothing is written into any other repo.

`--quick` runs steps 1, 2, 6 and 7 only: the objective bundle, no questions.
That is the floor: a report with the version, the verdicts, the anomalies
and the cost is worth more than most prose, and it costs the agent nothing.
A free-form memo can be attached as an appendix; the schema is what ingest
parses.

### A3. The maintainer's questions ship with the plugin

New per-plugin file `FIELD-QUESTIONS.md` at the plugin root, versioned with
the code. Three sections:

- **Watch items for this version** — HANDOFF §5's watch list moves here and
  HANDOFF links to it, so there is one source. Each item is one closed
  question the feedback skill will ask.
- **Settled decisions** — HANDOFF §3 mirrored as one line each with "settled
  with field evidence; report only NEW evidence". The agent reads this before
  writing defects. Expected effect: D3/D4-style declines stop consuming
  proposal space.
- **Open and recently shipped items** — item IDs from prior field reports
  with their disposition (`shipped in 0.13.0`, `declined: <reason>`,
  `BACKLOG`). This is what closes the loop for the reporter: the agent that
  filed `qa-0.12.0-20260909-weatherapp-2` sees it landed. It also lets the
  next report say "seen again" by ID instead of re-describing.

Ritual change (HANDOFF §2.8 extended): every release updates all three
sections in the same commit. Per-plugin content, so this file is NOT
byte-synced like CONTROLS.md.

### A4. Adopt `loop_usage.py` into the plugins

`review-loop-tools/scripts/loop_usage.py`, mirrored to qa. Agent 2's script
as delivered, with the project directory derived from `--dir` (default: the
cwd encoded the way Claude Code names `~/.claude/projects/` entries) and no
hard-coded path. Same accounting as `docs/loop-token-usage.md` (effective =
input×1 + cache_read×0.1 + cache_write×2 + output×5, dedup by requestId,
images 1,600 flat) so numbers stay comparable with every prior measurement.
This reverses proposal 2026-09-09 J4 ("commit the copy, don't maintain it")
— see judgment call J3.

### A5. Nothing new for the orchestrator to remember

The loop skills gain exactly two lines: the `anomaly` verb in the Contracts
section and the one-line invitation at the end of the report stage.
CONTROLS.md gains a "Feedback" section (root copy, synced) describing the
command, the drop location, and `--quick`.

### A6. arch-docs-tools gets the same command

`/arch-docs-tools:feedback` with the same schema. Its objective half is the
survey JSON, lint and coverage numbers, diagram counts per doc, and the
deliverable split chosen; the file lands in `docs/architecture/feedback/`
and the same XDG drop. The three defects this session found would have been
its first bundle.

## Part B — what stays in this repo (not shipped)

### B1. `tools/ingest_feedback.py`

Run by the maintainer session at the start of a cycle:

1. Scans the XDG drop (and any paths given on the command line, for bundles
   delivered from another machine) for files not yet in `docs/inbox/`; copies
   them in under their own names. Peter's hand-off step disappears.
2. Prints a triage digest, which becomes the proposal's "Sources" and
   "Version check" sections:
   - reported version vs the current `plugin.json` per plugin — **stale
     install flagged before anyone reads a claim** (HANDOFF's first
     diagnostic, automated);
   - installed-vs-running mismatch (symlink or `--plugin-dir` installs);
   - watch-item answers as a table across all bundles;
   - every defect item with its ID, impact rank, and whether it has a repro
     and an evidence path (missing → flagged, since "reproduce minimally
     first" is HANDOFF's second diagnostic);
   - items whose text matches a settled-decision keyword list, tagged
     "possibly settled — verify against HANDOFF §3";
   - anomalies grouped by code across bundles (three agents hitting the same
     fallback is a defect even if nobody wrote it up);
   - usage totals per role, and the reported-vs-effective ratio per run.
3. Writes `docs/inbox/dispositions.json` skeleton entries (`id`, `status:
   "new"`) for the proposal to fill in.

### B2. Dispositions are recorded once and flow forward

When a proposal is approved, its item dispositions go into
`docs/inbox/dispositions.json` (`shipped: <version>` / `declined: <reason>`
/ `backlog`). A small `tools/render_field_questions.py` regenerates the
"Open and recently shipped" section of each plugin's `FIELD-QUESTIONS.md`
from it, so the file the field agent reads is never hand-maintained. Commit
messages keep carrying the reasoning (the decision log ritual is unchanged).

## Part C — declined, with reasons

- **D1. GitHub Issues as the channel.** `gh` is not installed (HANDOFF §6),
  field agents would need credentials, and an issue is an outward-facing
  publish of a report that may quote app internals. A single self-contained
  file plus a same-machine drop covers both agents today; if a field agent
  is ever off-machine, the file is still the unit and can be sent by any
  means, then ingested by path.
- **D2. Auto-filing at loop end via a Stop hook.** Hooks are zero-token
  enforcement; feedback needs judgment, and forcing questions at the end of
  an eight-hour run is the opposite of frictionless. The objective half is
  automatic (A1); the subjective half is a one-line invitation.
- **D3. Free-form memos as the primary format.** The ten existing memos
  already converge on the same sections (keep / defects in impact order /
  cost / decisions). The schema codifies practice; memos remain allowed as
  an appendix.
- **D4. A shared database or dashboard.** Two field agents and one
  maintainer; files in git and a directory scan are the right size.
- **D5. Writing into the marketplace checkout from a field session.** A
  session in one repo writing into another repo's tree is exactly the kind
  of cross-boundary write `commit_guard` exists to prevent. The XDG drop is
  outside every repo; ingest is the only thing that writes into this one.
- **D6. Making feedback part of convergence or the report's WATCH LIST.**
  The report is for the app owner; feedback is for the plugin maintainer.
  Mixing them would put plugin bugs in front of the wrong reader.

## Part D — judgment calls flagged for Peter

**All five RESOLVED 2026-09-20 (interviewed), each on the recommended
option:** J1 XDG data dir; J2 `feedback/` is an allowlisted conclusion; J3
adopt and mirror `loop_usage.py`; J4 IDs include the host name; J5 the
shipped `FIELD-QUESTIONS.md` is the watch list's source of truth. Build
awaits the explicit "go".

- **J1. Drop location.** `${XDG_DATA_HOME:-~/.local/share}/quiller/inbox/`
  over `~/.claude/quiller-inbox/` or the field repo alone. Chosen for
  consistency with the consent store; the alternative is discoverable from
  a Claude session with no XDG knowledge. Either works.
- **J2. `feedback/` as a conclusion.** Allowlisted and committed in the host
  repo. It is small, and the memo cites it. The alternative (scratch, on
  disk only) means the host repo's history loses the evidence for its own
  plugin feedback.
- **J3. Adopting `loop_usage.py`.** Reverses 2026-09-09 J4. Reason: the
  measurement is the most expensive part of every report and has now been
  reimplemented by both agents from a docstring; shipping it makes numbers
  comparable across repos and versions. Cost: one more mirrored script.
- **J4. ID scheme includes the host name.** Makes IDs readable in commit
  messages (`qa-0.15.0-20260920-weatherapp-3`) at the cost of leaking the
  host repo's directory name into this repo's history, which the inbox
  files already do.
- **J5. Watch items move out of HANDOFF.** HANDOFF §5 keeps a pointer, the
  content lives in each plugin's `FIELD-QUESTIONS.md`. One source, but a
  maintainer reading HANDOFF alone no longer sees the list inline.

## Part E — build order and validation

1. **A3 + A1** first, as `review-loop-tools 0.14.0` / `qa-loop-tools 0.15.0`:
   `FIELD-QUESTIONS.md` seeded from HANDOFF §3 and §5, `run-summary.json`,
   the `anomaly` verb, the allowlist template bump, the two skill lines.
   Shared-script sync per ritual §2.2; CONTROLS.md "Feedback" section synced.
2. **A2 + A4**: the `feedback` skill and `loop_usage.py` in both loop
   plugins. Smoke test per ritual §5 in a scratch loop dir: `--quick` on a
   dir with no summary, a full run answering three watch items, and a run
   where `~/.claude/plugins/installed_plugins.json` disagrees with
   `plugin.json`.
3. **A6**: `arch-docs-tools 0.2.0`.
4. **B1 + B2** in this repo's `tools/`, plus `docs/inbox/dispositions.json`
   seeded with the 2026-09-09 items so the first regenerated
   `FIELD-QUESTIONS.md` already tells the field what shipped.
5. HANDOFF: §1 cadence rewritten around ingest, §2 rituals 1, 2, 8 amended,
   §5 watch list replaced by the pointer — same commit as step 1.
6. Standard sweep: `json.tool`, `ast.parse`, `bash -n`, no `/Users/` paths.

First measurement of the process itself: the next two field reports should
arrive by ingest with no hand delivery, state the running version in their
first ten lines, answer every watch item, and contain zero items that
ingest tags as settled. If any of those four fails, that is the first
feedback on the feedback process.

---

## Revision 2026-09-20 — what the 2026-09-13/19 reports change

Four files arrived by hand delivery on 2026-09-20 (three review-loop 0.13.0
reports, one qa decisions record). Read against the design above, they
confirm most of it and change five things.

**Confirmed.** All three review reports state the running version in their
first three lines and it is current. Both agents converged on the same
sections unprompted (usage table, what worked, defects in impact order,
recommendations, judgment calls). Agent 1's 2026-09-19 report cites its own
2026-09-13 workaround ("as the 2026-09-13 report suggested") — exactly the
"seen again by ID" case A2.4 provides for. The qa decisions record arrived
eleven days after the run it describes: the decisions section belongs in
the bundle written at run end, as A2.4 says, or it is written from memory
or not at all.

**Changed:**

1. **Cross-report duplication is the ingest's main job, not version
   checking.** Four defects were filed independently in all three reports
   (ollama 0/N kept, no per-lane rerun, the `:dispatched` marker, no lane
   usage). B1 gains a "same defect, N reports" grouping keyed on the
   anomaly code where one exists and on a normalized region+symptom
   otherwise; the proposal cites the group, not three items.
2. **Two schema sections added to A2.4.** *Host-repo recommendations*
   (agent 1's "Recommendations for this repo": which lanes to keep, session
   hygiene) — actions for the host, not the plugin, and today they sit in
   the same list as defects. *Environment and harness artifacts* (agent 1's
   "Environment notes (not the plugin's fault)": `NODE_OPTIONS`, MCP tools
   not loaded, a scheme that refuses UI tests). This is HANDOFF's second
   diagnostic ("distinguish harness artifacts from plugin bugs") made a
   field the reporter fills, so triage starts with the reporter's own call.
3. **Per-dispatch wall-clock and panel lane telemetry in `run-summary.json`
   (A1).** Agent 1 hand-timed every dispatch (`Wall` column) both runs;
   agent 2 measured effective tokens instead. The two scales cannot be
   compared. `dispatch_stamp.sh` already fires at every dispatch and the
   SubagentStop hook at every return: they record `(phase, start, end)` to
   `feedback/dispatches.jsonl` at no token cost, and panel `run` records
   `elapsed_s` per lane (proposal 2026-09-20 A12). The bundle then carries
   wall-clock by construction and effective tokens from `loop_usage.py`.
4. **Anomaly codes get a first vocabulary from these reports** (A1): lane
   `skipped`/`error`/`timeout`/`cached`/`capped`, `dispatch-count-mismatch`
   (counter left non-zero at phase end), `session-ok-created`,
   `read-guard-denied`, `archive-late-duplicates`, `mutate-baseline-red`,
   `mutate-dirty-refused`, `usage-repeat-notification`. Each is a place the
   0.14.0 scripts already decide something; the verb call is one line
   each.
5. **The recommended item ID is adopted retroactively** in
   `docs/proposal-2026-09-20-panel-field-reports.md` (e.g.
   `rl-0.13.0-20260919-weatherapp-3`) so the first `FIELD-QUESTIONS.md`
   dispositions list can be generated from that proposal without renaming.

Unchanged: the delivery drop, the one-command skill, `--quick`, and every
decline in Part C. Judgment calls J1–J5 stand and are put to Peter together
with the 2026-09-20 proposal's.

---

## As built — 2026-09-26

Parts A and B were built in full, with the 2026-09-20 revision. Where the
build departs from the text above:

| Proposal | As built | Why |
|---|---|---|
| Ships as review 0.14.0 / qa 0.15.0 | review **0.15.0** / qa **0.16.0** / arch-docs **0.3.0** | 0.14.0/0.15.0 went to the panel field reports first. |
| `render_report.py` writes the summary | `run_summary.py` builds it; `render_report.py` calls it in a guarded block | Keeps `render_report.py`'s review/qa divergence panel-only, and lets `feedback.py` build a summary for a loop that never reached the report stage. A summary failure can never fail a report. |
| `merge_ledger.py anomaly` is the recorder | `field_log.py` is; the verb delegates to it | Hooks and qa-/review-only scripts need it without importing the ledger code. One module also owns dispatch timing. |
| The skill asks questions and mints ids | `feedback.py scaffold` writes a draft, the agent edits it, `feedback.py finalize` validates, mints ids, appends the JSON and copies to the drop; `quick` does both | Everything mechanical is a script (HANDOFF section 3, "the orchestrator is plumbing"). The skill is 60 lines. |
| Watch items are numbered | Slugs: `w-dispatch-overlap`, `s-set-usage-replaces` | An item that stays on watch for three releases keeps its name; numbers would shift. |
| Usage window from "the loop's first rounds.md entry" | From the ledger's creation and the first recorded dispatch, to the report | `rounds.md` rows carry no timestamps — the 2026-09-20 weatherapp report hit exactly this. |
| Summary lists findings by severity and `current_status` | COUNTS only; no finding id, claim, region or evidence; hygiene and guard anomalies record the KIND, never a name or command; paths folded to `~` | The file leaves the host repo (the concern behind decline D1). The selftest plants a marker string in a finding and asserts it reaches neither the summary nor the report. |
| Ingest copies reports "under their own names" into `docs/inbox/` | Into `docs/inbox/<host>/` | Two hosts filing the same plugin version on the same day produce the same file name. |
| Anomaly code `session-ok-created` | `session-gate-blocked`; each dispatch row also records the session transcript's size | Creating `.session-ok` under the threshold is the normal path. The block is the event, and session size per dispatch is the number behind it. |
| Lane codes `skipped`/`error`/`timeout`/`cached`/`capped` | `lane-skipped`, `lane-error`, … plus `lane-disabled-by-precision` | One flat vocabulary across scripts. |
| Grant-probe and driver-`ping` failures recorded by scripts | Recorded by the orchestrator (`--code grant-probe-failed`, `driver-ping-failed`); the qa skill says when | No script performs either probe: the grant probe is a micro-dispatch, the ping is a command the orchestrator runs. |
| — | Added codes: `commit-guard-denied`, `mutate-allow-dirty`, `plan-unchunked`, `model-fallback` | Each is a decision a shipped script or the skill already makes. |
| — | `feedback.py` adds the three `feedback/` rules to an OLDER plugin-managed allowlist | Every loop bootstrapped before this release ignores `feedback/`; the first report from the field would have been filed into a directory git cannot see. A host-owned `.gitignore` is never touched. |
| — | Feedback filed after a loop was archived reports on the newest archive | `feedback/` rides with its loop; the next loop's Setup archives before anyone may have filed. |
| — | `session_guard.sh` stands down for `/<plugin>:feedback` and `:controls` prompts | Both name the plugin, neither starts a loop, and feedback is filed from the session the loop just ran in. |
| — | `arch_summary.py start` at Stage 1 | arch-docs has no loop state to date a run from. |
| — | `coverage_check.py` skips `<docs-dir>/feedback/` | A field report that names a source file must not count as documentation coverage. |

Not built, deliberately:

- **Dispatch timing for arch-docs-tools.** It has no hooks and no phase
  marker; its summary carries the run's wall-clock only.
- **The three arch-docs script defects** named in the problem table
  (coverage skips `.sh`, survey ignores `.md`; the erDiagram lint false
  positive was fixed in 0.2.0). They were never filed; they are now watch
  item `w-coverage-blind-spot` and a BACKLOG line, waiting for a report
  that measures them.
- **Pruning the drop.** Ingest reads it and never deletes from it.

Validation as executed: `feedback_selftest.py` 94 checks, run against both
loop plugins; `hooks_selftest.py` 19; `panel_selftest.py` 137; the usage
script reproduced `docs/inbox/loop-usage.py`'s total to the token on the
weatherapp project directory (433 transcripts, 509,373,423 effective) and
reproduced the nine per-dispatch figures the 2026-09-20 weatherapp report
assembled by hand (subagents 2,447,428). The three smoke cases from Part E
step 2 ran in scratch directories: a quick bundle on a loop with no
summary, a full report answering every watch item, and a run whose
`installed_plugins.json` disagrees with `plugin.json`.
