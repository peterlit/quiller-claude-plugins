---
name: controls
description: Explains the review loop's knobs, settings, and controls — max rounds, REVIEW.md seeding, commit-guard env vars, model pins. Invoke when the user asks how to configure, steer, or tune the review loop.
---
Read `${CLAUDE_PLUGIN_ROOT}/CONTROLS.md` — the shipped operator's reference
for both loop plugins — and answer the user's question from it. If they asked
a specific question, answer just that (quote defaults and the "in practice"
guidance); if they asked generally, summarize the sections most relevant to
what they're doing right now. Prefer the reference over your own assumptions:
it is versioned with the plugin and reflects the installed behavior.
