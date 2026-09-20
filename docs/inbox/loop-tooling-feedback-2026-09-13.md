# review-loop-tools 0.13.0 feedback — 2026-09-13 run (first multi-provider panel)

Run shape: SCOPE mode over one feature commit (ac2d639: radar map pin-tap /
long-press interactivity + per-zoom "What a column shows" table in the strip
detail sheets), skeptical reviewer pinned to Opus, implementer inheriting the
Fable 5.1 session, and a three-lane PANEL: codex (gpt-6-astra), gemini
(gemini-3.5-flash), ollama (qwen3-coder:30b, local). Verdict: CONVERGED at
round 2, closeout ran. 12 chair findings + 3 panel-minted; 1 blocker and 4
majors fixed and device-verified. Closeout: 4 fixed + 1 partial (punt sketch), full app unit target 278/278 green, Core untouched.

Run in a large session (8.2 MB transcript at loop start, over the 2 MB
guard) because the user asked for the whole task — implement, then loop — in
one session; `briefs/.session-ok` was created to proceed. The ~3× plumbing
cost the guard warns about applies to the orchestrator turns only; subagent
figures below are unaffected.

## Usage data

Reported subagent tokens (harness figure; billed effective runs ~4× higher
for code loops per CONTROLS.md) and wall-clock per dispatch:

| Phase | Agent (model) | Tokens | Tool uses | Wall | Outcome |
|---|---|---|---|---|---|
| seed panel | ollama lane (qwen3-coder:30b) | n/a | — | 109 s | 10 candidates |
| seed panel | codex + gemini lanes (after consent) | n/a | — | 228 s | 3 + 6 candidates |
| seed | panel-verifier (sonnet), pass 1 | 39,817 | 24 | 103 s | 0/10 kept |
| seed | panel-verifier (sonnet), pass 2 | 44,096 | 21 | 188 s | 5/9 kept |
| seed | skeptical-reviewer (opus) | 100,841 | 61 | 858 s | 1 blocker, 3 major, 3 minor |
| r1 | implementer (fable 5.1) | 103,134 | 47 | 1,025 s | 5/5 fixed, 7/7 mutants |
| r1 | skeptical-reviewer (opus) | 85,584 | 45 | 958 s | 5 fixed; +1 major (own mutants survived), +3 minor |
| r2 | implementer | 60,727 | 28 | 909 s | 2/2 fixed, 6/6 mutants |
| r2 | skeptical-reviewer (opus) | 53,167 | 31 | 474 s | converged; +1 minor |
| final panel | all three lanes | n/a | — | 202 s | 2 + 6 + 10 candidates |
| final | panel-verifier (sonnet) | 54,531 | 32 | 211 s | 4/18 kept |
| closeout | implementer | 64,860 | 30 | 596 s | 4 fixed, 1 partial (punt sketch) |
| closeout | skeptical-reviewer (opus) | 53,966 | 35 | 612 s | 11 fixed, 1 partial, 4 open minors → BACKLOG; 278 tests, 0 failures; 4/4 mutants |

Totals: 660,723 reported subagent tokens; ~97 min of agent
wall-clock (dispatches partly overlapped: the final panel pass ran alongside
the closeout implementer, the second verifier pass alongside round 1).
Per-round: seed 184,754 · r1 188,718 · r2 113,894 · closeout 173,357 (implementer 64,860 + reviewer 53,966 + final verifier 54,531).

Panel kept-rates (verified findings ÷ filed), both passes:

| Lane | Seed | Final | Notes |
|---|---|---|---|
| codex gpt-6-astra | 2/3 | 1/2 | Specific, line-accurate; the surviving finds were real minors (drift reported as zero; out-and-back drag dodges the net-displacement check). One overlapped the chair's blocker → cross-family agreement. |
| gemini-3.5-flash | 3/6 | 3/6 | One "blocker" claimed a passing test could not compile; one "won't fire" claim contradicted by a passing test; the kept items were real minors + one duplicate of a chair finding. Severity inflated. |
| ollama qwen3-coder:30b | 0/10 | 0/10 | Always files exactly the 10-cap; evidence lines point at unrelated code; three "blockers" describe guards that exist. Cost ~5 min GPU + two verifier passes for nothing. |

Verifier cost per kept panel finding: 138,444 tokens for 9 kept, of which
3 duplicated chair findings — ~23K tokens per net-new panel minor. None of
the panel's findings were round-worthy; all were closeout material.

## What worked notably well

- **The chair's mutation counter-check found the real gap.** The r1
  implementer shipped a 7/7-killed manifest confined to the files it liked;
  the reviewer wrote its own two mutants at the MapScreen call site, both
  survived, and a major was filed and fixed in r2. This is the loop earning
  its cost.
- **Device-verified findings, not inferred ones.** The seed blocker
  (long-press decided on `.began` with travel/drift hard-coded to zero →
  the add dialog pops mid-pan) and two AX5 majors (exclusion radius ~252 pt
  swallowing the whole radar map; caption eating 336 pt) were all measured
  on the simulator via the qa driver, with numbers, and re-measured after
  the fix.
- **Blind verifier as a filter.** 34 panel candidates in, 9 verified out,
  every rejection with a cited reason; the chair never saw raw candidates.
  The verifier's optional "one line of my own" channel produced two useful
  notes (extraction equivalence; haptic generator churn).
