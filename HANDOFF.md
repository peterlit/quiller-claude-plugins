# HANDOFF — maintainer's guide

Written 2026-09-07 for whoever (human or Claude session) picks up maintenance of
this repo next. The repo itself is complete and self-describing at the *what*
level (READMEs, CONTROLS.md, the SKILL.md files, and a rationale-dense git log).
This file captures the *how we work* knowledge that previously lived only in
the maintaining session's conversation history.

State as of this writing: `review-loop-tools 0.9.0`, `qa-loop-tools 0.11.0`,
`arch-docs-tools 0.1.0`, all committed and pushed to
`github.com/peterlit/quiller-claude-plugins`, working tree clean.

---

## 1. How this project actually works — the loop behind the loops

This marketplace is developed by a **measured field-feedback cycle**, and that
process is the most important thing to preserve:

- **Field agents** are separate Claude sessions Peter runs against real
  codebases: *agent 1* works in `~/Documents/src/weatherapp`, *agent 2* in
  `~/Documents/src/cardgame` (an app codenamed "Causeway"). They run the
  plugins for real, then write feedback memos and token-usage studies into
  their own repos (`weatherapp/docs/reports/`, `cardgame/docs/`). **Those memos
  are not in this repo** — Peter pastes or attaches them here. If you need the
  raw history, those directories are the archive.
- **Cadence**: Peter delivers feedback → you digest it and write a numbered
  proposal (what you'd change, the mechanism, what you'd decline and why) →
  Peter approves (his approvals are terse: "go", "yes", "build it") → you
  build → smoke-test → release. **Never build before the proposal is
  approved.** When a decision is a judgment call, flag it explicitly; he
  sometimes delegates ("use your judgment on the five decisions") but wants to
  see that the call existed.
- **First diagnostic for every field report: verify which plugin version
  actually ran.** `~/.claude/plugins/installed_plugins.json` is ground truth.
  One entire feedback cycle was spent on "0.4.0 features are absent" reports
  that came from a stale install. Ask for or check the version before treating
  any claim as a plugin bug.
- **Distinguish harness artifacts from plugin bugs before fixing.** Several
  reported "bugs" were test-chain artifacts (`&&` chains skipping setup, cwd
  deleted under the shell, BSD `grep -L` exit-code quirk, stale `.pyc`
  shadowing a restored file). Reproduce minimally first; two "regressions"
  turned out not to exist.
- **Commit messages are the decision log.** They carry the measured numbers and
  the reasoning for each rule. Read `git log` in full for the last handful of
  releases before re-litigating any design choice.

## 2. Non-negotiable maintenance rituals

1. **Bump `plugin.json` version on every user-visible change.** The plugin
   cache is keyed by version; an unchanged version means installed users
   silently never receive the update. Marketplace entries in
   `.claude-plugin/marketplace.json` never carry versions.
2. **Shared scripts are authored in `review-loop-tools/scripts/` and cp-synced
   byte-identical to `qa-loop-tools/scripts/`**: `merge_ledger.py`,
   `render_report.py`, `loop_guard.sh`, `subagent_guard.sh`, `read_guard.sh`,
   `dispatch_stamp.sh`, `session_guard.sh`, `commit_guard.sh`. Never edit the
   qa copy directly; after syncing, verify with `diff -q`. (`mutate.py`,
   `hotspots.py`, `metrics.py` are review-only; `qa_metrics.py`,
   `plan_round.py`, `nfr_*`, `provision_workers.sh`, `merge_coverage.py` are
   qa-only.)
3. **`CONTROLS.md` at repo root is canonical** and is cp-synced into both loop
   plugins (shipped so `/…:controls` works in-session). Any time a knob, verb,
   or policy changes, update the root copy and re-sync both.
4. **Validation sweep before every commit**: `python3 -m json.tool` on all
   JSON, `ast.parse` on all `.py`, `bash -n` on all `.sh`, and grep for
   absolute `/Users/` paths (none allowed — everything must route through
   `${CLAUDE_PLUGIN_ROOT}` or per-repo state dirs).
