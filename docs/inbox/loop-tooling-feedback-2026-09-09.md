# qa-loop-tools 0.12.0 feedback — 2026-09-09 run

Run shape: max_rounds=4 / parallel_testers=3 requested; round 1 full (85
cases), round 2 targeted (28), round 3 cut short by user wrap-up after the
blocker verification. 42 findings, 16 fixed-verified, 1 blocker found and
fix-verified. 4.53M reported subagent tokens. review-loop-tools 0.10.0 was
not run this session (its updated .gitignore convention was adopted; see
repo-versioning note).

## What worked notably well in 0.12.0

- **The default-closed allowlist `.gitignore` convention** ("conclusions in
  git, evidence on disk") worked exactly as documented: 84 conclusion files
  committed, zero evidence/fragments/briefs leaked into the index, hygiene
  check clean at both ends. Adopting it repo-wide (un-ignoring the loop dirs)
  was painless.
- **plan_round's DEGENERATED reduction** (round 2: diff touched >60% of
  cases → findings+smoke, 26 cases) is a big cost saver and made targeted
  rounds genuinely targeted despite per-workflow commits touching everything.
- **Coverage manifest + persona matrix**: 85/85 accounting with 3
  reasoned blocked cases; nothing silently dropped.
- **fix-reviewer earned its keep twice**: caught the implementer's
  unilateral wontfix on a confirmed accessibility defect (round 1) and
  validated the subtle WF-9b blocker diagnosis rather than rubber-stamping
  it (round 2). Zero unsound fixes shipped.
- **notes-rotate mostly held the HARNESS_NOTES ceiling** across ~30
  dispatches, and the notes demonstrably saved turns (anchor drift,
  toggle-dwell, landscape coordinate recipes reused across chunks).
- **provision_workers.sh completed cleanly (~5 min)** — a real improvement
  over the 2026-08 hangs.
- **regression-test-writer's archive sweep** found 15 previously-fixed,
  unguarded bugs across three archived ledgers and guarded 5 of them —
  exactly the intended value.

## Defects / friction, in impact order

1. **Worker recreation destroys per-device MCP grants (cost: the whole
   parallel lane).** provision_workers.sh deletes and recreates workers, so
   the new UDIDs had no simulator-input grants; all three wave-1 testers
   were refused every tap ("awaiting a response") with the user away, and
   the run had to fall back to sequential on the one granted device.
   Stage 0's "verify the control tools reach subagents" checks tool
   AVAILABILITY, not per-DEVICE grants — the docs conflate them. Fixes:
   reuse existing workers when present (don't delete), surface the grant
   state per-udid at provision time, and make Stage 0's check a real tap on
   each worker BEFORE the first dispatch wave.
2. **plan_round's chunker silently drops WF-9b** (letter-suffixed region
   id): its TCs appear in `selected` and in open-findings targeting, but no
   chunk contains them — all three rounds needed a hand-built manual chunk.
   Without that, the blocker living in WF-9b would never have been found.
   Lint passes, so nothing warns. The chunker's region parser needs the
   `WF-\d+[a-z]?` form, and lint should assert every selected TC lands in
   exactly one chunk.
3. **Evidence directories collide across loops.** `archive` leaves
   `evidence/` in place while round numbering restarts, so this run's
   `evidence/round-1/<slug>/` arrived holding ~35 prior-loop PNGs with the
   same TC names; three testers independently spent turns discovering this
   and defensively prefixing filenames. Archive should move `evidence/round-*`
   into the archive dir (WORKFLOWS/TESTCASES/tools carrying over is right;
   stale evidence is not).
4. **notes-rotate won't always enforce its own ceiling**: with many small
   sections it reported over_ceiling:true and rotated 0 sections repeatedly
   (10.2-12.1 KB); the orchestrator had to archive sections manually.
   Probably a per-section size floor — it should archive oldest sections
   until under, unconditionally.
5. **regression-test-writer refuses pbxproj edits even when the dispatch
   relays explicit user authorization**, leaving its (good) tests orphaned
   in `.qa-loop/regression-tests/`; the orchestrator had to route the
   wiring through qa-implementer. The agent boundary should bend to an
   explicit user grant, or the skill should document the implementer
   hand-off as the intended path.
6. **Minor**: `set-usage` prints `round_tokens` meaning the ROUND total
   (confusing next to a per-role call); the report's stop-condition line
   can't express "user abort" (hand-edited this run); `qa_metrics` counts a
   tester-reported still-open finding as neither reopened nor new (correct
   but the trend table then under-reads round 2's churn); no built-in "plan
   summary" printer (orchestrators re-parse the plan JSON by hand).

## Environmental facts this run surfaced (for HARNESS_NOTES posterity)

- Open-Meteo archive API 429-rate-limits this host after heavy loop use
  ("try again tomorrow"), which stalls deep history at ~26 days, keeps
  Monthly/Yearly gated off, and makes unknown-UV states unreachable — three
  test legs blocked on quota, not code. The proposed `-uiTestPinCoverageDays`
  hook would decouple the suite from the quota.
- The desktop-app harness forced no dispatch into the background; foreground
  parallel dispatch worked (wave 1) despite the grant failures.

## Verdict

0.12.0 is a substantial step up from the 0.10/0.11 runs (allowlist
versioning, degenerated targeting, archive sweep, sturdier notes-rotate).
The two things that actually threatened this run's integrity were #1
(parallelism silently dead on arrival) and #2 (a workflow silently
untested); both are cheap to fix and both would have been invisible without
manual cross-checks.