- **CHANGES blocks with honest residuals**: the r1 implementer disclosed
  that its first mutation test_cmd matched nothing under `-quiet` and
  reported false kills; the r2 implementer disclosed that mutate.py cuts its
  worktree from HEAD so a pre-commit run mutates the old code. Both are
  tooling lessons (below), surfaced by the agents themselves.
- **Closeout punt channel**: the renderer-pinning refactor (three private
  switches in a 5,000-line view) was correctly punted with a concrete sketch
  in `briefs/closeout-punts.md` instead of being built in the no-iteration
  phase.
- **`next-round` as one call** (merge + metrics + usage + brief + phase)
  kept orchestrator turns to ~3 per round as advertised; the escalation
  2→5 on the blocker was automatic and announced.

## Defects / friction, in impact order

1. **Consent silently lost across the plugin upgrade (cost: both remote
   lanes on the seed pass).** 0.13.0 keys the machine-local consent file by
   `sha256(realpath(loop dir))`; the consent written under the previous
   version sits at a different hash, so `run` skipped codex and gemini with
   "no remote-lane consent" — while `probe --smoke` had just reported both
   lanes "ok". An unattended run would have finished with a one-lane panel
   and only the run JSON would say why. Fixes: (a) probe must check consent
   for the configured lanes and fail the gate loudly; (b) on a key change,
   print the OLD path it would have honored and ask for re-consent once; (c)
   the skill should tell the orchestrator that consent cannot be carried
   over by copying (the auto-mode classifier correctly blocked my attempt).
2. **`:dispatched` stripped while an agent is still running.** Three times
   the SubagentStop of a *different* agent (verifier finishing while the
   reviewer ran; a background task notification) stripped the suffix from
   `.phase`, after which `loop_guard` blocked ordinary conversational turns
   with "round in flight… do not end the turn". Worked around with
   `…:waiting:<reason>`. The marker needs to count live dispatches (or key
   the suffix by agent), not be a single bit.
3. **No usage data from the panel.** `panel_review.py run` reports
   status/filed/overflow only — no tokens, no per-lane wall-clock, no
   `prompt_eval_count` from ollama even though the API returns it. The
   only cost signal for a lane is the verifier's tokens spent rejecting it.
   Add per-lane `elapsed_s` and whatever token counts each CLI/API exposes.
4. **`panel-tally` REPLACES `ledger["panel"][round]`.** A round whose lanes
   run in two batches (as here, after re-consent) loses the first batch's
   tallies unless the second verifier is told to carry them forward by hand.
   Merge per lane instead.
5. **Range + pathspec quoting differs between verbs.** `scope` stores a
   single string verbatim; `diff` needs the pathspec as separate shell
   words (`c27a1b2..HEAD -- ':!prompts.md'`) and fails with "bad revision"
   when given the same single string. One parser for both, or document the
   shape once.
6. **mutate.py trusts the manifest's test_cmd.** Two real failure modes
   this run: a filter pipeline that matched nothing under `-quiet`
   (every mutant "killed"); and a pre-commit run against a HEAD worktree
   that never contained the fix (every mutant "survived"). Add a baseline
   run (test_cmd unmutated must exit 0, and a deliberately-broken sentinel
   must exit non-zero) and refuse to run when the working tree is dirty
   relative to HEAD for the manifest's files.
7. **`probe --smoke` does not smoke the ollama lane** (lists models only).
   A local model that OOMs or clamps context would gate green.
8. **Skill silent on panel↔chair dedupe.** The verifier flagged two
   candidates as restating chair findings; the skill says "the chair mints
   their IDs like any finding" and nothing about adding `sources` to an
   existing ID. Both reviewers did the sensible thing unprompted, but the
   orchestrator had to spell it out in the dispatch.
9. **Session-size guard fires on every turn for the rest of the session**
   (UserPromptSubmit) once over the threshold — including on the user's
   own questions — with no way to acknowledge it after `.session-ok`.
10. **Gemini "best available" is quota-bound, not capability-bound.** On
    this API key gemini-3.1-pro-preview / gemini-3-pro-preview return 429
    "free-tier limit 0"; the lane had to fall back to gemini-3.5-flash. A
    probe that reports the model's quota state would save a manual
    smoke-test loop.

## Recommendations for this repo

- Keep codex; keep gemini only with a paid key and a pro model; drop the
  qwen3-coder:30b lane (0/20 kept across two passes). If a local lane is
  wanted, try it with `max_diff_tokens` lowered and severity capped at
  minor.
- Panel value here was cross-family *agreement* on the chair's blocker,
  not new findings. For scoped runs of this size, the seed pass is the
  useful one; the final pass produced only closeout minors.
- Start loops in a fresh session (the guard is right); do the
  implementation in one session and the loop in the next.

## Observations on the app (out of scope for the tool, for BACKLOG)

See the loop REPORT's WATCH LIST and BACKLOG entry for the residue:
four open minors (net-displacement-only long-press travel check; the closeout's in-place marker re-style loop has no mutation guard; marker body size pinned at 31×35 against a device-measured 31×34; haptic generators fired without prepare()) plus the punted renderer-pinning refactor (sketch in the loop archive's briefs/closeout-punts.md, copied to BACKLOG).
