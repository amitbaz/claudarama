---
status: superseded by ADR-0003
---

# Daemon Dual-Role Architecture

The office daemon serves two distinct roles simultaneously: it acts as a Supervisor that spawns and monitors `claude -p` turns, and as an MCP Server that those same turns connect back to.

We decided on this "loop" architecture (where the daemon passes `--mcp-server claudarama=http://localhost:<port>/mcp/<token>`, a secret per-turn token that identifies the caller, to the `claude` subprocesses it spawns) because it keeps all state mutations safely inside the daemon via MCP tool calls. The Supervisor part is relieved of executing business logic and only needs to monitor the `stdout` for crash or stuck detection. While slightly surprising, this cleanly decouples the process lifecycle management from the office rules and domain logic.
