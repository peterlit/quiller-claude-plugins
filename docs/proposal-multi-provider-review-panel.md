# Proposal: Multi-provider review panel for review-loop-tools

*Refreshed 2026-09-08. Decisions recorded 2026-09-09. Status: phase 1
implemented (review-loop-tools 0.11.0) — awaiting commit approval. Rollback
point: tag `pre-multi-provider-panel` (= `0a75e47`).*

## Decisions (2026-09-09)

The four open questions were answered by the maintainer:

1. **Panel rounds: `seed+final`.** The final-round panel exists to catch
   fix-introduced regressions the Anthropic family might share with the
   implementer.
2. **Candidate rejections: counts only.** Rejected candidates never earn a
   ledger ID; they appear solely in the Panel report section's per-lane
   tallies.
3. **Verification: separate blind verifier from v1.** The chair never reads
   raw candidates; a dedicated verifier agent adjudicates them (design
   below).
4. **Scope: review-loop only.** qa-loop is out — simulator evidence doesn't
   travel to external CLIs.

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

## Core design: finders, a blind verifier, and the chair

The single most important decision: **external reviewers only propose NEW
findings. They never touch ledger status.** The pinned Anthropic
skeptical-reviewer (the chair) remains the sole ledger owner — it mints
IDs, sets `current_status`, tracks rejections, and files the one fragment
that merges. This keeps every invariant intact:

- The ledger schema and status rules (`current_status`, `status_history`,
  `rejections` unions) are subtle; external models won't follow them
  reliably, and we shouldn't ask them to.
- Metrics, thrashing detection, and convergence math are untouched — only
  verified findings enter the ledger, so the panel is purely additive and
  cannot destabilize the loop's control theory.
- The merge path stays single-fragment per round. No merge changes needed.

Per decision 3, candidate adjudication is a **separate blind-verifier
agent**, not the chair. A new small agent, `panel-verifier` (pinned
`sonnet` — distinct from the chair's `opus` pin and, per the existing pin
rule, it must stay distinct from the session model too), receives the
candidate files plus the round's stat/diff paths, verifies each claim
against the actual code, and writes
`fragments/round-N-panel.verified.json`: confirmed findings only, each
carrying `source: "panel:<lane>"` and per-lane reject/demote counts in a
summary block. The chair never sees raw candidates at all — anchoring is
prevented structurally, not by prompt ordering.

Flow per panelled round (seed and final):

1. Orchestrator materializes the diff as today (`diff` verb).
2. `panel_review.sh` launches each configured lane in parallel
   (background, with per-lane timeout). Each lane writes
   `fragments/round-N-<lane>.candidates.json` — a *simplified* schema:
   `claim`, `evidence` (file:line), `severity`, `confidence`, `area`.
   No IDs, no status, no history.
3. The `panel-verifier` is dispatched with the candidate files and diff
   paths; it emits the verified file with per-lane tallies. The chair is
   dispatched as today — its own pass is fully independent — with one
   brief addition: the *verified* file path, labeled "panel findings,
   already code-verified; fold in with their source attribution, dedupe
   against your own findings, do not re-litigate."
4. Merge and metrics proceed unchanged.

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
control — a false positive costs the verifier time, and an
adversarially-prompted external model will over-file without it.

## Authentication guidance per lane

What each provider option needs before its lane can run, and what it
means for unattended loops and data handling. Everything here is
account-level setup the *human* does once; the loop only probes that
credentials already work.

### OpenAI — Codex CLI

Install: `npm install -g @openai/codex` (or `brew install codex`).
Credentials are cached in `~/.codex/`.

- **Option A — ChatGPT sign-in** (`codex login`, browser OAuth): uses a
  ChatGPT Plus/Pro/Team/Enterprise subscription's included quota. No
  per-token billing. The OAuth session expires periodically and renewing
  it needs a browser — a mid-loop expiry kills the lane (softly, per the
  timeout rule, but it kills it).
- **Option B — API key** (`OPENAI_API_KEY`, or `codex login --api-key`):
  usage-based billing on the OpenAI platform. No interactive renewal;
  **recommended for the loop** because dispatches are headless.
- Data handling: the API does not train on inputs by default. For
  ChatGPT-subscription auth, training use follows the account's data
  settings — verify the opt-out before pointing it at private code.

### Google — Gemini CLI

Install: `npm install -g @google/gemini-cli`. Credentials cache in
`~/.gemini/`.

- **Option A — Google sign-in** (OAuth, free tier): generous request
  limits at zero cost, but the free consumer tier's terms allow Google to
  use submitted content to improve its services — **do not use this tier
  on private code**. Workspace accounts may also require
  `GOOGLE_CLOUD_PROJECT` to be set.
- **Option B — AI Studio API key** (`GEMINI_API_KEY`): the *paid* API
  tier does not train on inputs; the unpaid API tier has the same caveat
  as Option A. **Recommended for the loop**: paid key, headless-safe.
- **Option C — Vertex AI**: `GOOGLE_GENAI_USE_VERTEXAI=true` plus GCP
  project and Application Default Credentials
  (`gcloud auth application-default login`). Enterprise data terms and
  billing; the right choice if the code already lives under a GCP org
  policy. ADC tokens refresh non-interactively once established.

### Local — Ollama

No authentication at all, which is the lane's reason to exist:
`brew install ollama`, run the app or `ollama serve`, then
`ollama pull qwen3-coder:30b` (or chosen model). The loop talks to
`localhost:11434`; nothing leaves the machine, no account, no billing.
Sizing note: a 30B-class coder model wants ~20+ GB of RAM; smaller pulls
(7–8B) run anywhere but drop precision further.

