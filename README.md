# Claudarama

Claudarama is a Claude Code plugin that turns your codebase into an autonomous AI startup. You are the CEO; the plugin provides a full organizational structure of AI specialists (PMs, Engineers, Researchers, Leads) that investigate, plan, build, verify, and learn on your behalf.

Instead of micro-managing an AI coding assistant by prescribing every task, you set the goals, grant the mandates, and approve work at strict decision gates. Claudarama handles the rest.

## Install and first run

Claudarama has two doors with the same actions behind both: a Claude Code plugin, used from inside a session, and a terminal command. Install either, or both.

### Before you start

- **Claude Code**, signed in.
- **[uv](https://docs.astral.sh/uv/)**. Both doors run through it; it supplies Python and the dependencies.
- **A project on GitHub.** The office keeps its tickets as GitHub issues, groups each Mandate's tickets under a milestone, and delivers work as pull requests that you merge at the PR gate. So the project must be a git repository cloned from GitHub, with Issues enabled.
- **[`gh`](https://cli.github.com), signed in** (`gh auth login`) as an account that can write to that repository: create milestones, edit issues, open and merge pull requests. `setup` stops with the fix when `gh` is missing or signed out.

### The plugin door

Inside Claude Code, add this repository as a marketplace and install the plugin from it:

```
/plugin marketplace add amitbaz/claudarama
/plugin install claudarama@claudarama
```

From a shell the same two steps are `claude plugin marketplace add amitbaz/claudarama` and `claude plugin install claudarama@claudarama`. Add `--scope project` to the install to enable the plugin in one project only.

Then, in a Claude Code session in your project:

1. `/claudarama:setup` scaffolds the pack, the project's `.claudarama/` directory. Commit it.
2. `/claudarama:open` opens the office. The session becomes the CEO's Session and Claude becomes the Assistant. At the first open the Assistant interviews you for the charter and confirms the project's test commands; after that, describe a problem and the Assistant shapes it into a Mandate for you to grant.
3. `/claudarama:status` shows what the office has used so far and, for each Mandate, a report of where the office did well and where it did not: each Role's turns with their usage and transcripts, every NO and FAIL with its reason, and every question a Role asked.

The office works while that session is open. Closing it pauses the office, and the next `/claudarama:open` picks the work up again.

### The terminal door

```
uv tool install git+https://github.com/amitbaz/claudarama
```

Then, in your project:

1. `claudarama setup` scaffolds the pack. Commit it.
2. `claudarama open` starts Claude Code as the CEO's Session, with the Assistant ready.
3. `claudarama status` shows the same usage and Mandate reports as `/claudarama:status`.

### When a gate opens

The office shows a macOS notification each time a gate opens, and the Assistant presents the gate in the Session, where you answer YES, NO or DISCUSS.

To be told on your phone as well, connect Remote Control in the Session (`/remote-control`) and turn on **Push when Claude decides** in `/config`. The Assistant then sends a push when a gate opens while you are away.

## Foundational Documents

To understand how Claudarama works, read these four pillars:

1. **[The Vision (`docs/CLAUDARAMA.md`)](docs/CLAUDARAMA.md):** What this plugin aims to achieve and how we prove it works.
2. **[The Operating Model (`docs/COMPANY.md`)](docs/COMPANY.md):** How the AI company actually functions on a daily basis (the 5-step lifecycle, the roles, and the CEO gates).
3. **[The Architecture (`docs/ARCHITECTURE.md`)](docs/ARCHITECTURE.md):** The strict separation between the project-agnostic Core plugin and your project-specific Pack, the office server, and mechanical gate enforcement.
4. **[The Vocabulary (`docs/GLOSSARY.md`)](docs/GLOSSARY.md):** The strict dictionary used by both humans and agents in this repository.

## Developing Claudarama

If you are an AI agent or contributor working on Claudarama itself, start by reading [**`AGENTS.md`**](AGENTS.md) for layout rules and build processes.
