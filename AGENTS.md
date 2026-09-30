# Claudarama

Claudarama is a Claude Code plugin that runs an AI startup for a software project: the owner is the CEO, every other seat is a named AI team member. A project adds a `.claudarama/` pack to become `<project>-office`; the first is `gili-office` for gili.careers.

## Start here

The project is still being designed. Before any work:

1. Read `docs/superpowers/specs/2026-09-30-claudarama-blueprint-design.md`, the umbrella design. Its "Open questions" section lists what is still undecided; its "Build order" lists the sub-projects.
2. Continue shaping the design by settling open questions with the owner one at a time. Record each decision in the spec body and remove it from "Open questions" in the same commit.
3. No implementation before the owner approves the written spec and then the written plan for the sub-project.

`docs/research/` holds research inputs (for example the oh-my-claudecode teardown). They are inputs, not decisions.

## Agent skills

### Issue tracker

Issues and specs for this repo live as GitHub issues, manipulated via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

We use the standard 5 triage roles mapping 1:1 with GitHub label strings (e.g. `needs-triage`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (one `GLOSSARY.md` and `docs/adr/` at the root). See `docs/agents/domain.md`.