5. **Smoke-test every behavioral change against the exact reported failure
   before shipping**, in a scratch directory outside the repo. This habit has
   caught shipped-bug candidates repeatedly (simulator device-type ordering,
   region prefix-matching, set-usage accumulation). When testing Python that
   was just edited, set `PYTHONDONTWRITEBYTECODE=1` — a stale `.pyc` once
   masked a file restore.
6. **Keep the "(measured: …)" style in agent prompts.** Rules that carry their
   originating incident and numbers are followed better; field agents have
   explicitly cited them. Same for the READMEs' WATCH LIST guidance: lead with
   behavior changes, not internals.

## 3. Design decisions that look wrong but are settled

Each of these was litigated with field evidence. Don't "fix" them without new
evidence:

- **Seed merges as round 0** (review) and **implemented_rounds gating** (qa):
  discovery rounds are net-negative by construction and were poisoning
  thrashing/diminishing detection.
- **`set-usage` REPLACES, `add-usage` accumulates.** The old accumulate-only
  behavior inflated one budget readout by 89%.
- **Harness-reported subagent token figures are workload-dependent floors**:
  roughly 4–7× below effective tokens for code loops, ~11× for simulator
  loops. Budgets are set on the *reported* scale on purpose.
- **fixed→partial is refinement, not a reopen**; reopen means fixed→open only.
  Converging severity series are exempt from churn/thrashing counting.
- **Archive directories are named by the *archived* loop's scope sha** (this
  flip-flopped twice before settling in 0.9.0).
- **Minors split by risk**: `fix_risk`-flagged minors ride round briefs; plain
  minors wait for closeout.
- **Closeout discipline**: smallest correct fix; `verify_cmd` must actually
  RUN every touched test target (build-for-testing alone is not verification);
  an `introduced_by_fix` blocker gets one extra dispatch, otherwise the loop
  ends "done-but-red" with the failure reported honestly. Closeout failed
  three different ways in the field before 0.9.0 — treat this area as fragile.
- **The fix-reviewer's verdict is not terminal.** Testers have overturned its
  accept/reject on-device three times. Never "optimize" by trusting it as a
  gate; it feeds the ledger, the tester confirms.
- **Model pins**: ux-tester and skeptical-reviewer = opus, fix-reviewer =
  sonnet, implementers = inherit. The point is *diversity* — pinned agents
  must stay distinct from each other and from the session model (Peter runs
  the orchestrating session on Fable, so inherit ≠ any pin). Never override
  pins in dispatch prompts.
- **Unsound-fix verdicts revert the finding to open** (chosen deliberately,
  with "reassess if sonnet proves trigger-happy" — rejection rate is a watch
  item, and every revert must be flagged to the human).
- **All ledger/report/planning mutations go through the scripts**
  (`merge_ledger.py` verbs, `qa_metrics.py`/`metrics.py`, `plan_round.py`,
  `render_report.py`). The orchestrator is plumbing; if an orchestrator is
  hand-editing `findings.json` or `rounds.md`, that's a bug in the skill
  wording, not a shortcut to bless.

## 4. Cost doctrine (measured, don't re-derive)

- Effective tokens = `input×1 + cache_read×0.1 + cache_write×2 + output×5`
  (dedup by requestId; images ≈ flat 1600). The field agents' measurement
  scripts live in their own repos.
- **Cost is turns × context.** Cache reads are 98–99% of raw tokens;
  thinking/output are ~1–7%; screenshots ~2.6%. Cutting thinking, screenshots,
  or verification depth saves almost nothing and was explicitly rejected.
- The **do-not-cut list**: reviewer verification depth, mutation re-runs,
  extended thinking, tester exploration. Savings come from fewer/shorter
  turns, scoping, fresh sessions (a fresh orchestrator session measured 3.3×
  cheaper than a continued one), and cheaper models on verifiable roles.
