# Claudarama

Claudarama is a Claude Code plugin that runs an AI startup for a software project: the owner is the CEO, every other seat is a named AI team member. A project adds a `.claudarama/` pack to become `<project>-office`. The core is tied to no single project.

## Start here

The project is built one sub-project at a time. Before any work:

1. Read `GLOSSARY.md` and use its terms.
2. Read `docs/superpowers/specs/2026-09-30-claudarama-blueprint-design.md`, the umbrella design. Its "Build order" lists the sub-projects; each built one has its own spec in `docs/superpowers/specs/` and closed issues on GitHub.
3. Work on the next unbuilt sub-project in "Build order". Settle its design with the owner one question at a time and write its spec. If a decision changes the blueprint, update the blueprint in the same commit.
4. No implementation before the owner approves the written spec and then the written plan for the sub-project.

`docs/research/` holds research inputs (for example the oh-my-claudecode teardown). They are inputs, not decisions.

## Agent skills

### Issue tracker

Issues and specs for this repo live as GitHub issues, manipulated via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

We use the standard 5 triage roles mapping 1:1 with GitHub label strings (e.g. `needs-triage`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (one `GLOSSARY.md` and `docs/adr/` at the root). See `docs/agents/domain.md`.
