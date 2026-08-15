# arch-docs-tools

A Claude Code plugin that produces **evidence-grounded architecture
documentation** for any repository — and decides for itself whether the
codebase warrants one document or several, dispatching a documenter
sub-agent per deliverable.

## How it works

1. **Survey** — `scripts/repo_survey.py` measures the repo deterministically:
   LOC and language mix per top-level directory, plus every detected
   buildable unit (package.json, `.xcodeproj`, Package.swift, go.mod,
   Cargo.toml, …).
2. **Split decision** — one buildable unit or a small repo gets a single
   `docs/architecture/overview.md` with the full treatment. Multiple units
   (say, a web prototype and an iOS app) each get their own detail doc plus
   a shared overview. A single huge unit is split by subsystem. The plan is
   announced before running; only genuinely ambiguous splits ask you to
   choose.
3. **Detail docs** — one `arch-documenter` sub-agent per deliverable, run in
   parallel. Each doc: top-level architecture diagram → module inventory
   (purpose, public interface, patterns, dependencies, primary file paths) →
   sequence diagrams for the 3–5 key flows → ER diagram where a persistent
   model exists → a candid **state of the architecture** section (decisions
   and inferred rationale from git history, coupling and tech debt,
   vestigial code).
4. **Overview** — a final agent synthesizes the shared doc from the detail
   agents' manifests (treated as claims to verify): how the deliverables
   relate, shared concepts and their sources of truth, a system-context
   diagram of external dependencies, and cross-deliverable inconsistencies.
5. **Scripted validation** — `mermaid_lint.py` catches the classic generated
   Mermaid failures (unknown diagram types, unbalanced brackets, unquoted
   labels, subgraph/end mismatch) and `coverage_check.py` cross-checks the
   module inventory against the real source tree, reporting unmentioned
   files largest-first. Agents fix their own documents until clean; residual
   gaps must appear in a "Not covered" appendix, never silently.

## Accuracy contract

Docs describe only what is verifiably in the code: claims checked against
source rather than file names, file paths cited throughout, and inferences
(especially about intent) explicitly labeled `Inference:`.

## Usage

```
/arch-docs-tools:arch-docs
```

Output lands in `docs/architecture/`. Diagrams are Mermaid, so they render
on GitHub and in most markdown viewers. Re-run after major refactors — the
docs cite real paths, so they age visibly with the code.

## Model configuration

The documenter uses `model: inherit` — deep code comprehension runs on
whatever model you pick for the session (`/model`). There is no adversarial
pairing here, so no pinned second model; if you want the docs themselves
reviewed, run `/review-loop-tools:review-loop` on the docs commit.
