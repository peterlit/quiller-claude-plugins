# Field questions — qa-loop-tools

What the maintainer wants to know from a run of THIS version, what is
already decided, and what happened to earlier reports. `/qa-loop-tools:feedback`
reads this file: it asks the watch items as closed questions and expects
you to have read the other two sections before writing a defect.

Versioned with the code: every release updates all three sections in the
same commit. The third section is generated — do not edit it by hand.

## Watch items for this version

Answer each `observed`, `not observed`, or `n/a` (the run never reached the
situation). One line of evidence when observed: a path in the loop dir, a
round number, a count.

- **w-driver-field-rig** — Did the shipped `ios-xcuitest` driver build and serve on this rig (an app other than the one it was written against), and did `qa.py <udid> ping` answer on every worker?
- **w-grant-probe** — On the MCP control path, did the Stage-0 real-tap probe catch an ungranted worker BEFORE wave 1, rather than mid-wave?
- **w-worker-reuse** — Did `provision_workers.sh up` reuse existing namespaced workers (`"reused": true`), and did reused workers keep their per-device grants?
- **w-letter-workflows** — Did a letter-suffixed workflow (`WF-9b` / `TC-9b.1`) plan and chunk with every selected case landing in exactly one chunk?
- **w-notes-ceiling** — Did `HARNESS_NOTES.md` stay under its byte ceiling across the run, and did you have to raise `QA_NOTES_CEILING_KB`?
- **w-archive-sync-conflict** — On a synced volume, did `archive` fail on a ` 2`-suffixed duplicate, report `duplicates_detected_late` above 0, or stay quiet while one appeared later?
- **w-arm-when-green** — With `regression_test_arming: arm-when-green`, how many tests were armed and how many of those later flaked?
- **w-minors-only-dispatch** — Under `full_pass_required`, was the minors-only implementer dispatch used for anything but minors?
- **w-fix-review-rejections** — How many fixes did the fix-reviewer reject as unsound or harmful, and did a tester later overturn any of its verdicts on-device?
- **w-degenerated-targeting** — Did a targeted pass degenerate to findings+smoke (`degenerated: true` in the plan), and was `--allow-wide` needed?
- **w-run-summary** — Did the report stage write `feedback/run-summary.json` without being asked, and does its `plugin.version` match what you believe ran?
- **w-dispatch-timing** — Does the summary's `dispatches` section account for every dispatch you made, including parallel testers (`unreturned` and `unmatched_returns` both 0)?
- **w-anomaly-verb** — Did you record a workaround with `merge_ledger.py anomaly` at the moment it happened (a hand-built chunk, an abandoned provisioner), and did any script-recorded anomaly surprise you?

## Settled decisions — report only NEW evidence

Each of these was litigated with field evidence. A report that re-raises one
without new numbers costs a proposal slot and is declined. If your run
produced evidence that contradicts one, that IS worth a defect — cite the
decision's id.

- **s-implemented-rounds** — Thrashing and diminishing signals count POST-IMPLEMENTATION rounds only (`implemented_rounds`). Discovery rounds are net-negative by construction.
- **s-set-usage-replaces** — `set-usage` REPLACES a (round, role) figure; `add-usage` accumulates. Accumulate-only once inflated a budget readout by 89%.
- **s-reported-token-scale** — Budgets and the BUDGET stop use the harness-REPORTED scale, which sits ~11x below billed effective tokens for simulator loops. It is a guardrail on runaway loops, not a dollar ceiling.
- **s-reopen-semantics** — Reopen means fixed->open only; fixed->partial is refinement. A finding a tester reports as still open is neither reopened nor new.
- **s-archive-naming** — Archive directories are named by the ARCHIVED loop's scope or build sha, not HEAD at archive time.
- **s-fix-reviewer-not-terminal** — The fix-reviewer's verdict feeds the ledger; the tester confirms on-device. It is never a gate, and `fixed` is minted only by a test pass.
- **s-unsound-reverts-to-open** — A fix judged unsound reverts its finding to open and is flagged to the human. The rejection rate is a watch item, not a reason to weaken the policy.
- **s-model-pins** — ux-tester `opus`, fix-reviewer `sonnet`, implementer `inherit`. The point is diversity: pins stay distinct from each other and from the session model, and a dispatch never overrides one.
- **s-pbxproj-boundary** — The regression-test-writer never edits `project.pbxproj`, even against a relayed "the user authorized it". Wiring routes through qa-implementer.
- **s-degeneration-guard** — A targeted pass whose diff touches more than 60% of test cases falls back to findings+smoke. `--allow-wide` is the escape hatch; per-workflow commits are the fix.
- **s-mutations-through-scripts** — Every ledger, report and planning mutation goes through the scripts. An orchestrator hand-editing `ledger.json` or `rounds.md` is a skill-wording bug to report, not a shortcut to bless.
- **s-do-not-cut** — Tester exploration, screenshots and extended thinking are not cost levers: cost is turns x context, and cache reads are 98-99% of raw tokens.
- **s-simulator-discipline** — Named per-repo worker devices, per-chunk resets, and stop-and-report on a vanished device stay as they are: several loop sessions share one Mac.

