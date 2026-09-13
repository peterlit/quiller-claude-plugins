# Loop report — .review-loop

**Stop condition:** `converged` after round 4 — no open blockers or majors; none newly introduced

**Subagent tokens:** 757,618 across 5 round(s)

**Findings by status:** fixed 21, open 3, wontfix 2, partial 1

## Trend

| Round | Blockers | Majors | Minors | Closed | New | Reopened | Promoted | Net | Tokens | Decision |
|-------|----------|--------|--------|--------|-----|----------|----------|-----|--------|----------|
| 1 | 1 | 3 | 2 | 9 | 2 | 0 | 0 | +7 | 137653 | continue |
| 2 | 0 | 3 | 1 | 2 | 0 | 0 | 0 | +2 | 151965 | continue |
| 3 | 0 | 1 | 1 | 2 | 1 | 0 | 0 | +1 | 119403 | continue |
| 4 | 0 | 0 | 2 | 2 | 2 | 0 | 0 | +0 | 156720 | converged |

## Tokens (reported — measured 4-7x below billed effective)

| Round | By role | Total |
|---|---|---:|
| 0 | reviewer 24,815 | 24,815 |
| 1 | implementer 76,192; reviewer 61,461 | 137,653 |
| 2 | implementer 80,056; reviewer 71,909 | 151,965 |
| 3 | implementer 60,407; reviewer 58,996 | 119,403 |
| 4 | implementer 111,973; panel-verifier 86,214; reviewer 125,595 | 323,782 |
| **all** | | **757,618** |

## Panel (multi-provider reviewers)

_Per-lane precision — the drop-or-keep signal. Rejected candidates are counts only; confirmed ones appear among the findings tagged `via panel:<lane>`._

| Round | Lane | Filed | Confirmed | Demoted | Rejected | Kept rate |
|---|---|---:|---:|---:|---:|---:|
| final | codex | 4 | 3 | 0 | 1 | 3/4 |
| final | gemini | 8 | 3 | 2 | 3 | 5/8 |

## Open findings by severity

### major (1)

- **security/panel_review.py:consent-xdg-inside-checkout** — major, partial; region `review-loop-tools/scripts/panel_review.py:114-137`; introduced_by_fix; via panel:codex
  - consent_path() honors XDG_CONFIG_HOME without checking it lies outside the reviewed checkout: a relative value resolves against the process cwd and an absolute value can point inside the repo, relocating the 'machine-local, repo-cannot-carry-it' consent store back under repo control, so a clone or unpacked bundle shipping the correctly hash-named consent file re-arms the bundled-archive egress/shell attack the round-4 consent redesign closed.
  - evidence: `review-loop-tools/scripts/panel_review.py:129-137`
  - note: Panel final-pass finding, minted into the ledger at closeout. CLOSEOUT: RELATIVE half fixed and verified -- panel_review.py:130-134 ignores a non-absolute XDG_CONFIG_HOME, says so on stderr, falls back to ~/.config; selftest asserts both the fallback and the stderr line. PARTIAL: the second half of the panel's claim is untouched -- an ABSOLUTE XDG_CONFIG_HOME that resolves inside the reviewed checkout (e.g. XDG_CONFIG_HOME=<repo>/.config) is still accepted verbatim, so the consent store can still sit in a directory a clone/bundle populates. Verified by reading the code: the only test is os.path.isabs(). No iteration follows -- routes to BACKLOG. Cheap containment if picked up: reject a base whose realpath is under the loop dir's repo root (os.path.commonpath), same fail-to-~/.config treatment.

### minor (3)

- **correctness/panel_review.py:severity-missing-still-dropped** — minor, open; region `review-loop-tools/scripts/panel_review.py:370-385`; fix_risk `True`; via reviewer
  - sanitize() still silently discards any candidate whose 'severity' key is absent, blank, or non-string (sev normalizes to '' and falls through the `continue`), even when claim and evidence are well-formed -- the same silent-loss failure the closeout just fixed for out-of-vocabulary severity STRINGS, and the most common shape of LLM sloppiness. The lane then reports filed:0 with no diagnostic anywhere, so a lane that found real issues looks like a lane that found nothing.
  - evidence: `review-loop-tools/scripts/panel_review.py:375-382`
  - note: CONFIRMED live at closeout: sanitize({'findings':[{'claim':'c','evidence':['a:1']}]}) -> filed 0; same for severity:2 and severity:'  '. The closeout's own rationale ('the verifier adjudicates severity anyway') applies identically here, so the fix is internally inconsistent. fix_risk: clamping would change what reaches the verifier. No iteration follows -- routes to BACKLOG.
