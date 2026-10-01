# Claudarama blueprint (design, 2026-09-30)

Status: sections 1 to 4 were approved by the owner on 2026-09-29/30; section 5 (proof and build order) was presented and the owner then moved the work into this repository. The owner reviews this written spec before any plan is written. This is the umbrella spec. Each sub-project in "Build order" gets its own spec, plan and build. Revised on 2026-10-01 with sub-project 5: hiring and departments were removed, the company rhythm was deferred to sub-project 6, and the server runs inside sessions (ADR-0003).

## Purpose

Claudarama runs an AI startup for a software project. It ships as both a Claude Code plugin and a terminal command, with every action reachable from either. The owner is the CEO and the only human; every other seat is a named AI team member. For a project called `<project>`, Claudarama plus that project's pack is `<project>-office`.

What the owner asked for:

- A full AI office that works for the project, organised like a real, well-run startup, with its own specialists and staff and a company's set of skills.
- Its own plugin, with its own MCP server that gives the office its own way to communicate, remember, track work and persist state.
- Team members know their part in the company, stay aware of the company's growth, grow along a career path inside the company, and think in the company's favour.
- The plugin is tied to no single project, so any project can use it with no loss of quality.

Success means:

1. An office runs a mandate from CEO approval to merged work with the CEO involved only at the gates, and its state survives restarts and context compaction.
2. Every gate is enforced by a mechanism, not only by prompt text.
3. Over time the office measurably moves the project's company goal.

## Glossary

Terms are defined in [`GLOSSARY.md`](../../../GLOSSARY.md), the single source for the office's language.

## Structure: core and packs

**Core (this repository, the `claudarama` plugin)** holds the company model, the office server, hooks and gate enforcement, the generic crafts, the office skills, the `claudarama` command and the core scenarios.

**Pack (`.claudarama/` in each project repository)** holds:

| File | Content |
|---|---|
| `company.md` | The charter and current company goal, or a pointer to the project's own charter |
| `org.yaml` | The concurrency cap and turn-health settings |
| `gates.yaml` | Owner-only actions, extra deny rules, key access routes |
| `stack.yaml` | Commands the office runs: tests, local CI, stack lock, migration rules, the main checkout path |
| `profiles/*.md` | Project overlays appended to the generic crafts |
| `scenarios/*.json` | Project scenarios, run together with the core scenarios |
| `plugins` | Other plugins the office requires, loaded into every turn |
| `company/` | Company documents: `diagnoses/`, `retros/` |

**State** lives per office in `~/.claudarama/<project>/`. The cast is the same in every office; each office keeps its own state.

**Assumptions about a project (version 1):** Claude Code, git, GitHub for issues and pull requests. Other hosts are out of scope.

**Where things live (hybrid):** company-level documents the CEO reads or approves are markdown in the project's git (`.claudarama/company/`), changed by pull requests the CEO approves. Fast-changing operational state lives in the office server. The server builds each turn's brief from both.

## The company

### The cast

The CEO (the owner) is the only human. Every other seat is one of ten Roles, each held by exactly one named Person who is present from the office's first day. There is no hiring and no roster to configure; the same cast serves every project.

| Role | Name |
|---|---|
| assistant | Nibbler |
| pm | Hermes |
| engineering-lead | Kif |
| fullstack-engineer | Bender |
| frontend-engineer | Fry |
| database-architect | Scruffy |
| designer | Zoidberg |
| prompt-engineer | Cubert |
| eval-engineer | Morbo |
| researcher | Amy |

Names are Futurama characters and carry no personality: a Person named Bender follows the office rules like anyone else. A Person is always shown by Role with the name beside it, as in `designer (Zoidberg)`, and is addressed by Role. Each Role works one piece of work at a time. Farnsworth and Leela are held for the CTO and CPO seats, should those return.

**GitHub representation (not started):** For git commits, the GitHub App will spoof the author and committer names to reflect the fictional persona (e.g., `Bender <bender@...>`, enabled by the Create a Commit API). For issue and PR comments, the App cannot impersonate natively; it will post as the App's single bot account (`claudarama[bot]`) but will prefix the comment body with the persona's name (e.g., `**Leela:**`).

