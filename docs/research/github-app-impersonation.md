# GitHub App Impersonation Capabilities

## Context
Can a single GitHub App act as/impersonate multiple distinct named users (e.g., Bender vs Leela) when commenting or committing, or do all actions show up as a single bot identity? 

## Findings

The capabilities depend on the specific action (committing vs. commenting) and how the App authenticates.

### 1. Issue and Pull Request Comments
**No, a single GitHub App cannot natively impersonate multiple fictional identities when commenting.**

When a GitHub App uses its **Installation Access Token** (server-to-server) to post a comment, the action is entirely attributed to the App itself. 
- **Visual Identity:** The comment appears under the App's single name and avatar (e.g., `claudarama[bot]`).
- **Audit Logs:** The activity is attributed to the GitHub App installation.
- **Customization:** The GitHub API does not support specifying a custom display name or avatar override per-comment.

**Workarounds for Comments:**
1. **Body Prefixing:** Prefix the comment body with the persona's name (e.g., `**Bender:** ...`).
2. **User-to-Server Authentication:** If the App acts on behalf of a *real* GitHub user who authorized the App via OAuth, the comment is attributed to that user (the UI shows the user's avatar with an overlaid App badge). This requires maintaining separate "machine user" GitHub accounts for each persona and authenticating them via the App.

### 2. Git Commits
**Yes, a single GitHub App can author commits under multiple distinct fictional names.**

When using the GitHub REST API (or raw Git commands) to create a commit, you can explicitly provide custom `author` and `committer` objects containing an arbitrary `name` and `email`.
- **Author Identity:** If the App provides `{"name": "Bender", "email": "bender@planetexpress.com"}` to the Create a Commit API, the commit author will display as "Bender".
- **Signature Verification:** Providing custom author/committer info alters standard GitHub App automatic commit signing.

## Conclusion
For commenting, you are tied to the single App bot identity (e.g., `claudarama[bot]`) unless you manage multiple real GitHub machine accounts. For commits, you can freely set the `name` and `email` properties to impersonate distinct personas.

## Primary Sources
- [Authenticating as a GitHub App installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
- [Authenticating on behalf of a user](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-on-behalf-of-a-user)
- [GitHub REST API - Create a commit](https://docs.github.com/en/rest/git/commits#create-a-commit)
