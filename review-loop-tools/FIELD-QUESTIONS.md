# Field questions — review-loop-tools

What the maintainer wants to know from a run of THIS version, what is
already decided, and what happened to earlier reports. `/review-loop-tools:feedback`
reads this file: it asks the watch items as closed questions and expects
you to have read the other two sections before writing a defect.

Versioned with the code: every release updates all three sections in the
same commit. The third section is generated — do not edit it by hand.

## Watch items for this version

Answer each `observed`, `not observed`, or `n/a` (the run never reached the
situation). One line of evidence when observed: a path in the loop dir, a
round number, a count.

- **w-dispatch-overlap** — With two agents live at once (a panel-verifier beside an implementer), did `:dispatched` stay set until the LAST one returned, with no hand-written `:waiting:` and no Stop-hook block on an ordinary turn?
- **w-lane-failover** — Did a panel lane hit a quota or model-unavailable error and fail over to the next entry in its `model` list, with `model_used` recorded in the run JSON?
- **w-precision-cap** — Did the final-pass cap fire on a lane that kept 0 of >=5 at seed (`cap` in its result), or did the probe report a lane `disabled-by-precision`?
- **w-excluded-trailer** — With pathspec excludes in the scope, did any panel candidate or chair finding still claim an excluded file "was not updated"?
- **w-empty-diff-refused** — Did `panel_review.py run` refuse an empty diff (exit 2) in a real run?
- **w-duplicate-of** — Did the final-pass verifier mark any re-filed finding `duplicate_of`, or write `notes_for_chair` that the chair acted on?
- **w-late-duplicates** — On a synced volume, did `archive` report `duplicates_detected_late` above 0, or did a ` 2`-suffixed name appear after archive and hygiene had both said clean?
- **w-suites-table** — Did the report's Closeout section carry the structured suite table (Executed / Failed / Skipped)?
- **w-mutate-refusals** — Did `mutate.py` refuse a red baseline or a dirty tree, and was `--allow-dirty` used for anything but a deliberate pre-commit check?
- **w-lane-tokens** — Did any CLI lane (codex, gemini) report token counts in its run JSON?
- **w-converged-in-closeout** — Did a run that stopped `thrashing_soft` or at the backstop headline `converged-in-closeout` after closeout left 0 blockers and majors open?
- **w-closeout-verify** — Did a closeout `verify_cmd` omit a test target its diff touched, and was the CHANGES block rejected for it?
- **w-run-summary** — Did the report stage write `feedback/run-summary.json` without being asked, and does its `plugin.version` match what you believe ran?
- **w-dispatch-timing** — Does the summary's `dispatches` section account for every dispatch you made (`unreturned` and `unmatched_returns` both 0)?
- **w-anomaly-verb** — Did you record a workaround with `merge_ledger.py anomaly` at the moment it happened, and did any script-recorded anomaly surprise you?

## Settled decisions — report only NEW evidence

Each of these was litigated with field evidence. A report that re-raises one
without new numbers costs a proposal slot and is declined. If your run
produced evidence that contradicts one, that IS worth a defect — cite the
decision's id.

- **s-seed-round-0** — The seed merges as round 0. A seed merged as round 1 poisons the net metric and makes a converging run look like thrashing.
- **s-set-usage-replaces** — `set-usage` and `next-round --usage` REPLACE a (round, role) figure; `add-usage` accumulates. Accumulate-only once inflated a budget readout by 89%.
- **s-reported-token-scale** — Budgets and the BUDGET stop use the harness-REPORTED scale, which sits 4-7x below billed effective tokens for code loops. It is a guardrail on runaway loops, not a dollar ceiling.
- **s-reopen-semantics** — Reopen means fixed->open only; fixed->partial is refinement. A converging series (every open finding introduced_by_fix, worst severity non-increasing, nothing reopened) is exempt from the churn signal.
- **s-archive-naming** — Archive directories are named by the ARCHIVED loop's scope sha, not HEAD at archive time.
- **s-minors-by-risk** — `fix_risk` minors ride round briefs; plain minors wait for the one closeout pass.
- **s-closeout-discipline** — Closeout is the smallest correct fix, its `verify_cmd` must RUN every touched test target, and an introduced_by_fix blocker earns exactly one extra dispatch before the report headlines "done-but-red".
- **s-model-pins** — Chair `opus`, verifier `sonnet`, implementer `inherit`. The point is diversity: pins stay distinct from each other and from the session model, and a dispatch never overrides one.
- **s-mutations-through-scripts** — Every ledger, report and planning mutation goes through the scripts. An orchestrator hand-editing `ledger.json` or `rounds.md` is a skill-wording bug to report, not a shortcut to bless.
- **s-do-not-cut** — Reviewer verification depth, mutation re-runs and extended thinking are not cost levers: cost is turns x context, and cache reads are 98-99% of raw tokens.
- **s-lane-failures-soft** — A failed panel lane is skipped with disclosure and exit 0; it never blocks a round. Non-zero exit from `run` on lane failure was declined.
- **s-dispatch-counter** — Live dispatches are COUNTED in `briefs/.dispatched`; keying the marker by agent name was declined.

