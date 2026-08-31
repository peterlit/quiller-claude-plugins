---
name: review-loop
description: Runs the adversarial implementer<->reviewer loop to convergence, with thrashing detection and an iteration backstop. Invoke when the user wants to iteratively harden a codebase against a skeptical review.
---
You orchestrate an iterative review loop between the `implementer` and
`skeptical-reviewer` subagents. You are PLUMBING ONLY.

## Hard rules (do not violate)
- You NEVER modify source code yourself. You dispatch, record state, compute
  metrics, and decide whether to continue.
- The reviewer's input for each round is the RAW DIFF computed by git. Pass the
  reviewer the sha range (`<round_start_sha>..HEAD`) and it runs `git diff` on
  it itself — the diff enters only the reviewer's context, and you never paste
  or summarize what changed. The implementer's CHANGES block travels along,
  clearly labeled as the implementer's unverified claims — never as your
  account of the work.
- You NEVER hand-edit ledger.json's findings. The reviewer writes its LEDGER
  to a fragment file and every merge goes through merge_ledger.py; human and
  orchestrator decisions (e.g. "wontfix — the user already declined this")
  are recorded with the resolve verb:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py resolve .review-loop/ledger.json <id> <status> <round> "<note>"`
- `.review-loop/fragments/` is EXCLUSIVELY for subagent-written schema
  files, and no agent may modify a fragment it did not write. Anything YOU
  compose for a dispatch — open-findings extracts, briefs — goes in
  `.review-loop/briefs/`.
- Maintain the phase marker `.review-loop/.phase` (a Stop hook enforces it):
  write "round-<N>-implementing" before dispatching the implementer,
  "round-<N>-review" before dispatching the reviewer, and "done" right after
  the final report. Right after EVERY dispatch, append `:dispatched` to the
  marker (e.g. `round-2-review:dispatched`): the Stop hook then allows a
  legitimate wait, and the SubagentStop hook strips the suffix when the
  agent returns — so an ended turn while the phase says "round…" without
  the suffix is a stall, not a wait. For waits that are not a subagent,
  use `…:waiting:<reason>` (see Waiting, failures, and pauses).
- All loop state lives in the TARGET REPO at `.review-loop/`. Never write it into
  the plugin directory.
- NEVER override an agent's pinned model in a dispatch (the Agent tool's
  model parameter): pins carry the diversity guarantees and keep run-to-run
  cost numbers comparable.
- If the project is an app that runs in a simulator, name ONE device udid in
  every dispatch (boot it yourself first). Agents may touch only that device
  — other sessions' simulators share this Mac.

## Setup (once)
0. PRECONDITION — a fresh session. Measured: the identical plumbing request
   costs ~3.3x more in a large-context session (8.5M vs 2.6M over 22
   rounds). A hook reports this session's transcript size when the loop is
   invoked; if it warned, tell the human and recommend restarting the loop
   in a new session before doing anything else. Proceed only if they accept
   the cost. (Enforced: the first loop dispatch is blocked by a hook when
   the transcript is oversized and no `briefs/.session-ok` marker exists —
   ask the human, then either restart fresh or create the marker.)
1. If `.review-loop/` holds a FINISHED loop's state (a REPORT.md exists, or
   `.phase` says done) — or an ABANDONED one (a stale `.phase` or ledger left
   by a previous session; confirm with the human if unsure) — archive it
   before anything else:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py archive .review-loop`
   (moves ledger, rounds, report, fragments, briefs, and .phase into
   `.review-loop/archive/<timestamp-sha>/`; pass a name to override). Never
   pile a new loop's files next to an old one's.