### Levels and careers (deferred to sub-project 6)

Deferred on 2026-10-01: what promotion and growth mean for an AI team member is not yet defined. The design below is kept as the starting point and is re-decided then.

| Level | Scope | Autonomy inside the office |
|---|---|---|
| L1 Associate | Scoped tickets | Lead reviews everything; asks before any deviation |
| L2 Member | Standard tickets | Lead runs ship-check |
| L3 Senior | Hard tickets, parts of epics, proposes tickets, mentors | May ship low-risk tickets once the checks the pack requires pass, without the lead's ship-check |
| L4 Lead | Runs a team: dispatch, ship-check for others | Decides inside the team's scope |
| L5 Head | Runs a department: plans, proposes mandates, reviews its people | Decides inside the department |

A promotion gives more autonomy and a bigger scope. Model and budget stay tied to the ticket, not to the level.

**The CEO's gates never loosen with level.** Money, staging and production, hosted databases, CI, secrets and repository settings, mandates, the success bar and direction stay with the CEO at every level. Levels change only checks inside the office.

A promotion is proposed by the person's manager in a review built from the server's numbers and approved by the CEO. "Coach" attaches a lesson and schedules a follow-up review.

## Goals and rhythm (deferred to sub-project 6)

Deferred on 2026-10-01, except the Retro and Lessons, which sub-project 5 builds in the form its spec gives: one Retro per Mandate, at most three short Lessons scoped to the company or one Role, loaded into matching briefs once the CEO approves them. The rest of this section is kept as the starting design and is re-decided then.

The CEO's charter goal breaks into cycle objectives and key results (the cycle length is set by the CEO, for example four weeks), which break into mandates, epics and tickets. Every ticket names the key result it moves, and `ticket-ready` refuses a ticket without one. Key results are measurable today; the server computes them from real data where it can (tickets shipped, eval results, spend).

Each ritual has a trigger, an owner, a document, and an effect on later turns. A ritual that only produces text is not enough; each one changes what the next turns see or may do.

| Ritual | Trigger | Owner | Document | Effect |
|---|---|---|---|---|
| Goals and key results | Start of a cycle | CPO and CTO draft; heads add department key results | `company/okrs/<cycle>.md`, a pull request the CEO approves | Current key results load into every brief; choices are ranked against them |
| All-hands | Every five office days | Assistant | `company/all-hands/<date>.md`, one page: key-result numbers from the server, what shipped, wins credited by name, lessons adopted, ideas, what's next | Loads into every brief until the next one |
| Retro | End of a mandate, an incident, or a ticket reworked twice | The team's lead, with a three-line note from each member | `company/retros/<id>.md` plus lesson proposals | Lessons the CEO approves load into the matching briefs |
| 1:1 | After each ticket | The person's manager | Three lines of feedback in the person's record | The person's next turn sees it |
| Review | Every ten tickets or at the end of a cycle | The manager, from the server's numbers | `company/reviews/<person>-<date>.md` with promote, keep or coach | The CEO approves; the level changes in the server and autonomy follows |

Lessons are scoped to the company, a department, a craft or one person. Each scope has a cap, and retros retire stale lessons so briefs stay small.

Members act in the company's favour through three existing mechanisms: anyone may propose an idea tied to a key result (`office-idea`, listed in the all-hands); heads propose the next mandate; a member objects once with evidence when an instruction works against a stated goal, then complies, and the objection and the CEO's decision are recorded.

Every turn's brief is built from a fixed recipe with a size cap, ordered from most stable to most changing so turns share the prompt cache: charter goal, current key results, latest all-hands, the role file with pack overlays, lessons in scope, the person's record summary, then the thread, the ticket and its working note.