- Shipped Tier 1 measured −38% on agent cost and ~2.5× on orchestrator;
  scoped review runs at 165–197K effective per finding vs a 323K baseline.

## 5. Agreed roadmap, not yet built

The cost-reduction proposal lived as a claude.ai artifact on the previous
account (rev 3, items A–I shipped) — **artifacts do not transfer between
accounts**, so its remaining content is summarized here:

- **Tier 2 — sonnet `ux-verifier`**: a cheaper verifier agent for
  confirmation passes, targeted re-tests, smoke passes, and the power-user
  persona; escalates to opus on any failure or uncertainty; 15% of its passes
  get an opus audit sample; auto-revert the whole tier if disagreement exceeds
  ~10%. Also: pin `regression-test-writer` to sonnet (mechanical, verifiable
  work). **Prerequisite**: one measured qa-loop run on the current version to
  establish the baseline.
- **Tier 3 (parked)** — compiled XCUITest replays: machine-readable per-TC
  step lists plus a replay runner, so re-verification is a compiled test run
  instead of an agent driving the simulator. The `.qa-loop/tools/` persistence
  convention is the stepping stone (agents already build ad-hoc drivers).
  Only worth it at a steady testing cadence.
- **Experiments deferred pending measurement**: a cheaper closeout verifier;
  a persistent reviewer reused across rounds via session resume (cache reads
  at 0.1× vs full re-reads each round).
- **qa-loop has no closeout stage.** Port review's closeout only after the
  review closeout has a clean field record — it was the most failure-prone
  area of the whole system.
- Pre-staged qa items from older feedback: a per-round accessibility-id index
  for testers; a single-command `qa-run.sh` orchestration wrapper.

**Watch items for the next field reports**: closeout verify-targets/red-target
enforcement holding; fix-reviewer rejection (unsound) rate; the new
`consulted` / at-cap "raise max_rounds?" thrashing flow's first real exercise;
HARNESS_NOTES actually staying under its 10KB ceiling; `token_budget` accuracy
now that `set-usage` replaces.

## 6. Environment notes (Peter's machine and habits)

- Peter's shell aliases `rm` to interactive mode — always use `rm -f` /
  `rm -rf` in scripts and commands.
- `gh` CLI is not installed; plain `git push origin main` works.
- Rollback tag `checkpoint-2026-08-14` exists but is old; the granular commit
  history since is the real safety net.
- Plugin pickup ritual after a release (run from a Claude CLI session):
  `/plugin marketplace update quiller`, then `/plugin update
  <plugin>@quiller`, then start a fresh session. The macOS app shares the
  plugin store but only loads plugins at session start.
- Local-iteration shortcut: replace the cache copy with a symlink to the
  working tree — `rm -rf ~/.claude/plugins/cache/quiller/<plugin>/<version> &&
  ln -s <repo>/<plugin> <that path>` — edits then go live next session with no
  reinstall. Remove the symlink before cutting a real release. (Alternatively
  `claude --plugin-dir` per session, as the README notes.)
- Multiple loop sessions share this Mac's simulators — that's why the skills
  have simulator-discipline rules (named `qa-worker-*` devices via
  `provision_workers.sh`, per-chunk resets, device-vanish = stop-and-report).
  Don't weaken those to "simplify".
- When writing release scripts as Python anchor-patches: grep the exact
  current text before asserting on it, and remember a failed assert aborts
  every later patch in the same script — re-run the whole remainder after
  fixing an anchor.

## 7. Working with Peter

- Concise, decisive approvals; expects a proposal (with declines and
  reasoning) before any build; values measured evidence over opinion.
- Wants judgment calls surfaced even when delegated, and human-flags on
  anything the loop decides autonomously (e.g., unsound-fix reverts).
- Commit style: `feat|fix|docs: <plugins+versions> — <driver>`, body carrying
  the evidence, ending with the Claude co-author trailer.
