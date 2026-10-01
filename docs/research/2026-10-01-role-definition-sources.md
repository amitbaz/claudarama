# Sources for role definitions (research, 2026-10-01)

A research input for the role files of sub-project 5. It records what public agent catalogues and Anthropic's guidance offer, so the role files can borrow patterns without copying filler. It is an input, not a decision.

## What was read

- **Claude Code Templates** (aitmpl.com), repository `davila7/claude-code-templates`, agents under `cli-tool/components/agents/<category>/<name>.md`, read at commit `fea62b2`. 424 agent files, median 163 lines. MIT licence; one file (`development-team/ui-ux-designer.md`) is CC BY 4.0; many files are near-verbatim copies from the two collections below.
- **VoltAgent/awesome-claude-code-subagents** (MIT) and **wshobson/agents** (MIT): the upstream of much of the catalogue.
- **Anthropic's guidance**: the Claude Code subagents, best-practices and memory pages, the prompting best-practices pages, the agent-skills best-practices page and "Effective context engineering for AI agents".

Borrowing structure and ideas carries no obligation. Copying text verbatim means keeping the MIT notice, or the CC BY attribution for that one file. The role files borrow patterns, not text.

## Closest catalogue files per role

| Role | Closest files | What is worth taking |
|---|---|---|
| assistant | `ai-specialists/task-decomposition-expert`, `deep-research-team/query-clarifier`, `business-marketing/business-analyst` | Ask-or-proceed triage with a skip clause and at most three questions; a hand-off table of workstream, role and artifact; pause criteria. No file resembles a chief of staff. |
| pm | `data-ai/se-product-manager-advisor`, `development-team/sdd-spec-writer` | A ticket written as a contract (objective, context, acceptance criteria, verification commands); the test "can someone start without reading any unreferenced file?"; a sizing rule. No file names who does each ticket. |
| engineering-lead | `development-tools/code-reviewer`, `git/commit-guardian` | Run tooling first; findings as severity, file and line, risk, fix; an ordered check list ending in a single verdict line. No file re-derives evidence or checks a pull request against its ticket, and none writes a retro. |
| fullstack-engineer | `development-team/fullstack-developer` | Define the data model and the interface before either side; a "before marking complete" list. |
| frontend-engineer | `development-team/frontend-developer` | "Match the current toolchain before suggesting upgrades." |
| database-architect | `database/database-architect`, `database/supabase-schema-architect` | Find existing migrations and schemas first; every migration has a tested rollback; every access rule has a positive and a negative test. |
| designer | `development-team/ui-ux-designer` (CC BY 4.0), `expert-advisors/se-ux-ui-designer` | A fixed critique structure (verdict, critical issues, one big win); concrete artifact templates. |
| prompt-engineer | `ai-specialists/prompt-engineer` | Get the baseline and success criteria first; measure against a held-out set; report measured numbers only. |
| eval-engineer | `security/llm-redteam-specialist`, `ai-specialists/model-evaluator` | An evidence bundle (model, prompt hash, corpus hash, pass or fail per seed); calibrate a model judge before reporting its scores; thresholds before running. No file builds evaluations of behaviour. |
| researcher | `data-ai/task-researcher`, `development-tools/debugger` | Record only findings verified by a tool result; write only inside one directory; reproduce before diagnosing; rank two or three hypotheses; converge on one recommendation. |

## Patterns worth borrowing

1. One role sentence, with no inflated persona.
2. A paragraph on how the role differs from its neighbours.
3. A short numbered procedure, only where order matters.
4. Ask-or-proceed triage with a skip clause and a cap on questions.
5. Explicit pause-and-escalate criteria.
6. An output template with an exact structure, plus one good-versus-bad excerpt.
7. A fixed finding format and a single closing verdict line.
8. Rules against invented numbers; evidence attached to every claim.
9. A write-scope restriction for investigating roles.

## Patterns to leave out

- Routing text (`description`, "use proactively", example blocks) and `tools` or `model` frontmatter: they serve delegation, which role files do not use.
- Technology, version and capability lists, pinned stacks, and numeric thresholds with no project basis. They also break the project-agnostic rule; stack knowledge belongs in the pack overlay.
- A handshake with a "context-manager" agent, progress blocks, and lists of other agents to integrate with.
- Sample completion messages with made-up metrics.
- "You WILL / MUST / CRITICAL" phrasing, framework recitations and closing platitudes.

## What every catalogue file lacks

- The role's position in the loop: which step, what state the work arrives in, which gate follows.
- Its inputs: a charter, a ticket and a thread, with a rule for what to do when the ticket is unclear and nobody can answer in a headless turn.
- One named deliverable, where it goes and its required sections.
- The hand-off: who receives it and what they need to start.
- A definition of done and a stop condition.
- Boundaries with reasons, and independence for the verifying role.
- What to write when blocked, in place of a plausible-looking deliverable.

## What Anthropic's guidance adds

- Start minimal and add an instruction only for a failure that was observed. For each line ask whether removing it would cause a mistake; if not, cut it.
- Give the reason behind an instruction; the model generalises from the reason.
- Say what to do rather than what not to do, and be specific about the output's format.
- Dial back emphatic language; emphasis on many lines means none stands out.
- "Report only work you can point to evidence for" and "run a real check that exercises the change before reporting it done" are worth stating once for everyone.
- Instructions are context, not enforcement. Anything that must never happen also needs a mechanical gate.
- Length: the official subagent example body is about 25 lines; the guidance for always-loaded instruction files is under 200 lines. No page gives a limit for a role file, so 40 to 80 lines is an extrapolation.

Pages: `code.claude.com/docs/en/sub-agents`, `code.claude.com/docs/en/best-practices`, `code.claude.com/docs/en/memory`, `platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`, `platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices`, `anthropic.com/engineering/effective-context-engineering-for-ai-agents`.
