# Proposal: Grok (xAI) as a review-panel lane

Written 2026-09-20. Status: **PARKED — captured for a future cycle, not
approved, nothing built.** Peter: "Capture the Grok proposal as an .md. We
will get back to it in the future."

## Why

The panel's value, measured over four field runs on 0.13.0, was
cross-family *agreement* on the chair's findings more than net-new
findings (agent 1, 2026-09-13: "Panel value here was cross-family agreement
on the chair's blocker"). Today the families are Anthropic (chair, verifier,
implementer), OpenAI (codex lane) and Google (gemini lane); the local
qwen3-coder lane went 0/40 and is now precision-disabled automatically. A
Grok lane adds a fourth family at API cost only.

## Facts on the maintainer's machine (2026-09-20)

- `which grok` resolves to `/Applications/cmux.app/Contents/Resources/bin/grok`,
  a cmux **wrapper** that installs terminal hooks and `exec`s a real
  `grok`/`grok-macos-aarch64` found elsewhere on PATH. No real xAI CLI is
  installed; the wrapper exits 127 without one.
- The wrapper's option table shows the real CLI's shape: single-shot mode
  (`--single`, `-p`/`--prompt-file`/`--prompt-json`), `--output-format`,
  `--sandbox`, `--permission-mode`, `--model`, `--cwd`, and `auth login` /
  `models` subcommands — codex-like.
- No `XAI_API_KEY` or `GROK_API_KEY` in the environment.
- xAI's API is OpenAI-compatible (chat completions at `https://api.x.ai/v1`).
  Current model identifiers and the API data-use terms must be confirmed at
  build time (the models endpoint lists what the key can reach; terms are
  not something to assert from memory).

## Options

### O1. Zero-code trial: a `cmd` lane

A ~15-line script reads the prompt on stdin, POSTs it to the chat
completions endpoint with the key from the environment, unwraps
`choices[0].message.content`, prints it. Consent: the exact command string
in the machine-local `cmd_lanes_approved` list (approving it IS the human's
egress decision — say so at the gate). 0.14.0's error classification,
passive token capture (the response's `usage` object), evidence pre-filter
and precision cap all apply to its output unchanged. Good for one or two
measured runs before any plugin code. Weakness: the command string is the
whole contract, and `run` cannot tell it is a remote lane.

### O2. RECOMMENDED — a generic OpenAI-compatible HTTP lane type; Grok is its first configuration

```json
{"name": "grok", "type": "openai-compat",
 "base_url": "https://api.x.ai/v1", "model": ["<confirm at build>", "<fallback>"],
 "api_key_env": "XAI_API_KEY", "timeout_s": 600, "max_diff_tokens": 32000}
```

- One implementation covers xAI, OpenAI direct, DeepSeek, Mistral,
  OpenRouter and local servers (llama.cpp, LM Studio) — a loopback
  `base_url` is local like ollama, anything else is a remote lane needing
  `remote_lanes_approved`.
- The safest lane shape the panel has: no CLI, no file tools, nothing to
  jail; `open_url` already bypasses proxies for loopback and honors them
  otherwise.
- Slots into 0.14.0 as built: model LIST fallback on quota/404 (HTTP 429 /
  404 map straight onto `error_kind`), real token counts from `usage`,
  `elapsed_s`, precision cap/disable, `--lanes`/`--detach`/`wait`.
- `response_format: {"type": "json_object"}` where the server supports it;
  `extract_json` handles the rest.
- Probe: key present → `GET {base_url}/models` as the smoke (lists what the
  key can reach; spends no generation quota — the gemini lesson) and reports
  the auth line; with `--smoke` optionally one tiny completion.
- Size: ~100 lines in `panel_review.py` (a `run_openai_compat` runner, the
  probe row, kind→consent mapping), selftest checks with a stubbed
  `open_url` (auth header, JSON body shape, model fallback on 429, usage
  capture, loopback = no consent), a CONTROLS "Review panel" paragraph,
  review-loop-tools 0.15.0.

### O3. A first-class Grok CLI lane (codex-style)

Needs the real CLI installed and authenticated; it is an agentic tool that
wants a workspace, which the panel's diff-only design denies by running
CLIs in an empty jail. More surface, less testable (no real CLI in the
build session), and it only wins if a subscription login is the affordable
auth path the way codex-on-ChatGPT is. Not recommended unless that is the
case.

## Declined for now

- Grok-specific lane type: O2 subsumes it and stays future-proof.
- Guessing model identifiers or pricing in this document.

## Open questions for Peter

1. Is there an xAI API key, and on which tier (rate limits shape
   `timeout_s` and whether a fallback model is needed)?
2. Do the API terms permit training on inputs? Same rule as gemini: API key
   only, never a consumer account, and the probe's auth line must say what
   was checked.
3. Replace the ollama lane in the two field repos, or run alongside it for
   a measured comparison (same scope, same passes)?

## Measurement plan when picked up

Two scoped review runs per field repo with the lane enabled; compare
kept-rate and verifier tokens per net-new kept finding against codex and
gemini (0.13.0 baselines: codex 2/3, 1/1; gemini 3/6, 1/8; ~23–28K
verifier tokens per net-new panel minor). The precision cap and disable
are the safety net if the lane is noise. Watch items: cross-family
agreement count on chair blockers/majors; whether the lane files
"hidden file not updated" claims despite the EXCLUDED trailer.