- **portability/panel_review.py:killpg-windows-attributeerror** — minor, open; region `review-loop-tools/scripts/panel_review.py:543-562`; via panel:gemini
  - run_cmd's timeout path calls os.killpg, which does not exist on Windows, and AttributeError is not in the contextlib.suppress allowlist -- a cmd-lane timeout on Windows raises instead of killing the process group, so the lane reports status=error (caught by run_lane's broad except) and the shell's children are left running.
  - evidence: `review-loop-tools/scripts/panel_review.py:557-560`
  - note: Panel final-pass finding (verifier demoted major->minor: blast radius is one lane, not the script), minted at closeout, NOT actioned by the closeout. CONFIRMED by reading panel_review.py:557-560: suppress covers only ProcessLookupError/PermissionError, and start_new_session is also POSIX-only. Windows is de facto unsupported for cmd lanes; the whole tool is otherwise POSIX-shaped (shell=True quoting, ~/.config). Routes to BACKLOG -- fix is one line (guard on hasattr(os,'killpg') else p.kill()) if Windows support is ever claimed.
- **correctness/panel_review.py:run-status-shape-lacks-lanes** — minor, open; region `review-loop-tools/scripts/panel_review.py:652-701`; via panel:gemini
  - run() prints three different top-level JSON shapes and exits 0 for all of them: {status: panel-unreadable|no-panel, note} carries no 'lanes' key, so a caller that reads ['lanes'] off a zero-exit run crashes with KeyError instead of seeing a skipped panel.
  - evidence: `review-loop-tools/scripts/panel_review.py:663-676`, `review-loop-tools/scripts/panel_review.py:699-701`
  - note: Panel final-pass finding (verifier demoted major->minor for lack of a demonstrated crashing caller), minted at closeout, NOT actioned. CONFIRMED the three-way shape split by reading the code; also confirmed no in-repo caller indexes ['lanes'] unconditionally -- panel_selftest.py branches on status first, and the only other consumer is the SKILL.md orchestrator LLM. Real cost is contract drift for any future scripted consumer. Routes to BACKLOG; a one-key fix ('lanes': []) in both early-return dicts would make the shape total.

## Disputed (agree-to-disagree)

_none_

## Fix review rejections

- **security/panel_review.py:consent-file-force-added-to-git** (fixed) — round 3: no-.git case closed, but an untracked bundled consent inside ANY unrelated checkout is still honored — cmd lane executed in a live repro
- **security/panel_review.py:consent-xdg-inside-checkout** (partial) — round 4: Claimed 'fixed' at closeout; only the relative-XDG half is closed -- an absolute XDG_CONFIG_HOME resolving inside the reviewed checkout is still accepted verbatim (panel_review.py:129-137), so the panel's claim is half-open.

## Severity changes

_none_

## Closeout

