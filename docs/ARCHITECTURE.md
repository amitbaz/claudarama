# Technical Architecture

This document defines the technical architecture of the Claudarama plugin, the underlying office server, and how state is managed.

## 1. Core vs. Pack

To ensure Claudarama can run a software company for *any* project without losing quality, the system is strictly split into two halves:

### The Core (`claudarama` plugin)
The Core is the project-agnostic engine, located in this repository. It contains:
*   The generic Role definitions (PM, Engineering Lead, Researcher, etc.).
*   The Ritual mechanisms and office skills.
*   The office server and database schema.
*   The gate hook and enforcement logic.

### The Pack (`.claudarama/` directory)
The Pack lives inside the target project's repository. It injects context into the Core:
*   `company.md`: The charter and Key Results.
*   `stack.yaml`: The allowed CLI commands, tests, and CI logic.
*   `org.yaml`: The concurrency cap and turn health settings.
*   `gates.yaml`: Extra deny rules and key access routes.
*   `profiles/*.md`: Project-specific overlays appended to the generic crafts.

## 2. The Office Server & State

The office has no daemon and nothing to start first (ADR-0003). The office server runs inside sessions.

*   **Shape:** Claude Code starts the office server as an ordinary MCP server process over stdio: one for the CEO's Session (passed by `claudarama open`, declared by the plugin) and one for each turn. No process listens on a port, so offices for several projects run side by side.
*   **Callers:** Each server process is handed the secret token that names its caller. A turn's token dies with the turn, and only the owner token, held by the CEO's Session, may take a gated action. Every state change goes through an MCP tool call.
*   **State:** Storage is handled by one SQLite file per office (`~/.claudarama/<project>/office.db`), using full-text search. All of the office's server processes share it, so correctness rests on SQLite's own locking rather than on a single writer. The server makes no model calls and computes no embeddings itself.
*   **Running turns:** The server that belongs to the CEO's Session launches the queued turns and monitors each until it finishes. It does so under the office's lock, so only one Session runs an office: a second Session on the same project leaves the running office alone, and takes over if the first closes.
*   **Pause and resume:** The office works only while a Session is open. Closing the Session stops the running turns and pauses the office; queued work stays in the database. At the next open, turns that were left running are queued again.
*   **Runtime (Conversations over Processes):** For each turn the Session's server builds a fresh brief and starts a fresh Claude Code conversation (`claude -p`). It streams the JSON output to a transcript beside the office's database, and then the process exits. A failed launch records its error output on the turn. There are no idle CPU costs for waiting members.
*   **Concurrency:** An office runs at most a set number of turns at once (`concurrency` in `org.yaml`, default 3), and a Role runs one turn at a time. A machine-wide cap (default 10) is kept through a shared slots file under `~/.claudarama/`, since no single process sees every office.

## 3. Communication & The CEO

Communication operates primarily in the terminal.

*   **The Assistant (`claudarama open`):** The CEO's Session. It batches reports and requests decisions on blocking gates.
*   **Push Notifications:** If the CEO is AFK and the office hits a blocking gate or finishes a mandate, the Session's server triggers a native macOS push notification. With no Session open the office is paused, so there is nothing to notify.

## 4. Gate Enforcement

The architecture enforces the CEO's gates mechanically, not just via prompt text:
*   A PreToolUse hook checks every tool call against a strict allowlist (generated from `stack.yaml` and `gates.yaml`).
*   The hook denies agents any access to `~/.claudarama/` where the SQLite state and owner tokens live.
*   The server pauses the office immediately if the provider usage limit is hit, preventing runaway spend.
