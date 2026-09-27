# Backlog

## Found by the documenters, 2026-09-27 (regeneration against 0.16.0 / 0.17.0 / 0.3.1)

The documenters verify claims against the code and report what they find.
None of the code items below has been through a proposal; each names how
it was established. Verify before proposing.

Fixed in review-loop-tools 0.16.1: `skeptical-reviewer.md` told the
reviewer two things about long manifests (0.16.0's A5 replaced the
matching paragraph in `implementer.md` and missed the reviewer's).

Code, reported as reproduced by running the scripts:

- **`union_evidence()` returns `{}` for list-shaped evidence**, so a merge
  that touches a review finding wipes its `file:line` evidence list. 18 of
  27 findings in this repo's own ledger have empty evidence. The qa loop's
  evidence is dict-shaped and unaffected.
- **`commit_guard.sh` without `jq` fails open on the staging rules and
  CLOSED on everything else**: the env-knob checks (`REVIEW_LOOP_TEST_CMD`,
  `REVIEW_LOOP_MAX_DIFF`) run on every shell call because the command is
  unreadable, and they are not gated on a live loop. A plain `ls` ran the
  test command and was blocked.
- **`subagent_guard.sh` decrements the live count before it validates.** If
  the host re-fires SubagentStop after a block (an inference), a refused
  fragment costs two counts — more likely with qa's parallel testers.
- **`mermaid_lint.py` gaps**: quoted `actor` aliases, semicolons in
  `loop`/`alt`/`opt` labels and unquoted diamond labels are not flagged; a
  cylinder node `[(Database)]` is a false positive.
- **`feedback.py` and `arch_summary.py` fall back to different repo roots
  outside git.** `feedback.py` takes the parent of the given directory, so
  for `docs/architecture` the host becomes `docs`.

Code, established by reading only:

- **A detached panel run that exits early never writes its summary**, so
  `panel_review.py wait` exits 3 indefinitely. `mutate.py` had the same
  flaw and 0.16.0 fixed it there.
- **The session-size gate runs only on a bare-phase dispatch**; a first
  dispatch under `:waiting:` or `:dispatched` is never gated.
- **`QA_LOOP_UNATTENDED` records nothing in the qa loop.** Only
  `next-round` writes the rounds.md note, and the qa skill never calls
  `next-round` (nor are `round_end_shas` written). The qa skill and
  CONTROLS both promise the record.
- **Ingest cannot show an arch-docs report's numbers.** The digest reads
  keys the arch-docs summary lacks (rounds, stop, reported usage); its
  `objective` block is never printed.
- **Ingest drops items from a report whose version is `unknown`**: the id
  pattern requires a numeric version.
- **Seven settled-decision ids have no ingest pattern**
  (`s-simulator-discipline` and all six arch-docs ids).
- **Feedback measures no tokens when the session was started from a path
  other than the repo root** (the transcript directory is derived from
  the git top-level; there is no override through `feedback.py`).
- **`mutate.py` hard-codes `.review-loop`** for its telemetry.

Tests and documentation:

- **No automated byte-identity check for the mirrored scripts.** Only
  `CONTROLS.md` has one (in `panel_selftest.py`); hook and script identity
  rests on a manual `cmp`.
- **The arch-docs feedback path and every qa-only script, and the driver,
  have no automated test.**
- **`qa-loop-tools/README.md` is stale in seven places** (listed in section
  6.5 of `docs/architecture/qa-loop-tools.md`); `review-loop-tools/README.md`
  in two.
- **HANDOFF section 3's fourteen settled decisions carry no ids**, while
  the three FIELD-QUESTIONS files carry `s-*` ids for theirs.
- **`docs/proposal-multi-provider-review-panel.md` still reads "awaiting
  commit approval"**; it shipped as 0.11.0.
- **The feedback path has not yet carried a real report.** The drop does
  not exist on this machine; the one report in `docs/inbox/weatherapp/`
  predates the command.

## From the agent-feedback process build (review 0.15.0 / qa 0.16.0 / arch-docs 0.3.0)

- **SessionStart duplicate scan** (declined as C6 in
  `docs/proposal-2026-09-27-weatherapp-0.14.0-report.md`). Comes back only
  if days-later renames are reported WITHOUT a machine event behind them;
  the one report so far traced to an accidental iCloud Drive off/on.
- **Hook ordering inside one batch of tool calls is unverified.** 0.16.0
  no longer depends on it (both orders are tested), but whether the
  dispatch hook runs before or after a same-batch Bash call, and whether a
  hand-back reliably precedes its token notification, are each known from
  one field run. Worth a watch-item answer before anything else is built
  on either.
- **`suites_note` is free text.** A closeout reviewer can satisfy the guard
  with `"suites": {}` and any note. If empty-with-note shows up on repos
  that plainly have test targets, tighten it.
- **cardgame's loop-dir `.gitignore` is host-owned** (its first line lacks
  "Managed by"), so the feedback command will not add the `feedback/`
  rules there and reports filed in that repo are not versioned — the drop
  copy is the delivery. Host-side fix: add `!**/feedback/*.json`,
  `!**/feedback/*.jsonl`, `!**/feedback/*.md` to
  `cardgame/.review-loop/.gitignore`. weatherapp's is plugin-managed
  (v0.12.0) and upgrades itself on the first report.
