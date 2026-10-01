# Technical Architecture

This document defines the technical architecture of the Claudarama plugin, the underlying office server, and how state is managed.

## 1. Core vs. Pack

To ensure Claudarama can run a software company for *any* project without losing quality, the system is strictly split into two halves:

### The Core (`claudarama` plugin)
The Core is the project-agnostic engine, located in this repository. It contains:
*   The generic Role definitions (PM, Engineering Lead, Researcher, etc.).
*   The Ritual mechanisms and office skills.
*   The Office Server daemon and database schema.
*   The gate hook and enforcement logic.

### The Pack (`.claudarama/` directory)
The Pack lives inside the target project's repository. It injects context into the Core:
*   `company.md`: The charter and Key Results.
*   `stack.yaml`: The allowed CLI commands, tests, and CI logic.
*   `org.yaml`: The concurrency cap and turn health settings.
*   `gates.yaml`: Extra deny rules and key access routes.
*   `profiles/*.md`: Project-specific overlays appended to the generic crafts.

## 2. The Office Server & State

The heart of the office is a local background daemon that manages asynchronous agents, state, and memory.

*   **Shape:** One local daemon serves every office on the machine. It exposes an MCP HTTP server on localhost.
*   **State:** Storage is handled by one SQLite file per office (`~/.claudarama/<project>/office.db`), using full-text search. The server makes no model calls and computes no embeddings itself.
*   **Runtime (Conversations over Processes):** When a ticket is assigned, the daemon starts a fresh Claude Code conversation (`claude -p`) in the project's worktree. It builds a fresh brief, streams the JSON output into the database, and then the process exits. There are no idle CPU costs for waiting members.
*   **Concurrency:** The daemon enforces an active turn limit per office (defined in `org.yaml`, default 3) and a global machine limit (default 10). 

## 3. Communication & The CEO

Communication operates primarily in the terminal.

*   **The Assistant (`claudarama open`):** The CEO's interactive session. It batches reports and requests decisions on blocking gates.
*   **Push Notifications:** If the CEO is AFK and the office hits a blocking gate or finishes a mandate, the daemon triggers a native macOS push notification.

## 4. Gate Enforcement

The architecture enforces the CEO's gates mechanically, not just via prompt text:
*   A PreToolUse hook checks every tool call against a strict allowlist (generated from `stack.yaml` and `gates.yaml`).
*   The hook denies agents any access to `~/.claudarama/` where the SQLite state and owner tokens live.
*   The server pauses the office immediately if the provider usage limit is hit, preventing runaway spend.
