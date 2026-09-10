# Loop report — .review-loop

**Stop condition:** `backstop` after round 2 — hit max_rounds

**Subagent tokens:** 583,667 across 3 round(s)

**Findings by status:** fixed 15, open 2, partial 1

## Trend

| Round | Blockers | Majors | Minors | Closed | New | Reopened | Promoted | Net | Tokens | Decision |
|-------|----------|--------|--------|--------|-----|----------|----------|-----|--------|----------|
| 1 | 0 | 2 | 3 | 9 | 1 | 0 | 0 | +8 | 162049 | continue |
| 2 | 0 | 1 | 3 | 3 | 2 | 0 | 0 | +1 | 94825 | backstop |

## Tokens (reported — measured 4-7x below billed effective)

| Round | By role | Total |
|---|---|---:|
| 0 | panel-verifier 90,004; reviewer 77,456 | 167,460 |
| 1 | implementer 95,013; reviewer 67,036 | 162,049 |
| 2 | implementer 92,330; panel-verifier 64,683; reviewer 97,145 | 254,158 |
| **all** | | **583,667** |

## Panel (multi-provider reviewers)

_Per-lane precision — the drop-or-keep signal. Rejected candidates are counts only; confirmed ones appear among the findings tagged `via panel:<lane>`._

| Round | Lane | Filed | Confirmed | Demoted | Rejected | Kept rate |
|---|---|---:|---:|---:|---:|---:|
| 0 | ollama | 10 | 0 | 1 | 9 | 1/10 |
| final | ollama | 10 | 0 | 0 | 10 | 0/10 |

## Open findings by severity

### minor (3)

