## Problem Statement

The Claudarama office currently lacks a persistent server and runtime. We need a way for headless AI team members to run concurrently, persist their state (records, threads, turns), and interact safely with their environment across process restarts without relying on the human CEO being interactively present.

## Solution

We will build a local Python daemon using the `FastMCP` framework. The daemon will play a dual role: an MCP Server providing tools to the AI members, and a Supervisor managing the lifecycle of headless `claude -p` subprocesses. State will be stored in a local SQLite database for speed, while heavy JSON outputs will be written to disk.

## User Stories

1. As the CEO, I want the daemon to run in the background so that the AI team can work on tickets while I am away.
2. As a Person (AI member), I want my active message threads injected into my brief so that I have the context of ongoing conversations when my turn starts.
3. As the system, I want turns to be strictly ephemeral so that waiting on another agent's reply doesn't lock up concurrency slots.
4. As a Person, I want to call tools via MCP so that state mutations (like sending a message or updating a record) are safely handled by the daemon.
5. As the daemon, I want to write raw JSON outputs to disk rather than SQLite so that the database remains fast for querying texts and briefs.
6. As the CEO, I want stalled turns (no output for 20 mins) to fail by default rather than automatically consuming a more expensive model, so that I have control over token usage.
7. As the system, I want the daemon to read company policy and role files directly from the file system when assembling a brief, so that the latest merged PRs are instantly reflected without caching staleness.
8. As the CEO, I want to run `claudarama open` to start an interactive session with my Assistant, so that I can review batched reports and unblock gates using native Claude interactive tools.

## Implementation Decisions

- The daemon will act as both a Supervisor (managing an `asyncio.Queue` of turns and spawning `claude -p` subprocesses) and an MCP Server (exposing tools).
- The subprocesses will connect back to the daemon's MCP endpoint (`--mcp-server claudarama=http://localhost:<port>/mcp`).
- Storage will be split: `office.db` (SQLite) for `people`, `turns`, `messages`, and `briefs`. `.jsonl` files on disk for raw turn output logs.
- Turns are ephemeral: sending a message ends the turn gracefully. A reply queues a fresh turn with the updated thread context.
- Model escalation (the "stuck ladder") for stalled turns will be strictly opt-in via a flag in `org.yaml`. By default, stuck turns will fail.
- `claudarama open` will be a thin wrapper that launches an interactive `claude` process pointing to the daemon's MCP endpoint, seeded with the Assistant's prompt.

## Testing Decisions

- A good test only tests external behavior, not implementation details.
- We will test the daemon at two high-level seams:
  - **The MCP HTTP Seam**: An HTTP client connects to the in-memory/temp daemon and calls tools (e.g., `send`). We assert that the SQLite DB mutates correctly.
  - **The Supervisor Seam**: A mock executable is used instead of the real `claude -p`. We enqueue a turn and assert that the daemon spawns the mock, captures its output to disk, updates the DB status, and correctly handles stalls/crashes.
- Prior art: See `tests/test_cli.py` and `tests/test_scenario_runner.py` for how tests manage temp directories and subprocess mocking.

## Out of Scope

- Building the actual AI agent prompts or tools that do the coding (this sub-project is purely the infrastructure/runtime).
- Multi-machine clustering or remote deployment (this is a local daemon per machine).
- The full interactive terminal UI (CEO session relies on native `claude`).

## Further Notes

- See ADR 0001 for the rationale behind the Daemon Dual-Role architecture.
