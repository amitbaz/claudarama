---
label: wayfinder:research
blocked_by: []
closed: true
---

# GitHub App Impersonation Capabilities

## Question

Can a single GitHub App act as/impersonate multiple distinct named users (e.g., Bender vs Leela) when commenting or committing, or do all actions show up as a single bot identity? We need to know this to design how the AI staff interacts on GitHub.

## Resolution

**No for comments, Yes for commits.**

When posting comments (issues/PRs) using an App Installation token, the identity is strictly tied to the App (e.g., `claudarama[bot]`). You cannot customize the display name or avatar per-comment.

When authoring commits via the API or git, you can pass custom `name` and `email` for the `author` and `committer` fields to impersonate distinct personas.

See `docs/research/github-app-impersonation.md` for full details.
