# Claudarama

A Claude Code plugin that runs an autonomous AI startup for a software project.

## Pointers

- **Vision**: `docs/CLAUDARAMA.md` for the core product vision and proof scenarios.
- **Architecture**: `docs/ARCHITECTURE.md` for the core vs. pack split and office server design.
- **Operating Model**: `docs/COMPANY.md` for the AI startup lifecycle, roles, and gates.
- **Vocabulary**: `docs/GLOSSARY.md`. Use its terms exclusively.
- **Issues**: GitHub via `gh`. See `docs/agents/issue-tracker.md`.
- **Triage**: 5 standard GitHub labels. See `docs/agents/triage-labels.md`.
- **Domain Docs**: Layout rules. See `docs/agents/domain.md`.

## Build Process

Build one sub-project at a time.

1. Find the next unbuilt sub-project in the "Build order" of `docs/superpowers/specs/2026-09-30-claudarama-blueprint-design.md`.
2. Settle its design interactively with the owner.
3. Draft the sub-project spec (and update the master blueprint if decisions alter it).
4. Secure owner approval on the spec, and then the plan, before implementing code.

`docs/research/` holds research inputs. Treat them strictly as inputs, rather than decisions.
