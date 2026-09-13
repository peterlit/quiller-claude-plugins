# HANDOFF — maintainer's guide

Written 2026-09-07 for whoever (human or Claude session) picks up maintenance of
this repo next. The repo itself is complete and self-describing at the *what*
level (READMEs, CONTROLS.md, the SKILL.md files, and a rationale-dense git log).
This file captures the *how we work* knowledge that previously lived only in
the maintaining session's conversation history.

State as of this writing (updated 2026-09-13): `review-loop-tools 0.13.0`,
`qa-loop-tools 0.14.0`, `arch-docs-tools 0.1.0`, all committed and pushed to
`github.com/peterlit/quiller-claude-plugins`, working tree clean. The 0.13.0
pair digested the 2026-09-09 field reports (two qa 0.12.0 runs + one review
0.10.0 run — see `docs/inbox/` and `docs/proposal-2026-09-09-field-reports.md`);
qa 0.14.0 shipped the driver contract + `ios-xcuitest` backend.

---

## 1. How this project actually works — the loop behind the loops

This marketplace is developed by a **measured field-feedback cycle**, and that
process is the most important thing to preserve:

- **Field agents** are separate Claude sessions Peter runs against real
  codebases: *agent 1* works in `~/Documents/src/weatherapp`, *agent 2* in
  `~/Documents/src/cardgame` (an app codenamed "Causeway"). They run the
  plugins for real, then write feedback memos and token-usage studies into
  their own repos (`weatherapp/docs/reports/`, `cardgame/docs/`). Delivered
  copies now land in this repo's `docs/inbox/` and get committed alongside the
  proposal they produced (the field repos remain the raw archive — and they
  are on this same Mac, so you can usually READ referenced material in place,
  e.g. the Causeway driver source, instead of asking for a delivery).
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
   `.claude-plugin/marketplace.json` never carry versions. Related: the
   loop-dir `.gitignore` allowlist templates embedded in the two SKILL.md
   bootstrap steps carry a `Managed by <plugin> vX.Y.Z` stamp naming the
   release that last changed the template — when a release adds a new
   durable output name, add its negation to the template and update the
   stamp in the same release (the definition of "conclusion" stays versioned
   with the code that produces it).
2. **Shared scripts are authored in `review-loop-tools/scripts/` and mirrored
   to `qa-loop-tools/scripts/`**: `merge_ledger.py`, `render_report.py`,
   `loop_guard.sh`, `subagent_guard.sh`, `read_guard.sh`, `dispatch_stamp.sh`,
   `session_guard.sh`, `commit_guard.sh`. CAVEAT (since 0.11.0's panel):
   `merge_ledger.py`, `render_report.py`, and `subagent_guard.sh` are no
   longer byte-identical — the review copies carry panel-only additions
   (panel-tally, the Panel report section, the panel-namespace guard note).
   The rule now: apply every shared change IDENTICALLY to both copies in the
   common regions, and keep the divergence panel-only; `diff` between the
   copies must show nothing but panel code. (Resolving this properly — port
   the panel to qa or add per-plugin section filtering — is a standing
   BACKLOG item.) `mutate.py`, `hotspots.py`, `metrics.py`, `panel_review.py`
   are review-only; `qa_metrics.py`, `plan_round.py`, `nfr_*`,
   `provision_workers.sh`, `merge_coverage.py` are qa-only.
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
7. **Driver backends live in `qa-loop-tools/drivers/<backend>/`** (first:
   `ios-xcuitest`). The platform-neutral verb contract is documented in
   CONTROLS.md ("Driver backends") and in each backend's README; skill and
   tester text speak only contract verbs. NEVER build inside the plugin
   cache — the skill copies the backend to `.qa-loop/driver/` and builds
   there (`dd/` cache, ignored by the allowlist). Nothing app-specific goes
   into a backend; app quirks belong in the target repo's HARNESS_NOTES.md.
8. **Keep THIS file current — in the same commit as the change.** Every
   release updates the state line at the top; any change that touches a
   ritual, a settled decision, the roadmap, or the watch items updates that
   section too. Peter's standing instruction (2026-09-13): HANDOFF.md is
   never allowed to go stale — it is the next maintainer's only inheritance.

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
  work). **Prerequisite SATISFIED (2026-09-09)**: agent 2's measured 40.1M
  qa-loop run on 0.12.0 is the baseline, and the regression writer is now the
  #2 cost center (7.2M for 49 tests). Needs its own numbered proposal next.
- **Tier 3 (closer than it was)** — compiled XCUITest replays: per-TC step
  lists plus a replay runner, so re-verification is a compiled test run
  instead of an agent driving the simulator. The shipped `ios-xcuitest`
  driver backend (0.14.0) IS the stepping stone HANDOFF used to name
  hypothetically — its `qa.py --batch` mode already replays a command list.
  Still only worth it at a steady testing cadence.
- **Experiments deferred pending measurement**: a cheaper closeout verifier;
  a persistent reviewer reused across rounds via session resume (cache reads
  at 0.1× vs full re-reads each round).
- **qa-loop has no closeout stage.** Port review's closeout only after the
  review closeout has a clean field record — it was the most failure-prone
  area of the whole system. (First good record: the 2026-09-09 review run's
  closeout fixed the remaining major and re-verified it; one more clean run
  and the port is arguable.)
- Pre-staged qa items from older feedback: a per-round accessibility-id index
  for testers; a single-command `qa-run.sh` orchestration wrapper.

**Watch items for the next field reports** (post-0.13.0/0.14.0): the shipped
driver building and serving on a field rig (first non-Causeway app); the
Stage-0 grant probe catching an ungranted worker BEFORE wave 1; namespaced
worker reuse actually preserving grants across loops; a `WF-<n><letter>`
workflow chunking cleanly; the notes byte-ceiling holding (and whether 10KB
default needs raising once driver recipes accumulate); `converged-in-closeout`
appearing on a scoped run instead of a "thrashing" headline; archive's
sync-conflict check firing (or staying quiet) on the iCloud repo;
`arm-when-green` flake rate; the minors-only `full_pass_required` implementer
dispatch not being abused for majors. Still standing from before:
fix-reviewer rejection (unsound) rate; closeout verify-targets/red-target
enforcement.

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