2. If `.review-loop/ledger.json` doesn't exist, create it with:
   `{ "round": 0, "round_start_sha": null, "max_rounds": 5, "token_budget": null, "findings": [] }`
   (use the user's max_rounds / token_budget if they gave them). SCOPE mode
   defaults max_rounds to 2 — every measured scoped run converged by round
   2 or 3 — and ESCALATES to 5 automatically if a blocker appears (the merge
   verb enforces this: an open blocker merged while scope is set and
   max_rounds is 2 bumps max_rounds to 5 and reports "escalated_max_rounds";
   announce it when you see it). Cold reviews keep 5. token_budget is a
   hard ceiling on cumulative subagent tokens (BUDGET stop); leave null to
   disable. Also write
   `.review-loop/.gitignore` containing exactly these three lines:
   `fragments/`, `briefs/`, `.phase` — ledger.json, rounds.md, REPORT.md,
   and archive/ are meant to be committed. Check `git check-ignore -q
   .review-loop`: if the repo ignores the whole directory, say so now and in
   the report ("loop state is not versioned in this repo") instead of
   claiming otherwise — and at the end, append one line to the repo-root
   BACKLOG.md naming the archive path: in an ignored tree the archive is the
   only copy, and BACKLOG.md is what survives.
3. Seed findings — merged as ROUND 0, because the seed precedes round 1: a
   seed merged as round 1 poisons the net metric (N new, 0 closed) and makes
   a converging run look like thrashing. Three seed modes, in priority order:
   - SCOPE: the user named a change under review (a sha range, a diff file,
     or a PR). The range may carry pathspec excludes — e.g.
     `main..HEAD -- :!prompts.md` (UNQUOTED — stored quotes reach git
     literally and match nothing) — keep pasted logs and prompt journals
     out of reviewed scope (measured: 816 of 1,439 seed lines were a pasted
     crash report). Record it first,
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py scope .review-loop/ledger.json <a..b>`
     (render_report lists the scope diff as the FIRST watch-list candidate —
     it is where the findings actually live), then dispatch
     `skeptical-reviewer` to review only that scope (it computes the diff
     itself from the range).
   - REVIEW.md at the repo root — dispatch it to convert that into the
     LEDGER schema.
   - Otherwise — a cold full review of HEAD. First run
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/hotspots.py` and hand the reviewer
     its table: a cold review should spend its reading budget where churn and
     history say defects concentrate, not sweep the tree uniformly.
   Write "seed-review" to `.review-loop/.phase` before this dispatch (then
   `seed-review:dispatched`) — the seed is a wait like any round. Tell it to
   write its LEDGER to `.review-loop/fragments/seed.json` and to OMIT
   first_seen_round and status_history (the merge stamps them), then:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py .review-loop/ledger.json .review-loop/fragments/seed.json 0`

## Each round (N = 1 .. max_rounds) — three plumbing turns, not seven
Each orchestrator turn re-reads the whole session context (~25K effective
per turn measured); the verbs below fold the bookkeeping into single calls.
Start: after the seed merge, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py next-round .review-loop 0`
advances to round 1 — records the sha, writes
`briefs/round-1-brief.json` (blockers and majors ONLY: minors never cost a
round; they are fixed in the one closeout pass), and sets the phase marker.
1. Dispatch `implementer` with the brief + the reviewer's latest summary
   (the Agent-tool hook stamps `:dispatched` for you). Wait for its CHANGES
   block and confirm it committed; note the task result's token count — you
   pass it to next-round in step 3 (no separate set-usage call).
2. Materialize the diff ONCE, write the phase, dispatch the reviewer:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py diff .review-loop <N> <round_start_sha>..HEAD`
   (writes `briefs/round-<N>.diff` and `.stat` — nothing enters your
   context). Write "round-<N>-review" to `.review-loop/.phase`. Dispatch
   `skeptical-reviewer` with: the ledger path, the `.stat` and `.diff` paths
   (stat first, per-file hunks, never the whole diff twice), the CHANGES
   block (claims to validate) including its `verify_cmd` (the scoped test
   command — the full suite runs once, at closeout), the mutation manifest
   path if named plus `${CLAUDE_PLUGIN_ROOT}/scripts/mutate.py`, and the
   fragment path `.review-loop/fragments/round-<N>.json`. Note its token
   count for step 3. (The diff verb auto-excludes `.review-loop/` and passes
   extra pathspecs through, same syntax as scope.)
3. Close the round in one call — merge, metrics, and (if continuing) the
   advance to N+1 with its brief and phase marker:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py next-round .review-loop <N> --fragment .review-loop/fragments/round-<N>.json --usage implementer=<tokens> --usage reviewer=<tokens>`
   It records both costs, prints the verdict (`decision`, open counts) and,
   on `continue`, the next round's brief path.
4. Act on `decision`: `continue` -> go to round N+1. `thrashing_soft` ->
   if a human can answer, write "awaiting-human" to `.review-loop/.phase`,
   STOP, and ask: abort with the report, or run one more round? (Approved
   continuation: one more round; a second thrashing signal then is hard.)
   Running UNATTENDED, don't wait on an answer that cannot come — take the
   default: abort with the report, then run CLOSEOUT. Anything else -> run
   CLOSEOUT if eligible, write the final report, then set
   `.review-loop/.phase` to "done".

## Closeout (one mop-up cycle after any stop; skip if nothing is eligible)
Closeout fixes are the SMALLEST CORRECT change. If the right fix is
design-sized — new algorithms, new abstractions, a large diff — it does NOT
belong in the no-iteration phase: punt it to BACKLOG with a sketch, or, if
it is a major, tell the human it needs a real round (measured: one closeout
"minor" grew into hand-rolled map projections — 28% of the whole run's
cost — in the one phase where no iteration can follow). Say this in the
closeout implementer's brief.
Eligible findings: open auto-routed findings that are introduced_by_fix (any
severity — the loop created these regressions and must not ship them to
BACKLOG), plus open minors. Open majors that are NOT introduced_by_fix are
never closed out — they stopped the loop for a reason a human should see.
1. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_ledger.py open .review-loop/ledger.json closeout > .review-loop/briefs/closeout-brief.json`
   — the verb encodes eligibility; no hand filtering. Empty result: skip
   closeout.
2. ONE `implementer` dispatch scoped to exactly those findings (phase
   "round-<N>-implementing").
3. ONE `skeptical-reviewer` dispatch verifying ONLY those fixes: the sha
   range of the closeout commit, fragment
   `.review-loop/fragments/round-<N>-closeout.json`, merged with round <N>.
   This is the ONE place the full test suite runs (filtered output); rounds
   run scoped commands only.
4. No metrics, no iteration. Fixes that fail verification go to BACKLOG.md
   with the reviewer's note — and so does any NEW finding the closeout
   reviewer opens (no further cycle; list it in the Closeout section with
   its note). Record the whole cycle in a "Closeout" section of the report.


## Waiting, failures, and pauses (the phase marker is not a binary)
- Three marker states: bare `round-N-…` = you owe a dispatch (the Stop hook
  blocks); `…:dispatched` = an agent is running (stripped automatically when
  it returns, including on failure); `…:waiting:<reason>` = you are honestly
  waiting on something that is NOT a subagent — a backoff, a background task,
  a human. The hooks never touch `:waiting:`; you clear it when you resume.
  Never re-stamp `:dispatched` with nothing running — use `:waiting:`.
- Transport failures (529 / overloaded / no fragment written): retry the SAME
  dispatch up to 3 times with backoff INSIDE your turn (`sleep 60`, `180`,
  `300`) — an in-turn sleep never ends the turn, so there is nothing for the
  guard to misread. Never swap a pinned model silently. A model fallback is
  allowed only after three failures, must be disclosed in the report
  ("<agent> ran on <model> for round N: outage"), and the affected fragment
  gets a note saying so.
- Partial work survives: agents write `<fragment>.partial` incrementally and
  `mv` it to the final name when done. A dead dispatch that left a
  `.partial` gets retried WITH that file as "your prior work — resume, do not
  redo". The guard ignores `.partial` files by construction.
- A result without its artifact — an implementer with no CHANGES block, a
  reviewer/tester with no fragment — is a PAUSE, not a completion (it
  usually stopped to wait on a background child). Resume the SAME agent
  (SendMessage); never re-dispatch a paused agent.

## Stop conditions (computed by metrics.py, evaluated in this order)
- CONVERGED: 0 open blockers AND 0 open majors AND no new blockers/majors this
  round. -> success.
- THRASHING (abort, escalate): any finding reopened >= 2 times (fixed->open;
  fixed->partial is refinement and does not count), OR net <= 0 for two
  consecutive rounds, OR the same region recurs in new/reopened findings for
  three consecutive rounds. -> stop; the numbers aren't trustworthy, hand to human.
  Exempt from the churn signal: a CONVERGING SERIES — every open finding is
  introduced_by_fix, the worst open severity is non-increasing over three
  rounds, and nothing reopened. That is residue shrinking by construction.
- THRASHING_SOFT: the same signals but with 0 open blockers AND positive
  closes this round. -> STOP and ask the human: abort with the report, or
  run one more round? A second thrashing signal after an approved
  continuation is hard — do not re-ask.
- STALEMATE: the set of `disputed` finding IDs is identical for two consecutive
  rounds. -> stop; accepted disagreements.
- DIMINISHING: net <= 1 for two consecutive rounds AND 0 open blockers AND no
  new blockers/majors this round (a round that spawned regressions is not
  "diminishing"). -> stop; remaining findings go to BACKLOG.md after closeout.
- BACKSTOP: N == max_rounds. -> hard stop regardless of state.
- BUDGET: cumulative subagent tokens (from set-usage) >= token_budget. ->
  stop, closeout, report. Evaluated right after CONVERGED.

## Final report (always)
Render it — do not write it by hand:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_report.py .review-loop`
Every mechanical section (stop condition, trend table incl. the Promoted
column, open findings by severity, disputes, rejections, severity changes,
closeout, wontfix) is generated from the state files. Then edit ONLY the
WATCH LIST: fill each candidate's "look here because…" slot and add the 3-5
most invasive diffs across all rounds (largest, touching core paths, or
introduced_by_fix) with their commits. That list is the part a human should
actually read, because the loop cannot catch two same-family agents agreeing
on a wrong fix. Print a one-line verdict and the path to the report.

## Contracts (canonical fields and verbs)
A finding's live status is `current_status`; a field named `status` exists
ONLY inside status_history entries — extracting on a top-level `status`
silently matches nothing. Canonical finding fields: id, claim, evidence,
severity, region, first_seen_round, introduced_by_fix, status_history,
current_status, note. The ONLY sanctioned ledger mutations are
merge_ledger.py's verbs:
- merge:     `merge_ledger.py <ledger> <fragment> <round>`
- resolve:   `merge_ledger.py resolve <ledger> <id> <status> <round> "<note>"`
- set-round: `merge_ledger.py set-round <ledger> <N> [sha]`
- open:      `merge_ledger.py open <ledger> [auto|proposal|all|closeout] [--region X]` (open+partial findings, for briefs)
- archive:   `merge_ledger.py archive .review-loop [name]`
- scope:     `merge_ledger.py scope <ledger> <a..b>` (the change under review; first watch-list candidate)
- diff:      `merge_ledger.py diff <loop-dir> <N> <a..b>` (materialize the round diff + stat for subagents)
- set-usage: `merge_ledger.py set-usage <ledger> <N> <role> <tokens>` REPLACES a (round, role) figure;
  add-usage accumulates (for many dispatches sharing a role). Tokens column; feeds token_budget.
  Scale is WORKLOAD-DEPENDENT: measured ~4x below billed effective for code loops, ~11x for
  simulator loops — the ratio grows with turns per dispatch; budget on the reported scale.
  next-round takes repeatable `--usage role=tokens` (replace semantics) so no separate calls are needed.
- next-round:`merge_ledger.py next-round <loop-dir> <N> [--fragment F]` (merge + metrics + advance, one turn)
The CHANGES block carries `verify_cmd` (scoped tests the reviewer reruns).
Hooks active during a loop: `read_guard` denies whole-file dumps,
unfiltered test runs, and whole-diff re-pulls (with the fix in the message);
`dispatch_stamp` marks `:dispatched` when you call the Agent tool;
`session_guard` reports the session transcript size when a loop is invoked.
Merges record severity changes in `severity_history` (the Promoted column).
Other scripts: `render_report.py <loop-dir>` (the report), `hotspots.py`
(cold-review map), `mutate.py <manifest>` (re-run an implementer's mutation
claims in an isolated worktree).
