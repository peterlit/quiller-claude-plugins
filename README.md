# quiller — Claude Code plugin marketplace

Plugins by Peter Litskevitch.

| Plugin | What it does |
|--------|--------------|
| [review-loop-tools](review-loop-tools/) | Adversarial implementer/reviewer convergence loop over the *code*, with thrashing detection and an iteration backstop. |
| [qa-loop-tools](qa-loop-tools/) | Simulator-driven UX/QA convergence loop over the *running iOS app*: persona-based testing with evidence-backed findings. |
| [arch-docs-tools](arch-docs-tools/) | Evidence-grounded architecture documentation for any repo, with automatic per-deliverable splitting and scripted diagram/coverage validation. |

Operating either loop? [CONTROLS.md](CONTROLS.md) is the shared reference —
every knob, where it lives, and how to use it in practice. It also ships
inside each plugin and is available in-session via
`/qa-loop-tools:controls` or `/review-loop-tools:controls`.

## Install

```
/plugin marketplace add peterlit/quiller-claude-plugins
/plugin install review-loop-tools@quiller
/plugin install qa-loop-tools@quiller
```

For local development, `claude --plugin-dir /path/to/<plugin>` overrides an
installed copy of the same name for that session.
