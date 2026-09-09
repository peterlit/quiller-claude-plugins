# Suggestion for review-loop-tools / qa-loop-tools: codify "conclusions in git, evidence and scratch on disk"

*From the Causeway repo, 2026-09-08. Untracked by design — hand this to the plugin maintainer.*

## What happened here

Both loops keep their state in a dot-directory (`.review-loop/`, `.qa-loop/`). The durable
outputs (REPORT.md, ledger.json, rounds.md, verdict.json, coverage.json, …) belong in git;
the working state (briefs/, fragments/, evidence/, scratch/, .phase) does not — evidence
alone is 1 GB of screenshots here. The repo had denylist `.gitignore`s ("ignore evidence,
fragments, briefs"), which meant anything *unanticipated* was tracked by default. Two things
slipped through before anyone noticed:

- A Finder-duplicated `fragments 2/` (38 scratch files) got committed — the space-suffixed
  name matched no ignore pattern. The same duplication event left the run's only ledger
  named `ledger 2.json`.
- A `tools/__pycache__/*.pyc` was tracked.

The fix that stuck: flip each loop dir's `.gitignore` to an **allowlist** (`*` then `!` for
each known conclusion name), plus a repo test asserting the index stays clean. The plugin is
in a better position than any host repo to make that the default everywhere.

## Suggestions, in rough priority order

1. **Ship the allowlist; write it at bootstrap.** The plugin — not the host repo — owns the
   vocabulary of its durable outputs. When a loop first creates its dot-directory, write a
   default-closed `.gitignore`:

   ```gitignore
   # Conclusions in git; evidence and scratch on disk. Managed by <plugin> vX.Y.
   *
   !*/
   !.gitignore
   !REPORT.md
   !REPORT-*.md
   !rounds.md
   !rounds-*.md
   !ledger.json
   !ledger-*.json
   !verdict.json
   !coverage.json
   # qa-loop additionally: TESTCASES.md, WORKFLOWS.md, HARNESS_NOTES.md, HARNESS_NOTES-*.md, tools/*
   ```

   Use exact/dash-prefixed patterns, never bare `name*` globs — that is what keeps Finder
   duplicates (`REPORT 2.md`) untracked by default. When a plugin release adds a new durable
   output type, the same release updates this template; that keeps the definition of
   "conclusion" versioned with the code that produces it. If the host already has a
   `.gitignore` there, don't overwrite silently — surface a one-line suggestion to upgrade
   (denylist detected → offer the allowlist).

2. **Stage by explicit path, never by directory.** Wherever the orchestrator or its
   sub-agents commit loop artifacts, the instruction should be "add these named files", not
   `git add .review-loop`. Directory-adds are how a permissive tree turns into a permissive
   history; they also defeat the allowlist via sheer habit (`git add -A`). Worth an explicit
   prohibition in the implementer/orchestrator prompts: no `-f`, no `-A`, no directory adds
   inside the loop dir.

3. **Preflight + closeout hygiene check.** At loop start and again at closeout, run the
   equivalent of:

   ```sh
   git ls-files <loopdir>            # nothing under evidence/fragments/briefs/scratch/__pycache__
                                     # no " N."-style Finder-dup names; no file > 256 KB
   ```

   At start: warn and offer to fix (rename dups back to their plain names, `git rm --cached`
   strays — never delete from disk). At closeout: put unresolved violations in the REPORT's
   watch list so they can't sit unnoticed. This is the layer that catches `git add -f` and
   pre-existing damage, which no `.gitignore` can.

4. **Finder-duplication awareness on macOS.** The failure mode is specific and silent:
   Finder/iCloud duplication renames `X` to `X 2` (dirs and files both), so the loop's *real*
   state can end up under a name the plugin never reads. If a known name is missing but a
   ` \d+`-suffixed sibling exists, treat the sibling as the real file, offer the rename, and
   never write to the space-suffixed name.

5. **Suggest (don't impose) a host-repo guard test.** A drop-in test the plugin can offer to
   write into the host's suite — ~40 lines: index has no scratch paths, no Finder-dup names,
   no oversized blobs, and the nested `.gitignore` still begins with `*`. See
   `tests/repo-hygiene.test.mjs` in this repo for a working node:test version. The offer
   belongs in bootstrap or the controls skill; the decision belongs to the host.

6. **Optional: let evidence live outside the worktree.** A config knob to point `evidence/`
   at an external directory (session scratchpad, `~/Library/Caches/...`) would keep the
   gigabyte out of the repo entirely for hosts that want that. Default should stay in-tree —
   evidence next to the report it supports is genuinely useful — but the knob costs little.

7. **State the principle in the docs.** One line in each skill's README/controls:
   "conclusions in git, evidence and scratch on disk — the shipped `.gitignore` allowlist is
   the definition." Agents running the loop in unfamiliar repos will follow the rule they can
   read; today the convention only exists as this repo's local practice.

## What we can't do from the host side

The host repo can (and now does) enforce all of this locally, but every new repo that adopts
the loops starts from the permissive default and re-learns the lesson after its first
gigabyte or first Finder duplication. Items 1–3 close that gap at the source and none of them
change the loops' behavior — only what their working directories leave behind in git.