- **arch-docs coverage and survey disagree on what a source file is.**
  `repo_survey.py` counts `.sh`, `.sql`, `.css`, `.html` and `.h`;
  `coverage_check.py` counts none of them, and neither counts `.md` — so a
  repo made of shell and Markdown (this one) reports coverage over a
  fraction of what it surveyed. Found while writing the feedback proposal,
  never filed from the field; watch item `w-coverage-blind-spot` asks for
  a measurement before anything changes.
- **A report from another machine.** The drop is machine-local. The report
  file is self-contained and `ingest_feedback.py <path>` takes it, but
  nothing moves it; if a field agent ever runs off this Mac, decide the
  channel then (the proposal declined GitHub Issues for today's setup).
- **The drop is never pruned.** `~/.local/share/quiller/inbox/` grows by
  one small file per report; ingest skips what `docs/inbox/` already has.
- **Ingest's settled-decision patterns are hand-maintained** (`SETTLED` in
  `tools/ingest_feedback.py`). A settled decision added to HANDOFF section 3
  and FIELD-QUESTIONS needs a pattern there too, or its re-reports go
  untagged. Generating the patterns from FIELD-QUESTIONS would need a
  keyword line per decision.
- **No dispatch timing for arch-docs-tools** (it has no hooks); its run
  summary carries the run's wall-clock only.

## From the 2026-09-13/19/20 panel field reports (shipped as review 0.14.0 / qa 0.15.0)

- **Synced-volume scratch isolation** (deferred as C7 in
  `docs/proposal-2026-09-20-panel-field-reports.md`). `archive` now re-checks
  for ` 2`-suffixed duplicates after a 3 s settle, but a file provider can
  re-stamp later still. If duplicates recur on iCloud/Dropbox repos after
  0.14.0, the next step is a `.nosync`-suffixed scratch area for
  `evidence/`, `fragments/` and `briefs/` (macOS skips `*.nosync` dirs) —
  design-sized: every path the skills and hooks name changes.
- **Codex/gemini token capture is passive.** `run_lane` records whatever
  usage the CLI prints; codex on a ChatGPT login prints nothing. If a
  documented `--json` event stream carries `usage`, add the flag and parse
  it — untested here because no real CLI run was possible in the build
  session.
- **Ollama `qwen3-coder:30b` is 0/40 in the field.** Host config, not ours;
  the precision cap and cross-loop disable now act on it automatically.
  Worth a CONTROLS note recommending a lower `max_diff_tokens` and a
  severity cap before anyone re-enables a local lane.

## From the 2026-09-09 field reports (shipped as review 0.13.0 / qa 0.13.0+0.14.0)

- **Symbol/hunk-level diff→workflow mapping** (agent 2 qa #7, deferred as
  design-sized). `plan_round.py`'s `paths()` mapping is file-prefix-based, so
  an app with few large view files maps most workflows to every diff and
  every targeted pass degenerates to findings+smoke. Sketch: map changed
  HUNKS to enclosing symbols (`git diff -W` or ctags), let `paths(WF-n)`
  optionally name symbols (`Shared/Cart.swift#CartModel`), intersect at
  symbol level, keep file-prefix as fallback. `--allow-wide` and the A9 perf
  gating recover most of the waste meanwhile; build this only if targeted
  passes still degenerate routinely after 0.13.0.
- **Tier 2 (sonnet ux-verifier + sonnet regression writer)** — prerequisite
  now satisfied: agent 2's measured 40.1M-effective 0.12.0 run is the
  baseline (HANDOFF §5 wanted one before building). The regression writer is
  now the #2 cost center (7.2M for 49 tests). Needs its own proposal.

## From review loop 2026-09-12/13 (REVIEW.md seed — panel hardening, v0.12.0)