### Loop-side rules that follow from the above

- **Setup-gate probe**: before offering a lane, verify auth *works now* —
  `codex login status` (or a one-token `codex exec` smoke call),
  a trivial `gemini -p "ok"` call, and `curl -s localhost:11434/api/tags`.
  A lane that would require an interactive browser login mid-loop is
  offered as "needs re-auth first"; the human runs the login in-session
  (`! codex login`) before the loop starts.
- **Recommend API-key auth for both remote lanes** in the gate text:
  subscription OAuth is fine for attended experiments, but the loop is a
  headless consumer and token expiry mid-run degrades the panel silently
  (well — disclosed, but degraded).
- **Keys live in the environment, never in `panel.json`** — the config
  names the env var, not the value, and `panel.json` stays committable
  under the loop-dir allowlist rules.
- The privacy consent line at the gate now has teeth: it can state per
  lane whether the configured auth tier trains on inputs.

## Configuration

- `.review-loop/panel.json`, written at Setup:
  ```json
  {
    "lanes": [
      {"name": "codex",  "cmd": "codex exec ...",   "auth_env": "OPENAI_API_KEY", "timeout_s": 600, "mode": "agentic"},
      {"name": "gemini", "cmd": "gemini -p ...",     "auth_env": "GEMINI_API_KEY", "timeout_s": 600, "mode": "agentic"},
      {"name": "local",  "model": "qwen3-coder:30b", "timeout_s": 900, "mode": "diff-only", "max_diff_tokens": 32000}
    ],
    "rounds": "seed+final"
  }
  ```
- **Detection at the gate**: Setup probes `command -v codex`,
  `command -v gemini`, `curl -s localhost:11434/api/tags`, and offers the
  available lanes. Nothing runs without the human turning it on.
- **`rounds` knob**: `"seed+final"` (default, per decision 1) | `"seed"` |
  `"all"`. Seed is where the finding set is born; final catches
  fix-introduced regressions the chair's family might share with the
  implementer. `"all"` exists for pre-release audits; `"seed"` for cost
  control.
- **Privacy consent is explicit and per-repo**: the gate states plainly
  that the codex/gemini lanes send the diff (and, in agentic mode, any
  file the tool reads) to OpenAI/Google, and whether the configured auth
  tier trains on inputs. Private repo → local lane only. This is a
  one-time recorded answer in panel.json, not a silent default.

## Report and measurement

- Findings carry `source` (`"panel:gemini"` etc.; absent = chair's own).
  `render_report.py` gains a **Panel** section: per lane, candidates
  filed / confirmed / demoted / rejected — i.e., measured precision per
  lane per run (counts only, per decision 2 — rejected candidates never
  enter the ledger). That is the drop-or-keep signal: a lane whose
  confirmed rate stays low across runs isn't earning its verification
  cost.
- Usage: verifier and chair costs land in the existing `set-usage` feed
  (verifier under role `panel-verifier`). External lanes bill outside
  Anthropic tokens; record wall-clock and a per-lane note in the report
  rather than pretending the token ledgers are commensurable.
  `token_budget` semantics unchanged.
- The WATCH LIST guidance updates honestly: a finding confirmed
  independently by two-plus families is *higher* confidence; a run where
  the panel filed nothing the chair hadn't found is *evidence the pins
  were enough this time* — both are worth a line.

## Risks and their mitigations

- **False-positive flood** → top-10-by-confidence cap, verifier rejects
  cheaply, per-lane precision in the report, drop persistently weak lanes.
- **Chair anchoring** → solved structurally: the chair never sees raw
  candidates, only the blind verifier's confirmed output (decision 3).
  Residual risk shifts to verifier leniency — watched via the Panel
  section's confirm rates; the verifier's `sonnet` pin is the tuning knob.
- **External CLI flakiness** (auth expiry, rate limits, outages) → soft
  timeout per lane, skip with disclosure, never block the round;
  API-key auth recommended over OAuth for headless reliability.
- **Data egress** → explicit per-repo consent at the gate naming each
  lane's training posture; local lane as the private-repo path; agentic
  lanes run read-only sandboxes.
- **Local model quality** → diff-only scope keeps it honest (nothing to
  hallucinate repo-wide), precision tracking decides whether it stays.
- **Cost drift** → seed+final default; external spend disclosed in the
  report; verifier + chair tokens measurable via the existing usage feed
  from run one.

## Phasing

1. **MVP**: `panel_review.sh` + prompt template + candidates schema +
   `panel-verifier` agent (sonnet pin) + chair-brief addition + `source`
   field + Panel report section + setup-gate auth probes. Seed+final
   rounds, diff-only mode for all three lanes (uniform, simplest to ship
   and measure).
2. **Agentic lanes**: read-only repo exploration for codex/gemini;
   compare precision against their diff-only baselines from phase 1.
3. **Tuning**: `rounds: all` support, per-lane auto-disable on measured
   low precision, and cross-family agreement promoting finding
   confidence.

## Resolved questions (2026-09-09)

Originally open, now decided — kept for the record:

1. Seed-only vs. seed+final → **seed+final**.
2. Record candidate rejections in the ledger vs. counts only → **counts
   only**.
3. Chair-verifies vs. separate blind verifier in v1 → **separate blind
   verifier**.
4. qa-loop in scope → **no; review-loop only**.
