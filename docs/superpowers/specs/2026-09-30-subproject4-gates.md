# Sub-project 4: Gates

This spec details sub-project 4 of the blueprint: the mechanisms that keep the office inside the CEO's gates, and the turn setup that keeps the office from draining the owner's Claude subscription. Decisions were settled with the owner on 2026-09-30. Terms follow `GLOSSARY.md`.

## 1. Identity at the MCP seam

Every call to the office server is tied to who made it.

- When the daemon starts a turn, it creates a secret per-turn token and passes the MCP endpoint as `http://localhost:<port>/mcp/<token>`. The server maps the token to the turn, its person and its ticket. The token dies when the turn ends.
- The CEO's session (`claudarama open`) holds the owner token. Only the owner token may grant a mandate, approve a gate request or hire.
- A `talk <name>` session carries that person's identity and allowlist, not the owner's. Grants and gated actions happen only in the `open` session, so every approval lands in one record.
- A hook denies turns any access to `~/.claudarama/`, which holds `office.db` and the owner token. All members still run as the owner's OS user, so this stops mistakes and casual forgery, not a determined attacker.

## 2. Grants

A turn starts only if one of these holds:

1. its ticket belongs to a mandate the CEO granted (replies in that ticket's thread included);
2. it is a ritual turn;
3. it is an Assistant turn.

Anything else, including a head's ticketless request, is refused: the work needs a ticket under a granted mandate first.

- The CEO approves a mandate in the `open` session; the Assistant records the grant with the owner token.
- `ticket-ready` must name the ticket's mandate; the server refuses a mandate that is not granted.
- The daemon is the authority for which mandates are granted and which tickets belong to them. It mirrors this one way to GitHub: a granted mandate becomes a milestone, and each ticket under it is placed in that milestone. If someone moves an issue to another milestone by hand, the daemon moves it back and says so in a comment. GitHub stays the source of truth for a ticket's content.

## 3. Permissions

One allowlist, generated in one place from the core list, the pack's `gates.yaml` and the commands in `stack.yaml`, feeds two walls:

1. **Native settings.** The daemon writes it into each turn's `--settings` as `permissions.allow` rules and runs the turn with `--permission-mode dontAsk`, so any call not covered is denied.
2. **The gate hook.** A PreToolUse hook splits chained shell commands (`&&`, `||`, `;`, `|`, `$(...)`, backticks) and checks every part against the same allowlist. It denies with a reason the model sees, and fails closed on anything it cannot parse.

Gated actions (money, staging and production, hosted databases, CI, secrets, repository settings, and the rest of the CEO's gates) never reach a headless turn. They run only in the CEO's `open` session, where Claude Code's own permission prompt is the CEO's approval (ADR-0002). A person who needs one ends their turn with a BLOCKED message to the Assistant.

## 4. Merging

A turn may merge a pull request only when a SHIP verdict is recorded in the server for the pull request's head commit. The gate hook checks this before allowing the merge command. Level decides whose ship-check counts: an L3 or above may merge on their own ship-check; below L3 the verdict must come from their lead. The checks a ship-check requires (CI, reviews, design or AI gates) come from the pack's `review-gate` list; the core names no tool.

## 5. Concurrency

- Per office: at most N turns at once, from `org.yaml` (default 3).
- Per machine: at most M turns across all offices (default 10), first in, first out.
- A person never has a turn and a session at the same time; queued turns for a person in a `talk` session wait until it ends.

Running more turns at once does not use more tokens in total, but drains the subscription's 5-hour window faster, leaving the office paused and the owner without Claude. The low default is raised once the numbers from section 8 show headroom.

## 6. Subscription usage limit

When a turn fails with a usage-limit error (matched on the error text, such as "You've hit your session limit" or "You've hit your weekly limit", since no structured field is documented), the daemon:

1. puts the turn back in the queue;
2. pauses every office on the machine, because the limit belongs to the owner's account, until the reset time in the message (or a configurable fallback when no time can be read);
3. sends the CEO a macOS push notification.

## 7. Lean turns

Today each turn starts as plain `claude -p <brief>` and loads the owner's whole personal setup: every plugin, skill listing, MCP server and the global `CLAUDE.md`. That costs thousands of tokens per turn and exposes hosted-infrastructure tools.

Each turn instead runs with its own clean Claude config directory per office (`CLAUDE_CONFIG_DIR` under `~/.claudarama/<project>/`), holding only the office plugin, the pack's required plugins (from the pack's `plugins` file) and the gate hook, and `--strict-mcp-config` with only the office MCP server.

Fallback, if the subscription login does not carry over to a separate config directory: keep the normal config directory and use `--strict-mcp-config` plus `--allowedTools`, which removes unlisted tool definitions from the context. `--bare` is not an option: it does not work with a subscription login and cannot load hooks.

## 8. Measuring usage

The daemon reads the `result` line of each turn's stream and stores its usage: input, output, cache-read and cache-write tokens, the model and `total_cost_usd` (an estimate on a subscription). `claudarama status` shows totals per person, per ticket and per ritual. This is the data every later efficiency decision, and the Budget sub-project, builds on.

## 9. Fewer turns

Every wake pays for a new turn, so the daemon wakes people less often:

- **Only some messages wake a turn.** DONE, BLOCKED and QUESTION start one. FYI and ACK wait for the receiver's next brief.
- **Batching.** When a waking message arrives, the daemon waits a short window (default 2 minutes, set in `org.yaml`), and never starts one while the receiver already has a turn running. All pending messages in that thread go to one turn.

## 10. Threads and working notes

- A thread is the messages about one ticket, or about one topic when there is no ticket. `send` takes either `ticket` or `topic`. This replaces today's pair-of-people threads (`turns.thread_with`, `get_thread`). A turn's brief loads only the thread that woke it, and a reply turn inherits its ticket, and so its grant, from its thread.
- At the end of a turn the person writes a working note of at most 500 characters with the `pin` tool: the files involved, what they found, the next step. The next turn on that ticket loads it.

## 11. Brief order

The brief follows a fixed order from most stable to most changing, so turns share the prompt cache (cache reads cost about a tenth of fresh input; on a subscription the cache lives one hour):

1. charter goal;
2. current key results and the latest all-hands;
3. role file with pack overlays;
4. lessons in scope;
5. the person's record summary;
6. the thread, the ticket and its working note.

## 12. Model

Every turn runs on Sonnet unless its ticket is marked hard by the CEO or a lead, which runs it on Opus. Pure sorting or summarising may use Haiku. The model is chosen per ticket, never per level; finer per-task choice can come later.

## 13. Fresh or resumed turns: an experiment

Turns start fresh on every wake. Resuming one conversation per person and ticket (`--resume`) might save re-reading code, but re-sends the whole conversation each wake, which is cheap within the one-hour cache and expensive after it. Nobody knows which wins without numbers, so:

- the daemon stores the conversation ID for each person and ticket;
- `org.yaml` gets a switch, `resume_per_ticket` (default off);
- one scenario runs the same ticket both ways and compares the usage from section 8.

The winner becomes the default. Always-on sessions stay rejected.

**Experiment result**: Running the local comparison scenario (scenarios/compare_resume.py) showed that while `resume_per_ticket: true` saves initial file-reading API calls, the unbounded conversation growth leads to massive input token costs once the 1-hour cache expires. `resume_per_ticket: false` (fresh starts + working notes) remains the default as it yields significantly lower overall cost over long tickets.

## 14. PreCompact checkpoint

The PreCompact hook stays: if a long turn compacts, it saves a checkpoint to the server first, so the next turn does not lose the work.

## Testing

- **Hook tests** feed recorded hook JSON on stdin: allowed and denied commands, each chained form, unparseable input (fails closed), access to `~/.claudarama/`, merge with and without a SHIP verdict on the head commit.
- **MCP seam**: calls with a turn token, the owner token, a dead token and no token; grant refusals; `ticket-ready` with an ungranted mandate.
- **Supervisor seam** (mock `claude` executable): concurrency caps, a usage-limit error pausing all offices, batching and wake types, usage captured from the result line, the generated settings and config directory.

## To verify during the build

Each has the fallback given above or is recorded here:

- whether the subscription login works with a separate `CLAUDE_CONFIG_DIR` (fallback in section 7);
- how native permission rules match chained commands (the gate hook covers it either way);
- the deny pattern syntax for MCP tools in `permissions.deny` and `--disallowedTools`;
- whether hooks and `--settings` apply under `claude -p --resume` (needed only if section 13's switch wins);
- what `--max-budget-usd` does when it trips (for the Budget sub-project).

## Out of scope

- Spend caps of any kind: per grant, per office day, per ritual. They belong to the Budget sub-project (5b).
- The rest of the company layer: hiring, levels, reviews, rituals themselves.