- **XDG consent store can still be relocated INTO the checkout by an absolute path** (`security/panel_review.py:consent-xdg-inside-checkout`, MAJOR, **FIXED post-closeout**). `consent_path()` now rejects an `XDG_CONFIG_HOME` whose realpath lies inside the reviewed repo (`dirname(realpath(loop))` — no git dependence), falling back to `~/.config` with a stderr warning; realpath on both sides catches symlink aliases. Selftest fixtures moved the hermetic XDG override to a sibling tempdir, plus attack-shaped checks: bundle shipping a pre-armed `.config/…/consent/<hash>.json` inside the checkout fails closed end to end, and a symlinked-into-repo base is rejected. Honest residual: repo-shipped env can still point the base at an attacker-controlled path *outside* the repo, but that requires the attacker to already control another location on the machine — outside the "repo carries the payload" threat model this store closes. Follow-up pass also closed the sibling vector through the `~/.config` **fallback** (repo-shipped `HOME` — demonstrated live): the fallback base gets the same containment check, and with nowhere trustworthy left `consent_path()` returns None → hard fail-closed, warning names HOME, consent-path verb refuses with a fix hint. Same pass: `remote_lanes_approved` grants only as JSON `true` (truthy non-booleans warn and gate closed), and the repo's own tracked legacy `.review-loop/panel-consent.json` was removed. Remaining hardening idea (backlog-grade, not built): the containment comparison is lexical `commonpath` — case-insensitive/Unicode-normalizing filesystems (APFS) could beat it with a case-twiddled base path; robust fix is an inode walk (`st_dev`/`st_ino` from the base's deepest existing ancestor vs the repo root).
- **Missing/blank/non-string severity still silently dropped** (`correctness/panel_review.py:severity-missing-still-dropped`, minor, **FIXED post-closeout**). `sanitize()` now clamps *every* out-of-vocabulary severity — unknown string, blank, missing key, non-string/unhashable — to minor; severity never gates a candidate with claim+evidence intact (the verifier adjudicates severity anyway). Selftest updated accordingly.
- **`os.killpg` on cmd-lane timeout raises AttributeError on Windows** (`panel:codex`/gemini fold-in, minor, open). Not in the suppress list; run_lane's broad handler contains it to one lane, but the lane reports a confusing error instead of a clean timeout on Windows.
- **`run()`'s no-panel/unreadable-panel output lacks a `lanes` key** (fold-in, minor, open). Three-way schema inconsistency between run()'s error shapes and its success shape; no in-repo caller crashes today, but external parsers of run output may.
- **Consent key case-fold on APFS** (wontfix, documented). Differently-cased spellings of the same loop dir hash to different consent keys → spurious fail-closed consent misses on case-insensitive filesystems. Deliberately NOT case-folded: folding would grant cross-loop consent on case-sensitive filesystems; a correct fix needs per-path FS case-sensitivity probing (design-sized).
- **Lane wall-time can reach timeout + min(timeout,10)** (noted, unfiled). ollama_model_ctx's metadata call budget is additive to the generate budget.

## From review loop 2026-09-09 (scope pre-multi-provider-panel..HEAD — multi-provider panel, v0.11.0)

- **probe smoke still misses the configured model on FIRST setup** (`minor/panel_review.py:probe-smoke-diverges-from-run`, partial after closeout). The bare-`probe --smoke` default path fix covers re-probes, but SKILL.md's setup order runs probe *before* panel.json is written, so the model the human just chose is never smoked on first setup. Reviewer's note: reorder the setup recipe (write panel.json, then smoke) or add a post-config smoke step.
- **Script-content pinning for cmd lanes** (design-sized, sketched in closeout). `cmd_lanes_approved` binds the invocation string only: approving `bash ./lane.sh` does not pin lane.sh's contents. Sketch: extend the machine-local consent file's entries to optional objects `{"cmd": "...", "files": {"tools/lane.sh": "<sha256>"}}` and have `cmd_approved()` verify file digests before executing; needs a consent-prompt UX change and a re-prompt path.
- **qa-loop-tools/CONTROLS.md documents a panel qa-loop doesn't ship** (convention issue). The byte-identical sync forces the `[review]`-tagged panel section into the qa copy while `qa-loop-tools/scripts/` has no panel_review.py and its merge_ledger.py lacks panel-tally. Either port the panel to qa or add per-plugin section filtering to the sync.
- **probe marks `configured: true` by lane NAME, not type** (pre-existing minor, untouched). A codex lane named `cx` won't get the flag in probe output.
