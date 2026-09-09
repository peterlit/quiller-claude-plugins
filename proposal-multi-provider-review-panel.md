# Proposal: Multi-provider review panel for review-loop-tools

*Refreshed 2026-09-08. Status: for review — nothing implemented.*

## The gap, in the plugin's own words

The review loop's guard against correlated blind spots is model pins:
skeptical-reviewer pinned to `opus`, implementer on `inherit`. Both
SKILL.md and CONTROLS.md admit the residual risk explicitly — the WATCH
LIST exists "because the loop cannot catch two same-family agents agreeing
on a wrong fix." Opus and Sonnet share training data, idioms, and RLHF
style; their blind spots overlap in exactly the places a review loop is
supposed to cover. Cross-provider reviewers — OpenAI, Google, and a
locally running open-weights model — are the only lever that decorrelates
at the family level.

## Why the architecture is already ready for this

The reviewer contract is file-based end to end, which is the whole reason
this is cheap to add:

- **Input is on disk**: `ledger.json`, `briefs/round-N.stat`,
  `briefs/round-N.diff`. No conversation context is needed to review.
- **Output is a schema'd fragment file** merged by `merge_ledger.py`. The
  merge verb already takes any fragment path.
- **Failure handling is file-based**: `.partial` files, retries, and the
  rule that a missing artifact is a pause, not a completion.

External reviewers therefore run as headless CLI processes dispatched via
Bash — not the Agent tool — reading the same briefs and writing candidate
files next to the fragments.

## Core design: finders and a chair

The single most important decision: **external reviewers only propose NEW
findings. They never touch ledger status.** The pinned Anthropic
skeptical-reviewer remains the sole ledger owner — it mints IDs, sets
`current_status`, tracks rejections, and files the one fragment that
merges. This keeps every invariant intact:

- The ledger schema and status rules (`current_status`, `status_history`,
  `rejections` unions) are subtle; external models won't follow them
  reliably, and we shouldn't ask them to.
- Metrics, thrashing detection, and convergence math are untouched — only
  chair-verified findings enter the ledger, so the panel is purely
  additive and cannot destabilize the loop's control theory.
- The merge path stays single-fragment per round. No merge changes needed.

Flow per panelled round:

1. Orchestrator materializes the diff as today (`diff` verb).
2. `panel_review.sh` launches each configured lane in parallel
   (background, with per-lane timeout). Each lane writes
   `fragments/round-N-<lane>.candidates.json` — a *simplified* schema:
   `claim`, `evidence` (file:line), `severity`, `confidence`, `area`.
   No IDs, no status, no history.
3. The chair (skeptical-reviewer) is dispatched as today, with one
   addition to its brief: the candidate file paths, labeled "claims from
   other reviewers — verify each against the code; confirm, demote, or
   reject." Confirmed candidates enter its fragment with a
   `source: "panel:<lane>"` field; rejections are counted per lane.
4. Merge and metrics proceed unchanged.

**Anchoring guard**: the chair's prompt orders its work — do your own
independent pass FIRST, then open the candidate files. Candidates are
always labeled unverified claims, same as the implementer's CHANGES
block. (A v2 option if anchoring shows up anyway: a separate cheap
verifier agent adjudicates candidates so the chair stays blind.)

**Timeout is soft**: a lane that hangs, rate-limits, or auth-fails is
skipped with a note in the report — never blocks the round. Same spirit
as the existing model-fallback disclosure rule.

## The three lanes

| Lane | Runner | Mode | Notes |
|------|--------|------|-------|
| OpenAI | `codex exec --sandbox read-only` | Agentic (can grep/read the repo) | Capture final message to the candidates file (`--output-last-message`). Read-only sandbox means it can explore but not mutate. |
| Google | `gemini -p "<prompt>"` (headless) | Agentic or diff-only | JSON output mode; same read-only discipline stated in the prompt. |
| Local | Ollama API (`/api/generate`, `format: json`) | **Diff-only one-shot** | e.g. `qwen3-coder`, `deepseek-r1`, `gpt-oss`. No harness: prompt = stance + stat + diff, response = candidates JSON. |

The local lane's constraints and its point:

- **Diff-only**: the model sees the stat and the diff hunks, not the
  repo. Cap input to the model's context (config knob, default ~32K
  tokens of diff; oversized rounds send stat + largest hunks and note the
  truncation — no silent caps, per the loop's own rule).
- **The point is privacy, not quality.** For repos that must not leave
  the machine, the local lane is the *only* cross-family option, and the
  setup gate should say so. Expect lower precision; that's what per-lane
  precision tracking (below) is for.