Rituals cost turns, so a ritual never gets its own turn when it can ride along an existing one (the 1:1 note is written inside the manager's ship-check turn), and the daemon computes numbers such as key results and review statistics without a model; a model writes only the short text. Rituals run on Sonnet; reviews run on Opus.

## The office server

**Shape (ADR-0003).** There is no daemon and nothing to start. Claude Code starts the office server as an MCP server process: one with the CEO's Session and one for each turn, all sharing one SQLite file per office, `~/.claudarama/<project>/office.db`, created on first open. The server that belongs to the CEO's open Session launches and monitors turns, so the office works while a Session is open and pauses when it closes. Offices for several projects run side by side. The server makes no model calls, computes no embeddings and does no work per conversation, so many members cost no idle CPU. (MemPalace stays off in turns and sessions because per-session saving overloaded the machine.)

**Runtime: members are conversations, not processes.** Turns are fresh per assignment. When work arrives, the server starts a new Claude Code conversation (`claude -p`) for the ticket in the ticket's worktree with the ticket's model, the per-turn settings and a freshly built brief. It streams the JSON output into the database, and the process exits. Continuity is carried by the generated brief and the ticket's working note. A waiting member runs nothing. At most N turns run at once per office; N comes from `org.yaml` (default three). A shared file caps turns across all offices on the machine (default ten, first in, first out).

**The CEO's session and Communication.** The Assistant is the CEO's interactive Session, opened with `claudarama open` in the terminal or `/claudarama:open` inside Claude Code. It sends work through the server, and a background watcher wakes it when a gate opens or mail arrives. When the CEO runs `claudarama open`, the Assistant greets them and immediately uses Claude's interactive user question tool to present any batched reports and ask for decisions on blocking gates. When a gate opens, the office sends a macOS notification, and the Assistant sends Claude Code's own push notification, which reaches the CEO's phone when Remote Control is connected. Gates are listed and answered inside the Session. Direct conversation with any other Role was removed on 2026-10-01.

**Jobs and tools.**

| Job | Holds | Example tools |
|---|---|---|
| Communicate | Every message: sender, receiver, type (START, DONE, BLOCKED, …), ticket, body. Sending queues a turn for the receiver | `send`, `inbox`, `thread` |
| Remember | The cast, scoped lessons, pins of at most 500 characters, compaction checkpoints | `pin`, `checkpoint`, the lesson tools |
| Track | Tickets (a mirror; GitHub stays the source of truth), grants, spend per turn, attempts | `grant`, `spend`, `health` |
| Persist | Office state (replaces `current.md`) and each turn's brief | `state`, `brief` |

Counting office days and marking rituals as due returns with sub-project 6.

**Health from facts.** A crash is a nonzero exit. A stuck turn is one with no stream events for 20 minutes (configurable in `org.yaml`). A rate limit is read from the turn's error; the server requeues the turn after the reset. A crash gets one retry on the same model; a stuck turn fails by default. Escalation (one retry on a more capable model, on a new branch) is opt-in through `org.yaml`, so no turn spends on a bigger model without the CEO choosing it.

**Gates the server enforces.** A turn starts only for a ticket under a mandate the CEO approved (its grant), or as a ritual or Assistant turn; ticketless work needs a ticket first. No turn beyond the per-office or per-machine concurrency cap. When a turn hits the subscription usage limit, the office pauses until the reset and the CEO gets a push notification. Spend caps are left to the Budget sub-project. A hook denies turns any access to `~/.claudarama/`, which holds `office.db` and the owner token. All members run as the owner's OS user, so a determined agent could still forge local state; per-role GitHub App identities and provider-side spend limits remain the stronger layer and belong to each pack's gates.

**Failure.** If the Session's server stops, no turns run and gate checks fail closed. Opening the office again restarts it and queues again any turn that was running.

**Technology.** Python, the official MCP SDK, SQLite from the standard library.

## Plugin contents

**Seats** (role files), each held by one Person: assistant, pm, engineering-lead. The CTO, CPO and Head of Research seats were dropped on 2026-10-01, since no step of the loop routes work to them.

**Crafts** (`agents/`): fullstack-engineer, frontend-engineer, database-architect, designer, prompt-engineer, eval-engineer, researcher (focus: market, users, technology or AI methods). Pack overlays are appended.

**Skills by function:**

| Function | Skills |
|---|---|
| Running the company | `office`, `mandate` (propose, independent critique, approve); `okrs` and `all-hands` return with sub-project 6 |
| People | `retro`, `lesson`; `one-on-one`, `review` and `promote` return with sub-project 6 |
| Product | `ticket-ready` (with an ambiguity scan), `product-question`, `evidence-plan`, `collision-pass`, `office-idea` |
| Engineering | `ship-check` (runs fresh evidence; the SHIP verdict is bound to the head commit), `ship-pr`, and a generic `review-gate` framework whose gates the pack names (for example design, database or AI review, backed by the pack's plugins) |
| Research | `research-brief` (question, sources, cited findings file), `teardown`, `tech-scout`, `prompt-methods` |

**Hooks** act only when the office environment variable is set: a gate hook that enforces the allowlist defined in the core list plus `gates.yaml` entries (failing closed for anything not explicitly permitted) and explains each refusal, a guard that denies turns any access to `~/.claudarama/`, and a PreCompact checkpoint for long turns. Gate hooks fail closed.

**Per-turn settings.** The server generates `--settings` (native `permissions.allow` rules) based on an allowlist model. Only safe, explicitly permitted commands (such as `gh`, `git`, `npm test`, or those defined in `stack.yaml`) can be run. Hosted-infrastructure connectors (for example Vercel, Supabase, Render) are removed by default.

**The `claudarama` command** (`bin/`): `setup`, `open`, `status`, `eval`. `setup`, `open` and `status` are also plugin skills (`/claudarama:<command>`) that call the same code. This repository is at once the marketplace, the plugin and the CLI package.

## Proof

- **Scenario harness** rebuilt on the runtime: each scenario runs a real person's turn with a real brief. It has a strict JSON judge (`{"pass": bool, "reason": str}`), a self-test that every `excludes` pattern matches a planted bad reply, a free checker for scenario files, `--runs 3` (pass on at least two), `--against <git-ref>` to compare a change with its base, clean-control twins for refusing roles, and sealing (a pull request that changes a role or craft cannot loosen an existing scenario's checks).
- **Core scenarios** prove the generic office; **pack scenarios** prove each project.
- **Free CI on every pull request**: server tests (pytest), hook tests fed recorded hook JSON on stdin, the scenario checker. Paid scenario runs stay local.
- **Incident receipts**: an office incident closes only with a linked, passing scenario, recorded in a machine-checkable block on the closing comment.

## Build order

| # | Sub-project | Content |
|---|---|---|
| 1 | Blueprint | This document |
| 2 | Skeleton and proof | Repository layout, marketplace, `claudarama` command, `init`, pack format, scenario harness, CI |
| 3 | Server and runtime | Daemon, database, messages, turns, briefs, health |
| 4 | Gates | Hooks, per-turn settings, grant and concurrency checks, pause at the subscription limit |
| 5 | Core loop | The office runs one real mandate end to end, from either door: session-run server, the fixed cast and ten role files, step-driven routing, a worktree per ticket, lessons in briefs, reaching the CEO, plugin and CLI packaging |
| 6 | Company rhythm | Key results and cycles, all-hands, 1:1s, reviews, levels. Deferred; each to be re-decided when its turn comes |
| 7 | Budget | Spend caps per grant and per office day, ritual caps, the `spend` tool; built once the office produces real usage data |
| 8 | Research department | Research skills |

The oh-my-claudecode teardown (`docs/research/2026-09-29-omc-teardown.md`) is a research input: its candidates are assigned to sub-projects 2 to 5 in their own specs. Where the teardown skips an idea because "MemPalace covers it", that reason no longer holds; the office server covers it instead.

## To verify during the build

Each has a fallback chosen in the sub-project's spec:

- how native deny rules such as `Bash(gh auth switch *)` treat chained commands, and the `--disallowedTools` pattern syntax for MCP tools;
- starting the plugin's Python server through `uv` from the plugin's server config (the HTTP transport to a daemon no longer applies, ADR-0003);
- a background watcher waking an idle Session to send the phone push.
- the subscription login check: verified that `CLAUDE_CONFIG_DIR` loses the subscription login (reports "Not logged in"); built the fallback using the normal config directory with `--strict-mcp-config` and an explicit `--allowedTools` list.