## Open and recently shipped items

<!-- BEGIN generated by tools/render_field_questions.py — do not edit -->
**Reported, not yet decided**

- `rl-0.14.0-20260920-weatherapp-0` — iCloud renamed committed archive conclusions to ' 2' names days after the archive; hygiene does not scan archive/ for a missing plain name
- `rl-0.14.0-20260920-weatherapp-1` — briefs/.dispatched read 0 with an agent live after a phase write and an Agent dispatch in one parallel batch; mark then stripped
- `rl-0.14.0-20260920-weatherapp-2` — rounds.md and verdict.json token figures miss usage recorded after next-round; trend table shows implementer-only tokens
- `rl-0.14.0-20260920-weatherapp-3` — Implementers resolved mutate.py themselves and ran the stale 0.13.0 cache copy; implementer.md names no path
- `rl-0.14.0-20260920-weatherapp-4` — Manifests over ~4 mutants exceed the Bash tool's 10-minute ceiling; agents split them into scratch copies
- `rl-0.14.0-20260920-weatherapp-5` — The closeout suites table did not appear: the reviewer's fragment carried no suites key

**Shipped**

- `rl-0.13.0-20260913-cardgame-1` — shipped in 0.14.0 — Gemini free-tier key: quota deaths, no tier in probe, no model fallback, note truncated _(Not shipped: Gemini tier detection via Google's models endpoint (declined, C3).)_
- `rl-0.13.0-20260913-cardgame-2` — shipped in 0.14.0 — No single-lane rerun; retrying one lane meant hand-editing tracked panel.json
- `rl-0.13.0-20260913-cardgame-3` — shipped in 0.14.0 — Lane timeouts exceed the Bash tool ceiling; needs --detach and wait
- `rl-0.13.0-20260913-cardgame-4` — shipped in 0.14.0 — read_guard false positive on heredoc content containing an xcodebuild string
- `rl-0.13.0-20260913-cardgame-5` — shipped in 0.14.0 — qwen3-coder lane filed 20 candidates, 0 kept; wants pre-filters and a kept-rate cap _(Not shipped: the claim-identifier pre-filter (declined as fuzzy, C5).)_
- `rl-0.13.0-20260913-cardgame-6` — shipped in 0.14.0 — Final-pass lanes re-file the ledger; verifier needs open ids and duplicate_of
- `rl-0.13.0-20260913-cardgame-7` — shipped in 0.14.0 — Verifier's side-observations have no channel to the chair (notes_for_chair)
- `rl-0.13.0-20260913-cardgame-8` — shipped in 0.14.0 — Two different rules for which implementer may touch BACKLOG.md
- `rl-0.13.0-20260913-cardgame-9` — shipped in 0.14.0 — Report's round-1 watch candidate lumps the closeout commit into its diff range
- `rl-0.13.0-20260913-cardgame-10` — shipped in 0.14.0 — Codex on ChatGPT login exposes no usage; capture token counts if the CLI prints them _(Capture is passive: codex on a ChatGPT login prints no usage. Estimating was declined (C8); active capture is in BACKLOG.)_
- `rl-0.13.0-20260913-weatherapp-1` — shipped in 0.14.0 — Consent silently lost across plugin upgrade while probe --smoke reported lanes ok
- `rl-0.13.0-20260913-weatherapp-2` — shipped in 0.14.0 — :dispatched suffix stripped by another agent's SubagentStop while a dispatch is live
- `rl-0.13.0-20260913-weatherapp-3` — shipped in 0.14.0 — Panel run reports no usage: no per-lane wall-clock, no ollama token counts _(Codex/gemini token capture is passive (whatever the CLI prints); estimating was declined (C8), active capture is in BACKLOG.)_
- `rl-0.13.0-20260913-weatherapp-4` — shipped in 0.14.0 — panel-tally replaces ledger panel tallies, losing a round's first batch
- `rl-0.13.0-20260913-weatherapp-5` — shipped in 0.14.0 — Range + pathspec quoting differs between the scope and diff verbs
- `rl-0.13.0-20260913-weatherapp-6` — shipped in 0.14.0 — mutate.py trusts test_cmd: no baseline run, no dirty-tree check vs HEAD worktree _(Not shipped: a deliberately-broken sentinel mutant (declined, C2) — the baseline run plus a control mutant covers it.)_
- `rl-0.13.0-20260913-weatherapp-7` — shipped in 0.14.0 — probe --smoke does not smoke the ollama lane (lists models only)
- `rl-0.13.0-20260913-weatherapp-8` — shipped in 0.14.0 — Skill silent on panel-to-chair dedupe and adding sources to an existing finding id
- `rl-0.13.0-20260913-weatherapp-9` — shipped in 0.14.0 — Session-size guard fires on every turn with no acknowledgment after .session-ok
- `rl-0.13.0-20260913-weatherapp-10` — shipped in 0.14.0 — Gemini model choice is quota-bound; probe should report quota state
- `rl-0.13.0-20260919-weatherapp-1` — shipped in 0.14.0 — Panel lanes inherit a poisoned NODE_OPTIONS and die silently; run exits 0 _(Not shipped: a non-zero exit from `run` when a lane fails (declined, C1) — lane failures stay soft, with a loud stderr banner.)_
- `rl-0.13.0-20260919-weatherapp-2` — shipped in 0.14.0 — No per-lane rerun; recovering two lanes overwrote the good lane's candidates
- `rl-0.13.0-20260919-weatherapp-3` — shipped in 0.14.0 — iCloud minted ' 2' duplicates inside the archive after archive and hygiene said clean _(Not shipped: a guarantee against later provider re-stamping (deferred, C7) — synced-volume scratch isolation is in BACKLOG.)_
- `rl-0.13.0-20260919-weatherapp-4` — shipped in 0.14.0 — Phase-marker suffix stripped with overlapping dispatches (recurring)
- `rl-0.13.0-20260919-weatherapp-5` — shipped in 0.14.0 — mutate.py has no per-mutant test command, so every mutant pays the UI suite
- `rl-0.13.0-20260919-weatherapp-6` — shipped in 0.14.0 — Closeout reviewer's task notified twice; usage could be double-counted
- `rl-0.13.0-20260919-weatherapp-7` — shipped in 0.14.0 — Verifier's kept and panel-tally's kept disagree by one (demoted duplicate counted)
- `rl-0.13.0-20260920-cardgame-1` — shipped in 0.14.0 — Pathspec excludes blind the panel: lanes file 'was not updated' on hidden files
- `rl-0.13.0-20260920-cardgame-2` — shipped in 0.14.0 — panel run accepted an empty diff and reported success; diff did not fail on git error
- `rl-0.13.0-20260920-cardgame-3` — shipped in 0.14.0 — qwen3-coder lane now 0/40; cap after 0/N and disable by precision across runs
- `rl-0.13.0-20260920-cardgame-4` — shipped in 0.14.0 — Phase marker is a single slot but two live dispatches are encouraged
- `rl-0.13.0-20260920-cardgame-5` — shipped in 0.14.0 — commit_guard fires when no loop is live (phase done)
- `rl-0.13.0-20260920-cardgame-7` — shipped in 0.14.0 — Lane timeouts vs the Bash ceiling again; skill should say to run detached
- `rl-0.13.0-20260920-cardgame-8` — shipped in 0.14.0 — WATCH LIST round-1 diff candidate still lumps round 1 with the closeout commit
- `rl-0.10.0-20260909-cardgame-1` — shipped in 0.13.0 — thrashing_soft at the cap is the wrong signal for a converging 2-round scoped run
- `rl-0.10.0-20260909-cardgame-2` — shipped in 0.13.0 — Unattended default is undocumented at the verdict and not recorded in rounds.md
- `rl-0.10.0-20260909-cardgame-3` — shipped in 0.13.0 — archive produced Finder-duplicate ' 2' names under iCloud, caught 3 hours later
- `rl-0.10.0-20260909-cardgame-4` — shipped in 0.13.0 — Implementer manifests cannot run: empty replacement rejected, <scratch> placeholder
- `rl-0.10.0-20260909-cardgame-5` — shipped in 0.13.0 — Closeout implementer's BACKLOG punt sketch existed only in its CHANGES block
- `rl-0.10.0-20260909-cardgame-6` — shipped in 0.13.0 — Seed review cost 1.25M effective from re-reading the same file windows
- `rl-0.10.0-20260909-cardgame-7` — shipped in 0.13.0 — 10-minute Bash ceiling makes agents invent their own long-run patterns
- `rl-0.10.0-20260909-cardgame-8` — shipped in 0.13.0 — Skill does not say whether closeout uses add-usage or next-round --usage
<!-- END generated -->