A shared prompt template ships in the plugin
(`templates/panel-reviewer.md`): the skeptical stance distilled from
skeptical-reviewer.md (guilty until proven correct, file:line evidence,
concrete failure modes, no praise, severity definitions,
CONFIRMED-vs-SUSPECTED honesty), plus the candidate JSON schema and a
**hard cap: top 10 findings by confidence**. The cap is the flood
control — a false positive costs the chair verification time, and an
adversarially-prompted external model will over-file without it.

## Configuration

- `.review-loop/panel.json`, written at Setup:
  ```json
  {
    "lanes": [
      {"name": "codex",  "cmd": "codex exec ...",   "timeout_s": 600, "mode": "agentic"},
      {"name": "gemini", "cmd": "gemini -p ...",     "timeout_s": 600, "mode": "agentic"},
      {"name": "local",  "model": "qwen3-coder:30b", "timeout_s": 900, "mode": "diff-only", "max_diff_tokens": 32000}
    ],
    "rounds": "seed"
  }
  ```
- **Detection at the gate**: Setup probes `command -v codex`,
  `command -v gemini`, `curl -s localhost:11434/api/tags`, and offers the
  available lanes. Nothing runs without the human turning it on.
- **`rounds` knob**: `"seed"` (default) | `"seed+final"` | `"all"`.
  Recommendation: seed-only. Breadth matters most in the seed review,
  where the finding set is born; per-round fix verification is chair
  work, and panelling every round multiplies external cost for findings
  the chair would catch anyway. `"all"` exists for pre-release audits.
- **Privacy consent is explicit and per-repo**: the gate states plainly
  that the codex/gemini lanes send the diff (and, in agentic mode, any
  file the tool reads) to OpenAI/Google. Private repo → local lane only.
  This is a one-time recorded answer in panel.json, not a silent default.

## Report and measurement

- Findings carry `source` (`"panel:gemini"` etc.; absent = chair's own).
  `render_report.py` gains a **Panel** section: per lane, candidates
  filed / confirmed / demoted / rejected — i.e., measured precision per
  lane per run. That is the drop-or-keep signal: a lane whose confirmed
  rate stays low across runs isn't earning its verification cost.
- Usage: chair verification cost lands in the existing `set-usage` feed.
  External lanes bill outside Anthropic tokens; record wall-clock and a
  per-lane note in the report rather than pretending the token ledgers
  are commensurable. `token_budget` semantics unchanged.
- The WATCH LIST guidance updates honestly: a finding confirmed
  independently by two-plus families is *higher* confidence; a run where
  the panel filed nothing the chair hadn't found is *evidence the pins
  were enough this time* — both are worth a line.

## Risks and their mitigations

- **False-positive flood** → top-10-by-confidence cap, chair rejects
  cheaply, per-lane precision in the report, drop persistently weak lanes.
- **Chair anchoring / lazy confirmation** → own-pass-first prompt
  ordering; candidates labeled unverified; v2 blind-verifier option.
- **External CLI flakiness** (auth expiry, rate limits, outages) → soft
  timeout per lane, skip with disclosure, never block the round.
- **Data egress** → explicit per-repo consent at the gate; local lane as
  the private-repo path; agentic lanes run read-only sandboxes.
- **Local model quality** → diff-only scope keeps it honest (nothing to
  hallucinate repo-wide), precision tracking decides whether it stays.
- **Cost drift** → seed-only default; external spend disclosed in the
  report; the panel adds chair verification tokens, measurable via the
  existing usage feed from run one.

## Phasing

1. **MVP**: `panel_review.sh` + prompt template + candidates schema +
   chair-brief addition + `source` field + Panel report section.
   Seed-round only, diff-only mode for all three lanes (uniform, simplest
   to ship and measure).
2. **Agentic lanes**: read-only repo exploration for codex/gemini;
   compare precision against their diff-only baselines from phase 1.
3. **Tuning**: `rounds: all` support, per-lane auto-disable on measured
   low precision, cross-family agreement promoting finding confidence,
   and evaluating a panel seat for the qa-loop's fix-reviewer.

## Open questions for the maintainer

1. Seed-only default, or seed+final? (Final-round panel catches
   fix-introduced regressions the chair family might share with the
   implementer — the strongest argument for `seed+final`.)
2. Should candidate *rejections* be recorded in the ledger (as wontfix
   rows with source) or only counted in the Panel section? Leaning:
   counts only — rejected candidates never earned an ID.
3. Chair-verifies vs. separate blind verifier in v1? Leaning: chair, for
   cost; revisit if the Panel section shows suspiciously high confirm
   rates.
4. Is qa-loop in scope at all for v1? Leaning: no — simulator evidence
   doesn't travel to external CLIs; review-loop's diff-shaped input is
   the natural fit.