- **docs/SKILL.md:consent-path-verb-unusable-on-fresh-machine** — fixed; CLOSEOUT VERIFIED: consent_path_cmd now os.makedirs(dirname(p), exist_ok=True) and exits 2 with a stderr explanation when the loop dir is absent (panel_review.py:171-180); selftest checks both (93/93 pass, verified writes land in the tempdir XDG, ~/.config/review-loop-tools untouched by the run). Documented order is safe: SKILL.md step 2 creates .review-loop/ledger.json before step 2b calls consent-path, so the new isdir() gate cannot break the scripted flow. Residual (NOT filed): makedirs can raise OSError (read-only or file-shaped $XDG_CONFIG_HOME) and would traceback instead of printing the path -- judged too marginal to file.
- **hygiene/version-strings-stale-at-0.11.0** — fixed; CLOSEOUT VERIFIED: both strings now read 0.12.0 and match plugin.json:3; the rewrite predicate at SKILL.md:81-86 still matches on the version-agnostic phrase 'an earlier "Managed by review-loop-tools" allowlist', so v0.11.0 .gitignore files stay upgradable. Repo-wide grep shows no other review-loop-tools 0.11.0 string except two intentionally historical ones (BACKLOG.md:3 dated entry, docs/proposal-*.md:4) plus the long-stale HANDOFF.md:9 snapshot (0.9.0, pre-existing, out of scope).
- **security/panel_review.py:consent-xdg-inside-checkout** — partial; Panel final-pass finding, minted into the ledger at closeout. CLOSEOUT: RELATIVE half fixed and verified -- panel_review.py:130-134 ignores a non-absolute XDG_CONFIG_HOME, says so on stderr, falls back to ~/.config; selftest asserts both the fallback and the stderr line. PARTIAL: the second half of the panel's claim is untouched -- an ABSOLUTE XDG_CONFIG_HOME that resolves inside the reviewed checkout (e.g. XDG_CONFIG_HOME=<repo>/.config) is still accepted verbatim, so the consent store can still sit in a directory a clone/bundle populates. Verified by reading the code: the only test is os.path.isabs(). No iteration follows -- routes to BACKLOG. Cheap containment if picked up: reject a base whose realpath is under the loop dir's repo root (os.path.commonpath), same fail-to-~/.config treatment.
- **correctness/panel_review.py:lane-name-suffix-self-collision** — fixed; Panel final-pass finding, minted at closeout. CLOSEOUT VERIFIED and the fix is provably complete, not just test-shaped: the suffix branch now also fires when raw matches -[0-9a-f]{8}$ (panel_review.py:583), so every suffixed output ends in '-<8 hex>' and every passthrough output by construction does not -- the two sets are disjoint, and residual collisions need a 32-bit sha256 prefix collision on names with identical 64-char sanitizations. Checked live: safe_lane_name('a.b')='a_b-2e7336dc', re-minted='a_b-2e7336dc-6e11865c'; 'codex'/'gemini' still byte-identical. Cosmetic side effect (not filed): a legit lane named e.g. 'gemini-deadbeef' now gets a suffixed artifact base -- harmless, since consumers read the 'candidates' path out of the run JSON (panel_review.py:650, 701) rather than reconstructing it.
- **correctness/panel_review.py:ollama-show-timeout-unbounded** — fixed; Panel final-pass finding, minted at closeout. CLOSEOUT VERIFIED: run_ollama passes min(timeout, 10) (panel_review.py:501); selftest stubs open_url and asserts the /api/show call carries the lane's 3s. Two honest residuals, neither filed: worst-case lane wall time is now timeout + min(timeout,10) rather than timeout, and a very short lane timeout makes the metadata call fail -> model_ctx None -> the num_ctx clamp guard goes inert for that run (it does warn on stderr, covered by an existing check).
- **correctness/render_report.py:sources-only-attribution-skipped** — fixed; Panel final-pass finding, minted at closeout. CLOSEOUT VERIFIED by reading render_report.py:32-36: the gate is now `source or sources`, and `srcs = f.get('sources') or [f['source']]` cannot KeyError (the or-branch only runs when sources is falsy, which with the new gate implies source is truthy). Empty sources=[] with no source correctly renders no attribution line. Selftest asserts 'via codex+gemini' for a sources-only finding.
- **correctness/panel_review.py:severity-out-of-vocabulary-dropped** — fixed; Panel final-pass finding, minted at closeout. CLOSEOUT VERIFIED for the claim as written: a non-empty out-of-vocabulary STRING now clamps to 'minor' (panel_review.py:377-381); checked live, sanitize() files {'severity':'Warning'} as minor. The adjacent missing/non-string case is still a silent drop and is filed separately as correctness/panel_review.py:severity-missing-still-dropped.
- **correctness/panel_review.py:severity-missing-still-dropped** — open; CONFIRMED live at closeout: sanitize({'findings':[{'claim':'c','evidence':['a:1']}]}) -> filed 0; same for severity:2 and severity:'  '. The closeout's own rationale ('the verifier adjudicates severity anyway') applies identically here, so the fix is internally inconsistent. fix_risk: clamping would change what reaches the verifier. No iteration follows -- routes to BACKLOG.
- **correctness/panel_review.py:consent-key-case-sensitive** — wontfix; Panel final-pass finding, minted at closeout; implementer declined and the argument HOLDS. Case-folding the key would make consent recorded for /repo/A also authorize /repo/a, which on a case-SENSITIVE filesystem (ext4, case-sensitive APFS volumes) are genuinely different loop dirs -- i.e. the cheap fix trades a fail-closed nuisance for a fail-open grant of remote-egress/shell consent. Today's failure mode is a consent miss with lanes skipped and a stderr line naming the consent-path verb, which is recoverable in one command. Any real fix must be filesystem-capability-aware (probe case-insensitivity of the loop dir's volume), which is not worth the surface. Routes to BACKLOG as documentation, not as work.
- **portability/panel_review.py:killpg-windows-attributeerror** — open; Panel final-pass finding (verifier demoted major->minor: blast radius is one lane, not the script), minted at closeout, NOT actioned by the closeout. CONFIRMED by reading panel_review.py:557-560: suppress covers only ProcessLookupError/PermissionError, and start_new_session is also POSIX-only. Windows is de facto unsupported for cmd lanes; the whole tool is otherwise POSIX-shaped (shell=True quoting, ~/.config). Routes to BACKLOG -- fix is one line (guard on hasattr(os,'killpg') else p.kill()) if Windows support is ever claimed.
- **correctness/panel_review.py:run-status-shape-lacks-lanes** — open; Panel final-pass finding (verifier demoted major->minor for lack of a demonstrated crashing caller), minted at closeout, NOT actioned. CONFIRMED the three-way shape split by reading the code; also confirmed no in-repo caller indexes ['lanes'] unconditionally -- panel_selftest.py branches on status first, and the only other consumer is the SKILL.md orchestrator LLM. Real cost is contract drift for any future scripted consumer. Routes to BACKLOG; a one-key fix ('lanes': []) in both early-return dicts would make the shape total.

