# Backlog

## From review loop 2026-09-09 (scope pre-multi-provider-panel..HEAD — multi-provider panel, v0.11.0)

- **probe smoke still misses the configured model on FIRST setup** (`minor/panel_review.py:probe-smoke-diverges-from-run`, partial after closeout). The bare-`probe --smoke` default path fix covers re-probes, but SKILL.md's setup order runs probe *before* panel.json is written, so the model the human just chose is never smoked on first setup. Reviewer's note: reorder the setup recipe (write panel.json, then smoke) or add a post-config smoke step.
- **Script-content pinning for cmd lanes** (design-sized, sketched in closeout). `cmd_lanes_approved` binds the invocation string only: approving `bash ./lane.sh` does not pin lane.sh's contents. Sketch: extend `panel-consent.json` entries to optional objects `{"cmd": "...", "files": {"tools/lane.sh": "<sha256>"}}` and have `cmd_approved()` verify file digests before executing; needs a consent-prompt UX change and a re-prompt path.
- **qa-loop-tools/CONTROLS.md documents a panel qa-loop doesn't ship** (convention issue). The byte-identical sync forces the `[review]`-tagged panel section into the qa copy while `qa-loop-tools/scripts/` has no panel_review.py and its merge_ledger.py lacks panel-tally. Either port the panel to qa or add per-plugin section filtering to the sync.
- **probe marks `configured: true` by lane NAME, not type** (pre-existing minor, untouched). A codex lane named `cx` won't get the flag in probe output.
