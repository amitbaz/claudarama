# The office server runs inside sessions, with no daemon

The office has no background daemon and no `claudarama up`. Claude Code starts the office server as an ordinary MCP server process: one with the CEO's session (declared by the plugin, and passed by `claudarama open`), and one for each turn, all sharing the office's SQLite file. The server that belongs to the CEO's open session also launches and monitors turns, under a lock so only one session runs an office. We chose this because a plugin user should have nothing to start, stop or find, because it removes ports and so lets offices for several projects run side by side, and because it is how Claude Code plugins already work.

This supersedes ADR-0001's single HTTP daemon. Two things carry over from it: every state change still goes through an MCP tool call, and each turn still carries a secret token that identifies the caller. The token is now handed to the turn's own server process rather than placed in a URL.

## Considered Options

- **Keep the daemon and start it automatically from `open`, on a port it picks.** A smaller change, and the office keeps working with no session open. It leaves a background process to track and a port that the plugin's static server config has to discover.

## Consequences

- The office works only while the CEO's session is open. Closing it pauses the office; queued work stays in the database and resumes at the next open.
- The phone push for an open gate depends on that same open session, so the two constraints coincide.
- Several processes write one SQLite file, so correctness rests on SQLite's own locking rather than on a single writer.
- The machine-wide cap on simultaneous turns is kept through the shared slots file, since no single process sees every office.