## Wontfix / resolved

- **security/panel_review.py:cli-lanes-retain-repo-read-access** — ACCEPTED as wontfix on the merits for the codex half: codex exec exposes only --sandbox read-only|workspace-write|danger-full-access, none of which restricts READS, so the empty-jail cwd + scrubbed env really is the best available mitigation and the residual is now stated in the module docstring (panel_review.py:43-46) and CONTROLS.md (all three copies byte-identical, md5 ce2f49cb…, asserted by the selftest). See the new docs finding: the shipped residual text names only codex and asserts 'no tighter flag exists today', which is false for the gemini lane. | Round 4: region untouched by the diff; all 84 selftest checks pass (82 -> 84, hermetic via XDG_CONFIG_HOME into the tempdir - confirmed by reading panel_selftest.py:536-540 and the env= propagation in run_panel/sh).
- **correctness/panel_review.py:consent-key-case-sensitive** — Panel final-pass finding, minted at closeout; implementer declined and the argument HOLDS. Case-folding the key would make consent recorded for /repo/A also authorize /repo/a, which on a case-SENSITIVE filesystem (ext4, case-sensitive APFS volumes) are genuinely different loop dirs -- i.e. the cheap fix trades a fail-closed nuisance for a fail-open grant of remote-egress/shell consent. Today's failure mode is a consent miss with lanes skipped and a stderr line naming the consent-path verb, which is recoverable in one command. Any real fix must be filesystem-capability-aware (probe case-insensitivity of the loop dir's volume), which is not worth the surface. Routes to BACKLOG as documentation, not as work.

## WATCH LIST

_The part a human should actually read. Candidates below are mechanical; the orchestrator fills each "look here because". Lead with any shipped BEHAVIOR CHANGE: convergence means two same-family agents agreed — not that the change is correct._

