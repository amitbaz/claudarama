# Gated actions run only in the CEO's session

Headless turns never receive permission for a gated action (money, staging and production, hosted databases, CI, secrets, repository settings). A person who needs one ends their turn with a BLOCKED message; the Assistant proposes the exact command in the CEO's `claudarama open` session, and Claude Code's own permission prompt there is the CEO's approval. We chose this so every gate is enforced by a mechanism rather than prompt text, and so nothing that loosens permissions ever flows into a headless turn.

## Considered Options

- **The CEO performs gated actions by hand.** Safe, but it turns the CEO into the office's operator for every migration and deploy.
- **Approval issues a one-time allow rule for the requester's next turn.** Keeps the work with the person who asked, but builds a path by which permissions grow in headless turns, and a forged approval would be enough to use it.

## Consequences

- `claudarama talk <name>` sessions carry that person's identity and allowlist, not the owner's, so they are not a second place for approvals.
- Gated work is serialised through the CEO's presence: when the CEO is away, it waits, and the daemon sends a push notification.
