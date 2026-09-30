# Sub-project 3: Server and Runtime

This spec details the Server and Runtime architecture for Claudarama, satisfying sub-project 3 of the blueprint. 

## 1. Daemon Architecture

The office daemon (`claudarama up`) serves two distinct roles simultaneously:
1. **Supervisor**: It manages an `asyncio.Queue` of incoming work, spawns headless `claude -p` subprocesses for each turn, and monitors their JSON `stdout` for completion, crashes, or stalls.
2. **MCP Server**: It uses the `FastMCP` framework to expose the office tools (`send`, `hire`, `mandate`, etc.).

**The Loop**: When the supervisor spawns a turn, it passes `--mcp-server claudarama=http://localhost:<port>/mcp`. This means the subprocess connects back to the daemon to perform state mutations. The supervisor part executes no business logic; it merely routes tools and monitors lifecycle health. (See ADR-0001).

## 2. Concurrency and Ephemeral Turns

Turns are strictly ephemeral and stateless beyond their generated brief. 
- A turn is a single run of a task or assignment. 
- If a person sends a message using a tool and must wait for a reply, their turn finishes cleanly (marked `done`).
- When the reply arrives, the daemon queues a brand new turn for that person. The new brief will contain the updated thread.
- The daemon pulls work from an SQLite `turns` table into an `asyncio.Queue`, processing up to `N` concurrent turns.

## 3. Storage Strategy

Storage is split between a fast local database and flat files:
- **`office.db` (SQLite)**: Holds relational and fast-moving state.
  - `people` (id, name, craft_or_seat, level, manager)
  - `turns` (id, person_id, status, error_message, log_path, created_at, updated_at)
  - `messages` (id, thread_id, sender_id, receiver_id, ticket, body, type)
  - `briefs` (turn_id, content)
- **Disk**: Raw JSON output streams from `claude -p` are written to `~/.claudarama/<project>/turns/<turn_id>.jsonl`. Only the file path is stored in the database to prevent SQLite bloat.

## 4. Brief Assembly

Briefs are built precisely at the moment a turn is moved from `queued` to `running`. The daemon mixes two sources of truth:
1. **File System**: Reads `docs/company.md`, `.claudarama/org.yaml`, and role/craft files directly from the worktree. This ensures the prompt always reflects the latest merged pull requests.
2. **Database**: Fetches active `messages` threads (via `thread_id`) and injects them under an "Active Inbox & Threads" section.

## 5. Health and Escalation

- **Crashes**: A non-zero exit code triggers one standard retry on the same model.
- **Stuck Turns**: Defined as no JSON output for 20 minutes. By default, stuck turns fail and pause.
- **Model Escalation**: The "stuck ladder" (e.g., automatically trying a more capable model on a new branch) is strictly opt-in via a flag in `org.yaml`. It is disabled by default to prevent unexpected token consumption.

## 6. The CEO Session

The CEO interacts with the office via `claudarama open`. This is a thin wrapper that launches a standard interactive `claude` process, seeded with the Assistant's prompt, pointing at the daemon's MCP endpoint. The Assistant uses native Claude interactive tools to present batched reports and fetch gate approvals from the CEO.