- **correctness/panel_review.py:sanitize-unhashable-severity-typeerror** (fix_risk changes the candidate-acceptance predicate in sanitize()) — look here because: the acceptance predicate changed twice (round 1 normalization, closeout clamp-to-minor) and is still knowingly inconsistent — missing/non-string severity drops silently (BACKLOG) while unknown strings now file as minor; this decides what external-lane findings you ever see.
- **correctness/panel_review.py:ollama-num-ctx-estimate-imprecise** (fix_risk changes ollama num_ctx sizing/refusal for every local lane run) — look here because: every local-lane run now goes through byte-aware sizing, an /api/show trained-context pre-check, and a post-call truncation raise — three chances to refuse a run that used to (wrongly) succeed; if local lanes start erroring on big diffs, this is why, and max_diff_tokens is the knob.
- **correctness/panel_review.py:ollama-url-trailing-slash** (fix_risk changes the endpoint URL string sent to ollama) — look here because: one-line normalize_url change, verified, low risk — listed only because it alters the wire URL for every ollama call.
- **correctness/panel_review.py:codex-stale-last-message** (fix_risk changes which raw output a codex lane treats as the current run's result) — look here because: the unlink-before-run plus stdout fallback decides which text gets parsed as candidates; a codex CLI update that changes --output-last-message behavior would surface here first.
- **correctness/panel_review.py:codex-out-file-relative-to-jail** (introduced by a fix) — look here because: this was the loop's own blocker — the round-1 jail broke every codex lane and 59/59 tests stayed green because the test mocked the exact failing layer; the lesson (end-to-end stub tests over mocks) is encoded in the new stub-codex selftest, keep it.
- **correctness/panel_review.py:lane-name-collision** (fix_risk True, introduced by a fix) — look here because: sanitized names now grow -8hex suffixes in artifact paths; anything external that expects fragments/panel/round-N-<rawname>.candidates.json must read paths from run's JSON output instead.
- **docs/CONTROLS.md:gemini-residual-understated** (introduced by a fix) — look here because: doc-only, fixed in closeout; the honest statement is that gemini has an unverified -s/--sandbox flag — verifying whether it restricts reads is a cheap future win.
- **docs/SKILL.md:consent-path-verb-unusable-on-fresh-machine** (fix_risk True, introduced by a fix) — look here because: the consent-path verb is the human's one entry point to the new consent store; it now mkdirs and validates the loop dir — try it once on your other machine before relying on the recipe.
- **hygiene/version-strings-stale-at-0.11.0** (fix_risk True, introduced by a fix) — look here because: the "Managed by review-loop-tools vX" line is written into HOST repos' .gitignore files; the upgrade predicate must stay version-agnostic (it did — SKILL.md:81-86) or old loops stop upgrading.
- **security/panel_review.py:consent-xdg-inside-checkout** (introduced by a fix) — look here because: was THE ONE OPEN MAJOR — CLOSED post-loop in a direct pass (commit 907074b: commonpath rejection with realpath both sides + selftest restructure + attack-shaped checks), and the follow-up pass closed the sibling vector through the ~/.config fallback (repo-shipped HOME → consent_path returns None, hard fail-closed). Residual and remaining hardening ideas live in BACKLOG.md.
- **correctness/panel_review.py:lane-name-suffix-self-collision** (introduced by a fix) — look here because: closed in closeout with a disjointness argument (suffixed set always ends -8hex, passthrough never does) — the rare kind of fix that's provably complete; nothing to do, listed for the record.
- **correctness/panel_review.py:severity-missing-still-dropped** (fix_risk True) — look here because: open BACKLOG minor from the closeout's own fix — candidates with no severity key vanish without a diagnostic; one clamp-or-log line finishes the job the closeout started.
- **round 1 diff** `0202fb8..5f8b1a6` — 3 files, 378 lines; largest: `review-loop-tools/tests/panel_selftest.py` (+202/-7), `review-loop-tools/scripts/panel_review.py` (+137/-26), `review-loop-tools/scripts/render_report.py` (+5/-1) — look here because: the biggest behavioral round — proxy-bypassing open_url, the consent git probe (later deleted), process-group kill, the CLI jail (which broke codex until round 2), and safe_lane_name all landed here at once.
- **round 2 diff** `5f8b1a6..47fe2a7` — 2 files, 315 lines; largest: `review-loop-tools/tests/panel_selftest.py` (+172/-0), `review-loop-tools/scripts/panel_review.py` (+124/-19) — look here because: fixed the round-1 blocker (abspath past the jail) and rebuilt the consent rc semantics that round 4 then replaced entirely — transitional code, mostly superseded, but the ollama /api/show pre-check born here is live.
- **round 3 diff** `47fe2a7..0c4258c` — 5 files, 167 lines; largest: `review-loop-tools/tests/panel_selftest.py` (+73/-2), `review-loop-tools/scripts/panel_review.py` (+53/-15), `review-loop-tools/CONTROLS.md` (+8/-0) — look here because: introduced PANEL_REVIEW_CONSENT_NO_GIT (deleted one round later) — if you ever see that env var referenced anywhere downstream, it's dead; also where the safe() crash-in-the-crash-handler got fixed.
- **round 4 diff** `0c4258c..HEAD` — 11 files, 579 lines; largest: `review-loop-tools/tests/panel_selftest.py` (+211/-75), `review-loop-tools/scripts/panel_review.py` (+98/-87), `review-loop-tools/skills/review-loop/SKILL.md` (+14/-10) — look here because: THE design change of the loop — consent moved to a machine-local XDG store keyed by realpath hash, git probes deleted, version bumped to 0.12.0 (breaking, unreleased); both same-family agents agreed this design is right and the cross-family panel then found its two edges (relative XDG closed, absolute-inside-checkout still open), so read consent_path() yourself.