- **minor/panel_review.py:probe-smoke-diverges-from-run** — minor, partial; region `review-loop-tools/scripts/panel_review.py:132-141`; fix_risk `Threading the configured model into --smoke changes what the setup gate actually calls and can turn a currently-green gate red; it is user-visible probe behavior.`
  - probe --smoke did not exercise the invocation/model the run path uses, so a green setup gate did not mean the lane works (a model the account cannot access gates green, then fails every round).
  - note: CORE FIXED, ONE EDGE REMAINS -> BACKLOG. Verified: probe() now defaults to os.path.join('.review-loop','panel.json') when no arg (panel_review.py:140-141); the selftest drives the documented bare probe(['--smoke']) from a temp cwd and asserts the configured model 'o4-max' reached the real runner and codex.smoke=='ok' (panel_selftest.py:246-259); mutant probe-default-panel-path-reverted KILLED (errors 0). Secondary cwd divergence is moot in the documented path (probe from repo root => os.getcwd() == run's repo). REMAINING EDGE: on FIRST setup the documented order is probe THEN write panel.json (SKILL.md:111-120 — 'To offer it: ... probe --smoke and present the available lanes ... Record the answer in TWO files'), so at probe time .review-loop/panel.json does not yet exist and the model the human just chose is still never smoked — exactly the failure the fix's own comment (panel_review.py:135-139) cites. The fix therefore only covers re-probes of an already-configured checkout. Cheap BACKLOG fix: one line in SKILL.md step 2b telling the orchestrator to re-run `probe --smoke` after writing panel.json (and have probe state in its output when it found no panel.json and is smoking CLI defaults).
- **correctness/panel_review.py:probe-crash-on-malformed-panel-json** — minor, open; region `review-loop-tools/scripts/panel_review.py:132-142`; fix_risk `Swallowing the parse error changes probe's shipped output/exit status at the setup gate (silently smoking CLI defaults vs failing loudly), so the fix must print an explicit 'panel.json unreadable' row rather than fall back silently.`; introduced_by_fix
  - The new default panel path makes bare `panel_review.py probe [--smoke]` read .review-loop/panel.json unguarded, so a truncated or hand-edited panel.json aborts the setup gate with a raw json.decoder.JSONDecodeError traceback and a nonzero exit instead of reporting lane availability. Before this closeout, bare probe never touched the file and was immune; the gate is precisely where a human has just hand-written panel.json, so malformed JSON is the likely case, and the traceback names no remedy.
  - evidence: `review-loop-tools/scripts/panel_review.py:140-141`, `review-loop-tools/scripts/panel_review.py:64-68`, `review-loop-tools/scripts/panel_review.py:428-433`
  - note: CONFIRMED by execution: in a scratch dir containing .review-loop/panel.json = '{"lanes": [ broken', `python3 panel_review.py probe` exits nonzero with a full JSONDecodeError traceback (main() at :428-433 has no try). load_json (:64-68) only guards nonexistence, not malformed content. Fix: try/except around the default-path load, emit {"panel": "unreadable: <err>"} into the probe output and continue with panel=None.
- **tests/CONTROLS.md:mirror-sync-unenforced** — minor, open; region `review-loop-tools/tests/panel_selftest.py:1-30`
  - HANDOFF.md:68-70 makes repo-root CONTROLS.md canonical and requires a manual cp-sync into both loop plugins, but nothing in the repo verifies it: no test, no guard script and no pre-commit check compares the three copies. That unenforced convention is exactly what produced the round-2 major (two of three copies shipped the withdrawn git-tracked-consent design for a full loop), and the closeout re-synced by hand without adding any guard, so the next doc edit drifts the same way.
  - evidence: `HANDOFF.md:68-70`, `CONTROLS.md:1`, `qa-loop-tools/CONTROLS.md:1`, `review-loop-tools/CONTROLS.md:1`
  - note: CONFIRMED: grep for 'CONTROLS.md' across all *.py and *.sh in the repo matches only nothing outside the docs themselves (commit_guard.sh does not check it), and `find -name CONTROLS.md` returns exactly the three copies. BACKLOG fix is three lines: assert md5(root) == md5(qa) == md5(review) in panel_selftest.py (or in commit_guard.sh, which already runs pre-commit).

## Disputed (agree-to-disagree)

_none_

## Fix review rejections

- **minor/panel_review.py:probe-smoke-diverges-from-run** (partial) — round 2: panel_lane_for is never reached: SKILL.md:112 / CONTROLS.md:233 invoke `probe --smoke` with no panel.json path, so panel is None and the configured model is still not threaded.

## Severity changes

_none_

## Closeout

- **minor/panel_review.py:probe-smoke-diverges-from-run** — partial; CORE FIXED, ONE EDGE REMAINS -> BACKLOG. Verified: probe() now defaults to os.path.join('.review-loop','panel.json') when no arg (panel_review.py:140-141); the selftest drives the documented bare probe(['--smoke']) from a temp cwd and asserts the configured model 'o4-max' reached the real runner and codex.smoke=='ok' (panel_selftest.py:246-259); mutant probe-default-panel-path-reverted KILLED (errors 0). Secondary cwd divergence is moot in the documented path (probe from repo root => os.getcwd() == run's repo). REMAINING EDGE: on FIRST setup the documented order is probe THEN write panel.json (SKILL.md:111-120 — 'To offer it: ... probe --smoke and present the available lanes ... Record the answer in TWO files'), so at probe time .review-loop/panel.json does not yet exist and the model the human just chose is still never smoked — exactly the failure the fix's own comment (panel_review.py:135-139) cites. The fix therefore only covers re-probes of an already-configured checkout. Cheap BACKLOG fix: one line in SKILL.md step 2b telling the orchestrator to re-run `probe --smoke` after writing panel.json (and have probe state in its output when it found no panel.json and is smoking CLI defaults).
- **tests/panel_selftest.py:no-assertion-consent-not-read-from-panel-json** — fixed; VERIFIED FIXED. The fixture panel.json now embeds consent in BOTH withdrawn shapes (nested `consent` object and top-level `remote_lanes_approved`/`cmd_lanes_approved`), and the cmd list holds the real sha256 of good_cmd plus the exact strings of the failcmd/tampered lanes (panel_selftest.py:56-66) — so any fallback flips the assertions rather than passing vacuously. Asserted at :87 (load_consent(loop) == {}) and end-to-end at :92 (good AND tampered still skipped). Mutation run confirms: mutant load-consent-panel-json-fallback-rearmed KILLED, errors 0, mismatches 0. Full suite rerun by me: ALL 36 CHECKS PASSED.
- **docs/CONTROLS.md:consent-design-not-propagated-to-mirror-copies** — fixed; VERIFIED FIXED by hash: all three copies now md5 46eca2faf37a65d0cff3d919e752bed9 (root, qa-loop-tools, review-loop-tools), matching the implementer's claim, and the shared text carries the untracked panel-consent.json design, the cmd_lanes_approved exact-string/digest list, the command-STRING-not-file-contents caveat, and the loopback OLLAMA_HOST caveat. find shows exactly three CONTROLS.md in the tree, so no fourth copy drifted. review-loop-tools/README.md:83-89 independently documents the untracked file correctly (it never mentions cmd lanes, so nothing to sync there).
- **security/panel_review.py:cmd-consent-hash-covers-invocation-not-script** — fixed; VERIFIED FIXED as scoped (doc-only was my own round-2 scoping). The caveat is present in all five places claimed: module docstring panel_review.py:34-37, SKILL.md:125-128 (explicitly at the consent prompt: 'Tell the human at the consent prompt'), and all three CONTROLS.md copies (identical md5). RESIDUAL, deliberately punted to BACKLOG: cmd_approved() still hashes only the invocation, so the technical exposure is unchanged — a human who approves `bash tools/lane.sh` still gets unattended execution of whatever that file becomes. BACKLOG item: hash the contents of any local file named in an approved cmd, or refuse cmds that reference repo-relative script paths.
- **correctness/panel_review.py:probe-crash-on-malformed-panel-json** — open; CONFIRMED by execution: in a scratch dir containing .review-loop/panel.json = '{"lanes": [ broken', `python3 panel_review.py probe` exits nonzero with a full JSONDecodeError traceback (main() at :428-433 has no try). load_json (:64-68) only guards nonexistence, not malformed content. Fix: try/except around the default-path load, emit {"panel": "unreadable: <err>"} into the probe output and continue with panel=None.
- **tests/CONTROLS.md:mirror-sync-unenforced** — open; CONFIRMED: grep for 'CONTROLS.md' across all *.py and *.sh in the repo matches only nothing outside the docs themselves (commit_guard.sh does not check it), and `find -name CONTROLS.md` returns exactly the three copies. BACKLOG fix is three lines: assert md5(root) == md5(qa) == md5(review) in panel_selftest.py (or in commit_guard.sh, which already runs pre-commit).

## Wontfix / resolved

_none_

## WATCH LIST

_The part a human should actually read. Candidates below are mechanical; the orchestrator fills each "look here because". Lead with any shipped BEHAVIOR CHANGE: convergence means two same-family agents agreed — not that the change is correct._

- **minor/panel_review.py:ollama-num-ctx-silent-clamp** (fix_risk behavior: either the lane must start erroring/skipping or the result gains a truncation flag the verifier reads) — look here because: the fix made an oversized prompt a hard lane error instead of a silent head-drop; a big diff that previously "worked" (badly) now skips the ollama lane entirely — confirm that trade is what you want for long diffs.
- **minor/panel_review.py:run-range-flag-unimplemented** (fix_risk behavior: implementing --range makes run() materialize diffs it currently never touches) — look here because: the fix chose to DELETE --range from the docs rather than implement it; if you had workflows passing --range, they now silently rely on a pre-materialized diff.
- **minor/panel_review.py:enabled-flag-unimplemented** (fix_risk behavior: honoring enabled changes which lanes run) — look here because: `"enabled": false` in panel.json now actually skips a lane; any config that carried the flag decoratively changes behavior on upgrade.
- **minor/panel_review.py:probe-smoke-diverges-from-run** (fix_risk Threading the configured model into --smoke changes what the setup gate actually calls and can turn a currently-green gate red; it is user-visible probe behavior.) — look here because: still only PARTIAL — on first-time setup the documented probe-then-configure order means the chosen model is never smoked; the one-line SKILL.md reorder is in BACKLOG.md.
- **tests/panel_selftest.py:no-assertion-consent-not-read-from-panel-json** (introduced by a fix) — look here because: the consent-isolation guarantee (tracked panel.json can never authorize) now rests on these selftest assertions; if the fixture is ever "simplified" the guarantee goes unwatched again.
- **docs/CONTROLS.md:consent-design-not-propagated-to-mirror-copies** (introduced by a fix) — look here because: fixed by hand-resync only — the cp-sync convention is still unenforced (BACKLOG), so the next CONTROLS.md edit can re-ship contradictory consent docs the same way.
- **security/panel_review.py:cmd-consent-hash-covers-invocation-not-script** (introduced by a fix) — look here because: closed as a doc caveat, not a technical fix — approving `bash ./lane.sh` still executes whatever lane.sh later becomes; decide whether script-content pinning (sketched in BACKLOG.md) is worth building before anyone uses cmd lanes in anger.
- **correctness/panel_review.py:probe-crash-on-malformed-panel-json** (fix_risk Swallowing the parse error changes probe's shipped output/exit status at the setup gate (silently smoking CLI defaults vs failing loudly), so the fix must print an explicit 'panel.json unreadable' row rather than fall back silently., introduced by a fix) — look here because: OPEN, introduced by the closeout's own probe-default-path fix and confirmed by execution — a hand-edited panel.json with a typo turns the setup gate into a raw traceback; small guarded-load fix specified in the finding note.
- **seed scope** `pre-multi-provider-panel..HEAD` — 14 files, 1376 lines; largest: `review-loop-tools/scripts/panel_review.py` (+436/-0), `review-loop-tools/tests/panel_selftest.py` (+270/-0), `docs/proposal-multi-provider-review-panel.md` (+164/-65) — look here because: this is the panel feature itself — 8 of 13 seed findings were majors here, concentrated in consent/egress gating and lane error handling; panel_review.py is brand-new code with no production miles.
- **round 1 diff** `9a02914..f6a9936` — 9 files, 452 lines; largest: `review-loop-tools/scripts/panel_review.py` (+135/-61), `review-loop-tools/tests/panel_selftest.py` (+162/-0), `review-loop-tools/skills/review-loop/SKILL.md` (+17/-9) — look here because: the most invasive round — it MOVED the consent contract (git-tracked panel.json → untracked panel-consent.json, a deliberate breaking change), rewrote extract_json, and touched the subagent_guard namespace; both agents agreed this design is right, which is exactly what the loop can't self-check.
- **round 2 diff** `f6a9936..HEAD` — 7 files, 308 lines; largest: `review-loop-tools/tests/panel_selftest.py` (+124/-16), `review-loop-tools/scripts/panel_review.py` (+74/-16), `qa-loop-tools/CONTROLS.md` (+17/-6) — look here because: security-critical rewrites of is_loopback() (ipaddress-based) and cmd consent binding (sha256 list, legacy boolean deliberately rejected — another breaking change) plus the closeout doc resync; the reviewer probed 22 host forms but IPv6/hosts-file corner cases beyond those are untested.