## Open and recently shipped items

<!-- BEGIN generated by tools/render_field_questions.py — do not edit -->
**In the backlog (accepted, not built)**

- `qa-0.12.0-20260909-cardgame-7` — plan_round degenerates every targeted pass; wants symbol/hunk-level diff mapping _(Design-sized; --allow-wide is the escape hatch and A5/A9 recover most of the waste, so the sketch sits in BACKLOG.md until targeted passes still degenerate after 0.13.0.)_

**Declined as already settled**

- `qa-0.12.0-20260909-cardgame-12` — Harness-scale budget is 6.9x under effective, so a budget stop cannot protect spend _(Budgets are deliberately on the reported scale (HANDOFF section 3 and cost doctrine); 0.13.0 only added the caveat sentence to CONTROLS.md (A10.6), no behavior change.)_

**Shipped**

- `qa-0.12.0-20260909-cardgame-2` — shipped in 0.14.0 — MCP simulator tool needs a per-device human grant; ship a generic XCUITest driver
- `qa-0.12.0-20260909-cardgame-1` — shipped in 0.13.0 — provision_workers.sh uses fixed names and deletes every qa-worker-* on the host
- `qa-0.12.0-20260909-cardgame-3` — shipped in 0.13.0 — notes-rotate second pass archives the largest section; 10 KB ceiling too small
- `qa-0.12.0-20260909-cardgame-4` — shipped in 0.13.0 — Tester and orchestrator instructions contradict on ## Chunk note rotation
- `qa-0.12.0-20260909-cardgame-5` — shipped in 0.13.0 — Evidence directories collide across loops; archive does not move evidence/round-N
- `qa-0.12.0-20260909-cardgame-6` — shipped in 0.13.0 — Sibling chunks of one workflow on different workers file duplicate findings
- `qa-0.12.0-20260909-cardgame-8` — shipped in 0.13.0 — full_pass_required with only minors open strands one-line fixes
- `qa-0.12.0-20260909-cardgame-9` — shipped in 0.13.0 — Tiny 1-2 case chunks each pay 40-60K fixed dispatch cost
- `qa-0.12.0-20260909-cardgame-10` — shipped in 0.13.0 — Findings with screen-name regions never reach a tester chunk
- `qa-0.12.0-20260909-cardgame-11` — shipped in 0.13.0 — Regression writer's default skip guard automates nothing; make arming a setting
- `qa-0.12.0-20260909-cardgame-13` — shipped in 0.13.0 — Perf lane re-runs its [perf] cases every round regardless of change
- `qa-0.12.0-20260909-cardgame-14` — shipped in 0.13.0 — MCP build tool targets the first booted device, which was another session's
- `qa-0.12.0-20260909-cardgame-15` — shipped in 0.13.0 — Small: aborted full pass trend row says full; watch list shows duplicate-resolved items
- `qa-0.12.0-20260909-weatherapp-1` — shipped in 0.13.0 — Worker recreation destroys per-device MCP grants; Stage 0 checks availability only
- `qa-0.12.0-20260909-weatherapp-2` — shipped in 0.13.0 — plan_round chunker silently drops letter-suffixed workflow WF-9b; lint passes
- `qa-0.12.0-20260909-weatherapp-3` — shipped in 0.13.0 — Evidence directories collide across loops because archive leaves evidence/ in place
- `qa-0.12.0-20260909-weatherapp-4` — shipped in 0.13.0 — notes-rotate reports over_ceiling but rotates 0 sections
- `qa-0.12.0-20260909-weatherapp-5` — shipped in 0.13.0 — Regression writer refuses pbxproj edits despite relayed user grant; tests orphaned _(Not shipped: letting the regression writer edit project.pbxproj on a relayed grant (declined, D2); the documented qa-implementer hand-off shipped instead.)_
- `qa-0.12.0-20260909-weatherapp-6` — shipped in 0.13.0 — Minor batch: round_tokens name, user-abort stop line, churn under-read, plan summary _(Not shipped: the qa_metrics reopen/churn sub-point (declined as settled, D3).)_
<!-- END generated -->
