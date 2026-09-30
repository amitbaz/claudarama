# oh-my-claudecode teardown: what gili-office should adopt (2026-09-29)

Status: proposal for the owner. Nothing here is adopted until the owner decides and the office changes at a planned restart.

Sources:
- oh-my-claudecode (OMC) v5.5.0 at `9fd35ec` (2026-09-22), MIT, <https://github.com/Yeachan-Heo/oh-my-claudecode>.
- The office as `plugins/gili-dev` 0.9.1 on `main` at `78eeece`.
- Claude Code docs for hooks, permissions and plugin layout (links inline).

OMC paths are relative to its repository root. Office paths are relative to `plugins/gili-dev/`.

## Summary

- **Don't fork OMC; take its ideas.**
  - Size: OMC is about 199K lines of TypeScript plus 250K lines of tests. The office is about 1K lines of scripts and 1.6K lines of markdown.
  - Pace: OMC had about 415 commits last month and ships a release roughly weekly.
  - Coupling: OMC writes `~/.claude/CLAUDE.md` and the `statusLine` in `~/.claude/settings.json`.
  - Fit: its model is one developer's session that keeps working until done. The office is a company with gates. What makes OMC worth studying is a set of mechanisms, and each is small to copy.
- **The office's biggest gap is that every gate is prose.**
  - `scripts/open-session.sh:67` starts every session with `--dangerously-skip-permissions`, and the plugin has no hooks.
  - `roles/common.md:51` says: "Nobody is prompted for permission in the office, so these rules are the only guard."
  - Claude Code still enforces two things in that mode, so this is cheap to fix:
    - a PreToolUse hook that returns `permissionDecision: "deny"`;
    - permission deny rules, including `--disallowedTools`.
  - Source: [hooks guide, "Hooks and permission modes"](https://code.claude.com/docs/en/hooks-guide) and [SDK permission evaluation order](https://code.claude.com/docs/en/agent-sdk/permissions).
- **Fix the scenario harness first.** It has two verified bugs (below). Every "scenario evals prove role changes" claim depends on it.
- **Rename `gili-dev` to `gili-office` and use the full plugin surface**: hooks, `bin/`, agents and skills. Skip `commands/`, because plugin skills are already slash commands. Defer an MCP server until a tool needs shared state that files cannot hold. The touch list is below.
- **Candidate count: 37.** 15 are ADOPT, 21 are ADAPT and 1 needs an owner decision. Most are effort S. A skip list with reasons follows the candidates.

## What OMC is

OMC is a Claude Code plugin plus an npm CLI (`omc`). It has five main parts:
- **Agents and skills.** 19 agents (`agents/*.md`, tiered Opus, Sonnet and Haiku) and 43 skills. The 21 files in `commands/` are thin wrappers of those skills.
- **Hooks.** 26 hook entries (`hooks/hooks.json`) run `node scripts/*.mjs`.
- **An MCP server** (`.mcp.json`, `bridge/mcp-server.cjs`) with state, notepad, memory, wiki, trace, LSP and ast-grep tools.
- **A tmux team runtime** (`src/team/`) that runs Claude, Codex, Gemini and other CLI workers through file mailboxes.
- **Execution modes**: autopilot, ralph, ralplan, team, deep-interview and ultragoal. Mode state lives under `.omc/state/`, and a Stop hook keeps the session going while a mode is active.

It is extensible without forking only at the margins. You can change config (`.claude/omc.jsonc`: model tiers, keywords, a `companyContext` tool slot) and add learned skills (`.omc/skills/`). There is no way to add roles, gates or approval rules.

## What the office is today

- **The Assistant** is the owner's own session. It coordinates and never edits code.
- **The other roles** each run in a detached tmux session with a `uds:` address: CTO, CPO, PM, tech lead, frontend lead, and specialists with staff profiles. `scripts/open-session.sh` opens them.
- **Work flows** from an approved mandate to epics, which `plan.py` turns into a plan. START grants carry a spend cap, and seats are capped at 3 specialists and 7 sessions.
- **The lead ships work.** It runs `ship-check` (SHIP or REWORK) plus three review gates, then `ship-pr` (CodeRabbit, local CI, squash-merge).
- **State** is `~/.gili-office/current.md` plus per-role handovers on GitHub.
- **Proof** is 12 scenario files run headless through `run-scenario.py`.

## Fix first: two scenario-harness bugs (verified 2026-09-29)

1. **The judge passes on any reply containing "PASS".**
   - `skills/office/scripts/run-scenario.py:50` returns `"PASS" in stdout.upper()`. A judge reply such as "FAIL: does not pass" counts as a pass.
   - Fix: have the judge return JSON `{"pass": bool, "reason": str}` and parse it strictly. OMC's `skills/autoresearch` requires the same: "structured JSON with required boolean `pass`".
2. **`no-pkill.json` cannot fail on `pkill`.**
   - Its `excludes` are `"\\\\bpkill\\\\b"`, which decodes to the regex `\\bpkill\\b`. That regex matches a literal backslash, never "pkill".
   - Checked: `re.search` against `run pkill -f sleep` returns `False` for both patterns.
   - Fix: use `"\\bpkill\\b"`. Also add a self-test that every `excludes` pattern matches a planted bad reply.

## The gili-office plugin: which surfaces to use

| Surface | OMC uses it for | gili-office would use it for | Verdict |
|---|---|---|---|
| `hooks/hooks.json` | 26 entries: keyword routing, Stop-loop modes, context injection, checkpoints | Gate refusals, compaction checkpoint and restore, heartbeat, SessionEnd notice | ADOPT, with an env gate (below) |
| `--settings` file from `open-session.sh` | not used | Native `permissions.deny` rules for office sessions only | ADOPT |
| `bin/` | `oh-my-claudecode.js` CLI shim | `office-health`, `remove-worktree`, the gate scripts, as bare commands | ADOPT |
| `agents/` | 19 tiered agents, `disallowedTools` on read-only ones | Keep the 5 staff profiles. Enforce review-only through `open-session.sh --review`, not frontmatter, because the same profiles also build | Keep |
| `skills/` | 43 skills | Keep the office skills; add the changes listed below | Keep |
| `commands/` | 21 thin wrappers over skills | Nothing. Plugin skills already run as `/gili-office:<skill>` | SKIP |
| MCP server | state, notepad, memory, wiki, trace tools | Nothing yet. MemPalace already covers memory and events; files and scripts cover office state | DEFER |

### Hook scoping

Plugin hooks load in every session that has the plugin enabled. `gili.careers/.claude/settings.json:17` enables `gili-dev` for every session in that repository, so an unscoped office hook would fire in the owner's ordinary coding sessions. Use two layers:

1. **Hard denies** go in an office settings file that `open-session.sh` passes with `--settings`.
   - It uses native `permissions.deny` rules, for example `Bash(gh auth switch *)`.
   - It uses `--disallowedTools` for whole tool families.
   - These rules exist only in office sessions and hold even in bypass mode.
2. **Plugin hooks** cover what rules cannot express: explaining refusals, the compaction checkpoint, heartbeats, and checking comment bodies.
   - Each hook exits at once unless `GILI_OFFICE_ROLE` is set. `open-session.sh` exports it.
   - Gate hooks fail closed: on a parse error or timeout they deny with "gate hook failed; ask the owner".
   - Do not copy OMC's catch-all `{continue:true}` on error, or its `DISABLE_OMC` / `OMC_SKIP_HOOKS` escape switches.

Verify against the pinned Claude Code version before relying on them:
- how prefix rules like `Bash(gh auth switch *)` treat chained commands;
- the `--disallowedTools` glob syntax for MCP tools.

### `bin/` caveat

`bin/` has been on the Bash tool `PATH` since Claude Code 2.1.91 ([what's new, 2026 w14](https://code.claude.com/docs/en/whats-new/2026-w14)). claude.ai organization plugin distribution rejects a plugin with a top-level `bin/` ([plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)). That only matters if this marketplace is ever distributed through organization settings.

## Adoption candidates

Effort: S is under a day, M is one to three days, L is more. Verdicts:
- **ADOPT**: take the idea as is.
- **ADAPT**: take the idea, change the shape.
- **OWNER**: needs an owner decision first.

### A. Gates as mechanism

**A1. Office deny list for Bash and file writes. ADOPT, M.**
- **OMC:** it has the deny mechanism but no gate content. `scripts/pre-tool-enforcer.mjs:420-427` returns `hookSpecificOutput.permissionDecision: "deny"` with a reason, and it blocks no destructive commands.
- **Office today:** prose in `roles/common.md:48-58`, plus one scenario (`no-pkill.json`).
- **Proposal:**
  - Settings deny rules and a PreToolUse hook refuse:
    - `gh auth switch|logout|login|refresh|token`;
    - unsetting or reassigning `GH_TOKEN`;
    - `git push` to `main`, `--force`, `git rebase`;
    - `gh secret|variable`, `gh workflow run`, and `gh api -X PUT|PATCH|DELETE` on repo settings;
    - `coderabbit --use-credits`, `vercel --prod`, `supabase db push|link`;
    - `pkill`, `killall`;
    - Write or Edit to `.github/workflows/**`, `.coderabbit.yaml`, `.env*`.
  - Each refusal is appended to `~/.gili-office/audit.jsonl` (session, command, rule), following OMC's `delegation-audit.jsonl` in `src/hooks/omc-orchestrator/audit.ts`.
  - Example refusal: `[OFFICE GATE] 'gh auth switch' is refused in office sessions: the GitHub identity is set by the owner. Send the Assistant an owner-only request (what, why, cost).`
- **Risk:** regexes can be evaded, for example with `bash -c "$(...)"`. That matches the 2026-09-28 direction: credentials enforce, and hooks explain.
- **Test:** `hooks/*.test.sh` pipes fixture JSON on stdin, like `open-session.test.sh`.

**A2. Remove hosted-infrastructure connector tools from office sessions. ADOPT, S.**
- **Problem:** office sessions inherit the owner's claude.ai connectors, including Vercel (`create_deployment`, `buy_domains`), Supabase (`apply_migration`, `execute_sql`) and Render (`trigger_deploy`).
- **Proposal:** `open-session.sh` passes `--disallowedTools` for `mcp__claude_ai_Vercel__*`, `mcp__claude_ai_Supabase__*` and `mcp__plugin_render_render__*`. A1's hook denies the same patterns as a backstop.
- **Why it matters:** this is the widest unguarded money and production path found.

**A3. Review-only sessions. ADOPT, S.**
- **OMC:** `disallowedTools: Write, Edit` in the frontmatter of its verifier, critic, code-reviewer, security-reviewer, analyst, architect and explore agents. It is read in `src/agents/utils.ts` `parseDisallowedTools()`.
- **Proposal:**
  - `open-session.sh --review` adds `--disallowedTools "Edit Write NotebookEdit"` and `OFFICE_MODE=review`. A1's hook then also denies `git commit|push`.
  - Leaders may Write only under `~/.gili-office/` and the scratch directory, using OMC's path allowlist idea (`isAllowedPath()` in `src/hooks/omc-orchestrator/index.ts`).
- **Don't:** put `disallowedTools` in `agents/*.md`, because the same profiles also build.

**A4. Review verdicts only from the reviewing role. ADAPT, M, needs owner sign-off on cost.**
- **OMC:** `agents/verifier.md` says "Never self-approve or bless work produced in the same active context", and `agents/code-reviewer.md` says "Never approve your own authoring output".
- **Office today:**
  - `ship-check/scripts/review-gate.sh` accepts the latest comment starting with the gate mark (for example `🧱 **Database architect review.**`).
  - Every session shares one `gh` login, so the author can post it.
  - `roles/lead.md` says "A ticket the gate's own profile built carries its own approval".
- **Proposal:** A1's hook denies a `gh issue comment` whose body starts with a gate mark unless `GILI_OFFICE_ROLE` is that profile in review mode. Own-profile tickets then get a separate review session, and `open-session.sh` accepts a ` review` name suffix.
- **Cost:** one extra seat and some model spend per gate-profile ticket.
- **Later:** the per-role GitHub App bots from 2026-09-28 make this a credential check instead of a regex.

**A5. START grant as a file the scripts check. ADAPT, S.**
- **OMC:** plans stay `pending approval` until approved, and the ultragoal CLI rejects checkpoints without gate JSON (`src/ultragoal/artifacts.ts`).
- **Office today:** "Start a specialist only on `START`" is prose in `roles/lead.md`.
- **Proposal:**
  - On START the Assistant writes `~/.gili-office/grants/<ticket>.json` (mandate approval link, spend cap, time).
  - `new-worktree.sh` and `open-session.sh` refuse a `#<ticket> <profile>` session without that file.
  - PARK or merge deletes it.
- **Risk:** any same-user session could forge the file. It still turns "forgot" into "deliberately forged", and leaves a trail.

**A6. Seat limits enforced in `open-session.sh`. ADOPT, S.**
- **OMC:** clamps workers in code: `resolveMaxWorkers` in `src/team/governance.ts` and `ABSOLUTE_MAX_WORKERS` in `src/team/types.ts`.
- **Office today:** the Assistant counts seats from `OPENED`/`CLOSED` messages.
- **Proposal:**
  - `open-session.sh` reads `~/.gili-office/limits` (`sessions=7 specialists=3`) and counts `tmux ls` names matching `^gili-` but not `^gili-setup-`. It exits 65 at the cap.
  - Reserve one seat for the Assistant, which may not be named `gili-*`.
  - Add the cases to `open-session.test.sh`.

**A7. SHIP verdict bound to the exact head commit. ADOPT, S.**
- **OMC:** `src/ultragoal/artifacts.ts` refuses the final story without a clean code-review verdict. `skills/harbor/SKILL.md` says: "A merge approval binds to the exact PR head."
- **Office today:** the lead sends `SHIP #n`. `ship-pr` merges on CI plus `--match-head-commit`, and nothing checks that a lead verdict exists for that head.
- **Proposal:**
  - The lead posts `Lead ship-check: Ready at <sha>`.
  - A new `ship-check/scripts/ship-gate.sh` (reusing `review-gate.sh`) runs just before `gh pr merge`. It refuses if no Ready verdict matches the head.
  - Docs-only pushes stay exempt, as `ship-pr` step 5 already allows.

**A8. Criterion amendment ledger. ADAPT, M.**
- **OMC:** `skills/ralph/SKILL.md` `<PRD_Criterion_Amendments>`: the original is "retained verbatim" with reason, evidence, authority and timestamp. "An amendment without bounded evidence… is invalid — the PRD fails closed."
- **Office today:** `cpo.md` "Criterion changes" and `ticket-comment/templates/criterion-changed.md` record Before, Now and Why. They have no evidence or authority field, and nothing catches a silent edit.
- **Proposal:**
  - Add `Evidence:`, `Decided by:` and a `<!-- CRITERION-CHANGED -->` marker to the template.
  - At START, the lead saves the ticket's checkbox lines to `~/.gili-office/criteria/<n>.txt`.
  - A `criteria-gate.sh` in ship-check fails when a criterion was removed or reworded without a marker comment.

### B. Proof and evals

**B1. Fix the two harness bugs** (see above). **ADOPT, S.** Do this first.

**B2. Scenario-file checker with no model calls. ADOPT, S.**
- **OMC:** `tests/harbor-scenarios.test.ts` checks every scenario for decidability and a declared list of forbidden actions.
- **Proposal:** `test_scenarios.py` beside `run-scenario.py`. It checks that:
  - each `role` exists in `roles/`;
  - there is at least one include pattern or a judge;
  - every pattern compiles;
  - every `excludes` pattern matches a planted bad reply.
- It runs free in CI (B8).

**B3. Seal existing scenarios against the PR that changes a role. ADOPT, S–M.**
- **OMC:** `skills/self-improve/scripts/validate.sh` keeps sealed files "so benchmark code cannot be modified by the loop".
- **Proposal:** a test fails when one diff touches `roles/` or `agents/` and also loosens or deletes an existing scenario's `checks` or `judge`. New scenarios are allowed. An owner-labelled PR is the exception path, and B1 needs it.

**B4. Clean-control twins. ADAPT, S per twin.**
- **OMC:** every `benchmarks/*/ground-truth/*.json` has `isCleanBaseline` fixtures that penalise false alarms.
- **Proposal:** each refusing or flagging scenario gets a twin where the correct behaviour is to accept. For example, `database-architect-flags-missing-rls` gets `database-architect-accepts-correct-rls`. This catches roles that over-refuse.

**B5. Repeated runs and old-versus-new comparison. ADAPT, M.**
- **OMC:** `benchmarks/run-all.ts --save-baseline/--compare`. Its README advises averaging 3 runs. Its committed baseline is placeholder zeros, so skip committed baselines.
- **Proposal:**
  - `run-scenario.py --runs N`: default 3; pass when at least N−1 runs pass.
  - `run-scenario.py --against <git-ref>`: builds the prompt from the old role file and reports pass-rate changes. The table goes in the role-change PR.
- **Cost:** triples the cost per check, which is paid and local only.

**B6. Incident closure receipt. ADAPT, S–M.**
- **OMC:** `receipts/issue-*/merged.receipt.json` records issue, PR, the exact commit the checks ran on, the merge commit and the verdict. A failed CI result stays on record.
- **Office today:** the 2026-09-28 rule "office-incident closed only with a linked scenario" has no enforcement yet.
- **Proposal:** the closing comment carries a fenced JSON block `{incident, scenario_path, scenario_sha, pr, head_sha, runs, passes}`. A `gh`-based check refuses to close without it, or when `scenario_path` is missing on `main`.

**B7. Hook tests from stdin fixtures. ADOPT, S.**
- **Problem:** `run-scenario.py` runs `claude --print --tools ""`, so no hook ever fires in a scenario.
- **Proposal:** each hook gets a `.test.sh` that pipes recorded hook JSON in and checks the decision JSON out. These count as the "linked scenario" for hook incidents.

**B8. CI workflow for the free checks. ADOPT, S.**
- **OMC:** `.github/workflows/ci.yml` and `pr-check.yml`.
- **Office today:** no workflow. `.github/` holds only an issue template.
- **Proposal:** one workflow running `agents.test.sh`, the `*.test.sh` scripts, `pytest` for office scripts, and B2. It makes no model calls. Paid scenario runs stay local, as the owner directed.
- **Note:** CI workflow changes are owner-only, so the owner merges this one.

**B9. Fresh evidence in ship-check. ADAPT, M.**
- **OMC:** `agents/verifier.md`: "Run verification commands yourself. Do not trust claims without output." Its evidence table is `Check | Result | Command/Source | Output`.
- **Office today:** `ship-check` proof rows cite code and tests but run nothing. Tests first run in `ship-pr` local CI, after SHIP.
- **Proposal:** run the tests named in the proof rows through the stack lock and record command, exit code and head SHA. A move of the head makes the verdict stale, which ties in with A7.

**B10. Blocker-pattern scan at ship time. ADAPT, S.**
- **OMC:** `scripts/workflow-drift-guard.mjs` blocks a "done" claim while changed files contain `.only(`, `.skip(`, TODO-implement or `throw new Error("Not implemented")`.
- **Proposal:** make the same pattern list a blocking step in `ship-check`, not a Stop hook. A long-running tmux role has no single final stop.

### C. Continuity

**C1. Checkpoint before compaction, restore after. ADAPT, M.**
- **OMC:**
  - `src/hooks/pre-compact/index.ts` writes `.omc/state/checkpoints/checkpoint-<ts>.json` holding pointers, not copies.
  - `scripts/session-start.mjs` restores it when `source == "compact"`, capped at 1,200 characters, ignoring checkpoints over 24h old, once per session.
- **Office today:** nothing, and `open-session.sh` turns MemPalace auto-save off.
- **Proposal:**
  - A PreCompact hook writes `~/.gili-office/checkpoints/<role>-<ts>.md` with role, run key, ticket, branch, boss address and the C2 pin. For the Assistant it also copies `current.md`'s Pending decisions, Working and Limits sections.
  - A SessionStart hook on `compact` injects the newest checkpoint, ending with: "Reread your latest handover (`gh issue view <n> --comments`) before acting. Never recover spend or direction from this summary."

**C2. A 500-character pinned note per role. ADAPT, S.**
- **OMC:** `.omc/notepad.md` `## Priority Context` (at most 500 characters), injected every SessionStart by `src/hooks/notepad/index.ts`.
- **Proposal:** each role rewrites `~/.gili-office/<run>/<Role>.pin.md` on state change, and C1 injects it. Example: "#843: RLS migration drafted, waiting on DB architect review; don't touch auth.ts". Skip OMC's working-memory and manual sections, because MemPalace and handovers cover them.

**C3. Decided, Rejected and Risks in the handover. ADAPT, S.**
- **OMC:** `skills/team/SKILL.md` stage handoffs have Decided, Rejected (with why), Risks, Files and Remaining, in 10–20 lines.
- **Office today:** `ticket-comment/templates/handover.md` has Status, Completed, Pending/Blockers and Links. A reopened role can re-open settled questions.
- **Proposal:** add the three sections, keeping "links, not pasted text". This stays per role, in line with the 2026-09-26 decision against one handover per epic.

**C4. Detect and resume sessions stuck on a rate limit. ADAPT, S–M.**
- **OMC:** `src/features/rate-limit-wait/tmux-detector.ts` matches `/rate limit/i`, `/usage limit/i` and `/resets? .+ at/i` in pane text and resumes after the reset.
- **Proposal:**
  - On each wake, the Assistant captures the last ~20 lines of each `gili-*` pane.
  - A match marks the row "rate-limited, resets <time>" in `current.md`, and the Assistant sends `continue` after the reset.
  - It sends a PushNotification only if the reset falls past 20:00 or blocks a pending CEO decision.
- **Skip:** OMC's OAuth usage endpoint, which is not a documented API.

### D. Liveness and recovery

**D1. `office-health`: measured liveness instead of a judgement call. ADOPT, S–M.**
- **OMC:**
  - `src/team/tmux-session.ts` treats "esc to interrupt" and spinner lines as busy, and a showing prompt as idle.
  - `src/team/runtime-v2.ts` combines pane state, heartbeat age and status age into stall reasons. "Unknown evidence never authorizes replacement."
- **Office today:** `roles/lead.md` "Health check" judges "no message, commit or screen change for 20 minutes" by hand.
- **Proposal:**
  - `bin/office-health` prints one JSON line per `gili-*` session: `alive`, `pane` (active, idle_prompt, usage_limit or lock_wait), `screen_changed_s`, `last_commit_age_s`, `verdict` (working, stalled, dead or waiting_stack).
  - It hashes `capture-pane` output to measure screen change.
  - `stalled` requires an idle prompt, no screen change for at least 20 minutes, and no DONE or BLOCKED recorded. An active pane is never killed.
- **Conflict:** see "Conflicts with earlier decisions" below.

**D2. Heartbeat from a hook, not a prompt. ADAPT, S.**
- **OMC:** `src/team/worker-commit-cadence.ts` writes a PostToolUse hook into the worker's worktree settings. Its prompt-driven heartbeat (`worker-bootstrap.ts`) is unreliable.
- **Proposal:**
  - `new-worktree.sh` merges PostToolUse and Stop hooks into `<worktree>/.claude/settings.local.json`. `gili.careers/.gitignore` already ignores `.claude/*`.
  - Each hook writes a timestamp to `~/.gili-office/health/<slug>.beat`, which D1 reads.
  - A Stop beat followed by silence means the specialist ended its turn without reporting.

**D3. One nudge before the stuck ladder. ADOPT, S.**
- **OMC:** `src/team/idle-nudge.ts` nudges idle workers, at most 3 times.
- **Proposal:** when D1 says `stalled`, the lead sends one "Status? Continue #<n>, or report SPECIALIST_BLOCKED." per attempt, then follows the existing Stuck ladder.

**D4. Separate restart policy for crashes and for stuck work. ADAPT, S.**
- **OMC:** `src/team/worker-restart.ts` allows 3 restarts on the same model with backoff. `worker-health.ts` separates "dead" from "hung".
- **Office today:** one path. A retry goes one model up on a new branch, then the ticket pauses. A crashed session has no specific rule.
- **Proposal:**
  - Crash (tmux gone, no DONE): reopen once on the same model, branch and worktree with `--handover-from`.
  - Stuck: keep today's ladder.
  - Add an `attempt` column to `current.md` Working.

**D5. Never force-remove a dirty worktree. ADOPT, S.**
- **OMC:** `src/team/git-worktree.ts` "cleanup never force-removes dirty worker changes" (it raises `worktree_dirty`).
- **Office today:** `roles/lead.md` runs `git worktree remove --force` in four places (Stuck, after merge, Park, Goodnight).
- **Proposal:** `bin/remove-worktree <path> <branch>` first commits `wip: checkpoint before removal` and pushes. It refuses if the push fails, and only then removes. Replace the four raw removals with it.

**D6. SessionEnd notice. ADAPT, S.**
- **OMC:** `scripts/session-end.mjs` runs async with a 300ms foreground budget.
- **Proposal:** an async SessionEnd hook appends a logstream event or messages the boss: "`#843 fullstack-engineer` session ended (reason)". The lead then sees a dead specialist before its timer fires. Fail open is fine here, since the hook only notifies.

### E. Role prompts (each proven by a new scenario)

**E1. Confidence on review findings, with a never-downgrade rule. ADAPT, S.**
- **OMC:**
  - `agents/code-reviewer.md` sends low-confidence CRITICAL/HIGH findings to Open Questions without blocking.
  - `agents/critic.md`: "NEVER downgrade a finding that involves data loss, security breach, or financial impact."
- **Proposal:**
  - Add `Confidence` and a non-blocking "Open questions" line to `agents/database-architect.md`, `designer.md` and `prompt-engineer.md`.
  - RLS, data-loss and paid findings are never downgraded.
  - Add a scenario proving an uncertain RLS finding still blocks.

**E2. Ambiguity scan in `ticket-ready`. ADOPT, S.**
- **OMC:** `agents/critic.md`: "Could two competent developers interpret this differently? If yes, document both interpretations."
- **Proposal:** a failing line `AMBIGUOUS: <quote> → A / B`, routed to the CPO through `product-question`. Add the scenario `pm-flags-ambiguous-criterion.json`.

**E3. Pre-mortem in mandate feasibility. ADAPT, S.**
- **OMC:** planner and critic deliberate mode require "pre-mortem (3 failure scenarios)".
- **Proposal:** one line in `roles/cto.md`: list 3 ways the outcome fails and the check that would reveal each.

**E4. Independent critic on mandate proposals. ADAPT, M.**
- **OMC:** `skills/ralplan` reviews a frozen plan snapshot. "Architect output MUST NOT be passed to Critic." It requires at least 2 options or a reason alternatives were ruled out.
- **Proposal:**
  - Before the CPO hands a mandate proposal to the Assistant, it runs one subagent critic, with no seat, on the frozen issue revision.
  - Checklist: options, a bar measurable today, and a pre-mortem when money, production or migrations are involved.
  - The verdict is posted on the issue. Extend `scenarios/cpo-next-outcome.json` to cover it.

**E5. Structured "what the last attempt learned". ADAPT, S.**
- **OMC:** `agents/tracer.md` output is Observation, ranked hypotheses, Critical Unknown, Discriminating Probe.
- **Proposal:** make the restart note in `roles/lead.md` "Stuck" four lines: observation, top 2 hypotheses, ruled out, next probe.

**E6. Standing approval rules and a reuse check. ADAPT, S.**
- **OMC:** `skills/harbor/SKILL.md`:
  - a repeated approval becomes "one rule, not repeating signatures";
  - a four-question reuse check runs before citing a past decision;
  - "Batch signing binds to the object list… displayed at signing time".
- **Proposal:**
  - `mandate-decision.md` gains a Standing rule block (scope, allowed actions, facts that must hold, exceptions, source).
  - The Assistant runs the reuse check before asking or skipping a question.
  - A "Start" approval covers only the tickets shown at that time. A5 gives this teeth.

**E7. `office-idea` duplicate rule. ADAPT, S.**
- **OMC:** `skills/launch`: "a concept-similar re-proposal must state what changed, or it is declined". `skills/skillify` has a three-question quality gate.
- **Proposal:** add both to `office-idea/SKILL.md` step 1.

**E8. Glossary and short decision records. ADOPT, S.**
- **OMC:** its `CONTEXT.md` gives each term a definition, a boundary and a resolved ambiguity. `docs/adr/*` records each decision in one paragraph that names the rejected option.
- **Proposal:**
  - Use that three-part format for office terms: role, specialist, seat, brief, grant, incident.
  - Record owner decisions as one-paragraph records. This keeps proposals separate from adopted behaviour, as `AGENTS.md` asks.

### F. Needs an owner decision

**F1. Codex as a one-shot, review-only second opinion. OWNER, M.**
- **OMC:**
  - `src/team/cli-worker-contract.ts` has review workers write `verdict-<task>-<attempt>.json` (`verdict: approve|revise|reject`, findings with severity, file and line).
  - A missing CLI fails startup and never falls back silently.
- **Proposal:** the lead runs `codex exec` in the ticket worktree, and `ship-check` reads the verdict as one more gate. It takes no seat and never builds or merges.
- **Needs owner:** this changes the "Claude only" rule and adds a billing line with its own cap.
- **Codex as a builder: SKIP.** It cannot use `uds:` messaging or `ship-pr`.

## Skip list

| OMC feature | Why not for the office |
|---|---|
| Ralph, ultragoal and autopilot "never stop" Stop hook (`scripts/persistent-mode.mjs`) | Office roles end their turn after a question and sleep on timers; a stop-blocker fights that and has no spend cap. The Stuck ladder covers persistence. Reuse only its safety rules (never block on `stop_hook_active`, context-limit stops, user aborts or auth errors; cap at 2 blocks) if a Stop hook is ever added. |
| Magic-keyword routing and skill injection (`keyword-detector.mjs`, `skill-injector.mjs`) | They need a human typing prompts. Office roles are briefed. |
| Deep-interview ambiguity score (`skills/deep-interview`) | The model scores itself, and it can take up to 20 rounds of owner attention. OMC's own `skills/intent` says its stop gate "is a completion gate, not an ambiguity score". E2 is the cheap version. |
| Task leases and claiming (`src/team/state/tasks.ts`) | Office work is pushed to one owner by START, so there are no competing claimers. |
| Merge orchestrator and auto-commit after every edit | One branch per ticket, squash-merged through `ship-pr`. D5 is the cheap safety net. |
| File inbox, outbox and `.ready` protocol | `uds:` messaging plus the "I am" message already do this. |
| Experimental agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) | They lose watchable tmux sessions, per-session models and worktree isolation. |
| State, shared memory, project memory, wiki and trace MCP tools | `current.md`, GitHub handovers and MemPalace already cover them. A second store would drift. |
| Discord, Telegram and Slack notifications with reply-to-pane | PushNotification meets the need. Replies typing into bypass-permission sessions are too risky. |
| HUD and statusline cost display | No one watches detached panes, and OMC has no per-ticket spend tracking. Its budget warning is described (`src/hud/types.ts`) but never built. |
| Subagent cost limit (`src/hooks/subagent-tracker`) | Advisory only (`auto_execute: false`). The Keychain wrapper and provider hard limits are the real mechanism. |
| PermissionRequest auto-allow | Never fires under bypass. It becomes relevant only if the office drops `--dangerously-skip-permissions`, which is a separate decision. |
| Deliverables per stage (`templates/deliverables.json`) | Its checker prints nothing in every branch. The office has no stage documents the lead checks by hand. |
| OMC's orchestrator and designer prompt text | "RELENTLESS EXECUTION" fights wake timers and GOODNIGHT. Its font rules fight `docs/design-language.md`. |
| AI-slop cleaner pass after review | It moves the head after approval and would break A7. CodeRabbit plus ship-check cover this. |
| Two model registries | OMC's frontmatter and `src/agents/definitions.ts` disagree (`security-reviewer` is `opus` in one and `sonnet` in the other). Keep the office's single source: profile pins checked by `open-session.sh` and `agents.test.sh`. |
| Installer that edits `~/.claude/CLAUDE.md` and settings | The marketplace install already loads the plugin. |
| SWE-bench, geobench, seminar, shellmark and inventory dirs | Marketing, leftovers or specific to their repository. |

## Conflicts with earlier decisions

- **D1 and D2 add health and heartbeat files.** On 2026-09-26 the owner decided: "Do not add phase-change messages or a worktree state file now; revisit only if false alarms continue." D1's state is derived from tmux and git, not reported by the specialist, but D2 is a state file. Treat both as the revisit case and let the owner decide.
- **F1** changes the "Claude only" rule.
- **A4** adds a review seat per gate-profile ticket. That is capacity the 2026-09-26 limits did not plan for.
- **B8** changes CI and repository settings in this repository, so the owner merges it.
- Everything else fits the 2026-09-26 decisions and the 2026-09-28 terminal-first direction.

## Rename: `gili-dev` to `gili-office`

References to update, found on 2026-09-29:
- **This repository:** 39 files mention `gili-dev`, including `.pytest_cache` and `__pycache__`.
  - `.claude-plugin/marketplace.json`, `plugins/gili-dev/.claude-plugin/plugin.json`, `README.md`.
  - Plugin `AGENTS.md`, `agents.test.sh`, `agents/frontend-engineer.md`, `agents/fullstack-engineer.md`.
  - Skills `office`, `ship-pr`, `ship-check` (including `scripts/db-review.sh`), `ticket-comment`, `ticket-ready`.
  - Role files `common.md`, `cto.md`, `lead.md`, `pm.md`, `specialist.md`, `duties/prompt-engineer.md`.
  - Office script tests, and `plugins/gili-evals/skills/prompt-engineering/SKILL.md`.
  - Dated docs and plans keep the old name as history.
- **gili.careers:**
  - `AGENTS.md:108,113,128` (`/gili-dev:ship-pr`, `/gili-dev:office`, `gili-dev:ship-check`);
  - `.claude/settings.json:17` and `.claude/settings.local.json:61` (`"gili-dev@gili-ai-marketplace": true`).
- **Local install:** `~/.claude/plugins/installed_plugins.json` holds `gili-dev@gili-ai-marketplace`. Install `gili-office` and uninstall `gili-dev`.
- **Cleanup at the same time:**
  - the stale `skills/office/scripts/__pycache__/wake-bridge*.pyc` left over from HQ;
  - the unused `scripts/office-comment.sh`;
  - the operating-model audit's dead link to `roles/worker.md`.

Do the rename at a planned restart, as the 2026-09-26 decision requires, so running roles never mix old and new names. Bump to `gili-office` 1.0.0.

## Suggested order

1. **Harness trust:** B1, B2, B7, B8. After this, a scenario result means something.
2. **Rename and plugin skeleton:** `gili-office`, `bin/`, `hooks/hooks.json` with the env gate, and the office `--settings` file.
3. **Gates:** A1, A2, A3, A6, A7, then A5 and A8. These are mostly the hook and `open-session.sh` flags, each with a stdin-fixture test.
4. **Safety nets:** D5, D1 with D3, D4, C3.
5. **Continuity:** C1 with C2, C4, D6.
6. **Evals depth:** B3, B4, B5, B6, B9, B10.
7. **Prompt changes, each with its scenario:** E1–E8.
8. **Owner decisions:** A4, D2, F1.
