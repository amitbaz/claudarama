# Sub-project 5: Core loop

This spec details sub-project 5 of the blueprint. Decisions were settled with the owner on 2026-10-01, and extended later that day with trustworthy diagnosis, the mandate report and project knowledge (user stories 63 to 78). Terms follow `GLOSSARY.md`; the server's shape follows ADR-0003, and gated actions follow ADR-0002.

## Problem Statement

The CEO wants to install Claudarama on any project, describe a problem, and have the office carry it through diagnosis, planning, verified work and a lesson, stepping in only at the gates. Today that cannot happen on any project:

- There is no way to install it. The repository has no plugin, and the CLI runs only from its own checkout.
- The CEO must start a server by hand, and that server never runs a turn. Two projects on one machine share one database.
- The office has no people and no role files, so there is nobody to do the work and nothing telling them how.
- Nothing moves the loop forward. A grant wakes nobody, a YES at a gate only flips a flag, and a NO carries no reason back to the author.
- Turns have nowhere to work: no worktree, no branch, and three of them would share one checkout.
- The command that launches a turn is rejected by the real `claude`, and the permission wall around a turn has holes.
- An approved Lesson is a file path that nothing reads, so the office never gets better.
- The CEO learns that a gate is waiting only by opening the office again.

The case that matters most is when the CEO is lost: something in a large system is not working, and the CEO cannot tell whether the fault is in the code, the prompts, the bars or the tests themselves. Nothing in the office guards against the failure this invites. No one checks whether the measure can be believed, so specialists can spend a mandate's worth of turns fixing the wrong thing against a noisy test. No one challenges a Diagnosis before the CEO, who cannot judge it, is asked to approve it. A failing ticket can be retried without limit.

## Solution

The CEO installs Claudarama once, as a Claude Code plugin from a marketplace or as a terminal command, and runs `setup` in a project. The Assistant asks a few questions to write the charter and confirms the project's test commands. From then on the CEO opens the office, from inside Claude Code or from the terminal, and talks to the Assistant.

When the CEO describes a problem, the Assistant shapes it into a Mandate. Once the CEO grants it, the office runs by itself: a researcher writes a Diagnosis, the pm turns it into an Epic of tickets that each name the Role to do them, specialists work each ticket in its own worktree and open pull requests, the engineering-lead verifies each one, and the engineering-lead writes a Retro that proposes Lessons. The CEO answers four kinds of gate (Diagnosis, Epic, PR, Lesson) and is notified, on the desktop and on the phone, whenever one opens. Approved Lessons load into every later brief they apply to.

The office's findings are built to be trusted when the CEO cannot check them. A Diagnosis reports how much its measure varies when nothing changes and tests each rival explanation. A second specialist tries to refute it before the CEO sees it. A fix counts only if it beats the measure's spread, and a ticket that fails verification twice stops and goes back for re-diagnosis. After a mandate, a report shows where the office went wrong, by Role.

Every specialist exists from the first day. There is nothing to start, stop or configure beyond the pack, and offices for several projects run side by side.

## User Stories

Installing and setting up

1. As a CEO, I want to install Claudarama from a Claude Code marketplace, so that I can use it without leaving Claude Code.
2. As a CEO, I want to install Claudarama as a terminal command, so that I can use it without the plugin.
3. As a CEO, I want every action available from both the terminal and a Claude Code session, so that I use whichever I am already in.
4. As a CEO, I want `setup` to scaffold the pack in my project, so that the office has a place for its charter and settings.
5. As a CEO, I want the Assistant to ask me a few questions and write the charter, so that I do not start from an empty file.
6. As a CEO, I want the Assistant to propose the test commands it finds in my repository for me to confirm, so that specialists can run my checks from the first ticket.
7. As a CEO, I want the scaffolded pack to contain only settings the office actually reads, so that editing a setting always has an effect.
8. As a CEO, I want the README to give the install and first-run steps, so that I can set up a new project without reading the source.
9. As a CEO, I want a clear message when `gh` is missing or not signed in, so that I know what to fix before the office starts.

Opening and running the office

10. As a CEO, I want the office to start when I open it, with no server to start first, so that there is nothing to manage.
11. As a CEO, I want the office's database created the first time I open it, so that setup has no separate database step.
12. As a CEO, I want offices for two projects to run at the same time, so that I can try Claudarama on several projects.
13. As a CEO, I want each project to have its own office state even when two repositories share a directory name, so that their work never mixes.
14. As a CEO, I want the office to pause when I close my Session and resume where it stopped when I open it again, so that no work is lost.
15. As a CEO, I want a specialist interrupted by closing the Session to pick up from their worktree and working note, so that an interruption costs little.
16. As a CEO, I want a second Session on the same project to leave the running office alone, so that turns are never launched twice.
17. As a CEO, I want to see the office's status, so that I know what is running, queued and waiting on me.

The cast

18. As a CEO, I want all ten specialists present from the first day, so that I never hire or configure a roster.
19. As a CEO, I want every specialist shown by Role with their name beside it, so that I never have to remember who is who.
20. As a CEO, I want the office to refer to work by Role in every prompt, message, notification and GitHub comment, so that the output reads the same everywhere.
21. As a specialist, I want my brief to state my Role and name, so that I know who I am in the office.
22. As a specialist, I want a role file that says where I sit in the loop, what I produce, who receives it and what done means, so that I can do my step without being rescued.
23. As a specialist, I want one shared set of office rules in every brief, so that evidence, scope and how a turn ends are the same for everyone.
24. As a CEO, I want project-specific stack knowledge to come only from my pack's overlays, so that the core stays right for any project.

The loop

25. As a CEO, I want to describe a problem to the Assistant and have it shaped into a Mandate, so that I do not write tickets.
26. As a CEO, I want to see which Role will investigate before I grant a Mandate, so that a wrong choice is caught at the grant.
27. As a CEO, I want the investigation to start as soon as I grant the Mandate, so that nothing waits for a second instruction.
28. As a researcher, I want to submit my Diagnosis as a document on the ticket's branch, so that the CEO and later specialists read the same file.
29. As a CEO, I want my YES at the Diagnosis gate to merge the Diagnosis and wake the pm, so that planning starts without another step.
30. As a pm, I want to draft an Epic whose tickets each name the Role that will do them, so that the right specialist gets each one.
31. As a pm, I want the office to refuse a ticket naming a Role that does not exist, so that no ticket is stranded.
32. As a CEO, I want to see each ticket's Role at the Epic gate, so that I can correct routing before work starts.
33. As a CEO, I want my YES at the Epic gate to start every ticket with its named Role, so that work fans out without a dispatcher.
34. As a specialist, I want my own worktree and branch for each ticket, so that my work never collides with another ticket or with the CEO's checkout.
35. As a CEO, I want specialists never to switch branches in my own checkout, so that I can keep working in the project.
36. As an engineering-lead, I want to be woken when a pull request opens for a ticket, so that verification starts without anyone asking.
37. As a CEO, I want only the engineering-lead to be able to record a Ship-check, so that no author approves their own work.
38. As a specialist, I want a FAIL verdict to come back to me with the reason, so that I know what to fix.
39. As a CEO, I want a pull request merged only when I say YES and a SHIP verdict exists for its head commit, so that the PR gate stays mine.
40. As an engineering-lead, I want to be woken to write the Retro when a Mandate's tickets are all closed, so that the Learn step starts by itself.
41. As a CEO, I want any NO to ask me for a one-line reason and deliver it to the author, so that the redo addresses my objection.
42. As a CEO, I want DISCUSS to become a conversation in my Session that ends in YES or NO, so that I never have to quit to resolve a gate.
43. As a specialist, I want to post a question to the thread and stop when the ticket is unclear, so that I never produce a plausible-looking guess.
44. As a CEO, I want each Role to work one piece of work at a time, so that a specialist's work stays coherent.

Lessons

45. As an engineering-lead, I want a Retro to propose at most three short Lessons, each scoped to the company or one Role, so that the CEO can judge them in one answer.
46. As a CEO, I want my YES at the Lesson gate to merge the Retro and adopt its Lessons, so that one answer closes the Mandate.
47. As a specialist, I want adopted Lessons in my scope to appear in my brief, so that I work with what the office has learned.
48. As a CEO, I want to remove a Lesson by telling the Assistant, so that a bad Lesson stops shaping turns.
49. As a CEO, I want Diagnoses and Retros kept in fixed places in my repository, so that I can find and read them later.

Reaching the CEO

50. As a CEO, I want a desktop notification when a gate opens, so that I know the office is waiting.
51. As a CEO, I want a push on my phone when a gate opens while my Session is open and I am away, so that I can answer from wherever I am.
52. As a CEO, I want messages addressed to me shown together when I open the office, so that nothing sent to me is lost.
53. As a CEO, I want to list and answer open gates inside my Session, so that all decisions happen in one place.

Safety

54. As a CEO, I want a turn to run only commands on its allowlist, so that a specialist cannot run anything I did not permit.
55. As a CEO, I want the gate hook to block when it fails for any reason, so that an internal error never opens the wall.
56. As a CEO, I want the plugin's skills and hooks kept out of specialists' turns, so that installing the plugin does not widen what a turn can do.
57. As a CEO, I want gated actions to stay in my Session behind Claude Code's own permission prompt, so that ADR-0002 still holds from both doors.
58. As a CEO, I want a failed turn to show its error, so that a broken launch is not reported as an anonymous failure.

Proof

59. As a CEO, I want one real Mandate run end to end on a sandbox repository from a plugin session, so that I know the office works before I point it at a real project.
60. As a CEO, I want every one of the ten Roles to run at least once in that proof, so that no role file is untested.
61. As a maintainer, I want a free scenario that drives the whole loop with scripted turns, so that a change that breaks the loop fails in CI.
62. As a maintainer, I want role files checked against the template for free, so that a role file cannot silently lose a required part.

Trustworthy findings

63. As a CEO, I want to say that something is not working without knowing why and get a finding I can trust, so that I do not need to know where to begin.
64. As a CEO, I want a Diagnosis to report how much its measure varies when nothing changes, so that nobody chases noise.
65. As a CEO, I want a fix to count only if it beats that spread, so that a lucky run is never reported as an improvement.
66. As a CEO, I want the office to repair the measure first when it is too noisy to judge anything, so that turns are not spent fixing against it.
67. As a CEO, I want a Diagnosis to list the rival explanations at every level, each with what was run to check it, so that the office does not fix the first suspect it thought of.
68. As a CEO, I want a second specialist to try to refute a Diagnosis before I see it, so that I am not the only check on a finding I cannot judge.
69. As a CEO, I want the Challenge verdict and its reasons shown at the Diagnosis gate, so that I know whether the finding is contested.
70. As a challenger, I want to regenerate the evidence a Diagnosis rests on, so that my verdict does not depend on the author's claims.
71. As a CEO, I want a disputed Diagnosis returned to its author once before it reaches me, so that obvious gaps are closed without my time.
72. As a CEO, I want a ticket that fails verification twice to stop and go back for re-diagnosis, so that the office never burns turns on endless attempts.
73. As a CEO, I want the Assistant to ask me for a few judged cases when a mandate is about quality, so that the office knows what correct means to me.
74. As a CEO, I want a Ship-check to name any change a pull request makes to a bar, a threshold or a test's expectation, so that a pass is never bought by loosening the bar.

Understanding and improving the office

75. As a CEO, I want a report for each mandate showing each Role's turns, the reasons for every NO and FAIL, the questions asked and where each transcript is, so that I can find what to improve.
76. As a CEO, I want the Assistant to check at setup whether my project has its own agent instructions and offer to draft them, so that specialists start from the project's own knowledge.
77. As a CEO, I want the setup interview to ask for my project's unwritten rules, so that every brief carries what cannot be looked up.
78. As a CEO, I want to save my answer to a specialist's question as a Lesson, so that the same question is never asked twice.

## Implementation Decisions

### Distribution

- This repository is three things at once: the marketplace, the plugin and the CLI package. Every action is implemented once, in the CLI; each plugin skill calls the same code.
- The commands are `setup` (formerly `init`), `open` and `status`, reachable as `claudarama <command>` and `/claudarama:<command>`. `eval` stays a terminal-only development tool. `up` and `talk` are removed.
- Both doors require `uv` on the machine.
- Plugin skills are invocable by the user only, never chosen by the model. Plugin hooks do nothing outside the CEO's Session.

### The office server (ADR-0003)

- There is no daemon. Claude Code starts the office server as an MCP server process: one for the CEO's Session, declared by the plugin and passed by `claudarama open`, and one for each turn. All share the office's SQLite file.
- Each server process is handed the secret token that identifies its caller. A turn's token dies with the turn. Only the owner token may grant, answer a gate or remove a Lesson.
- The server belonging to the CEO's Session launches and monitors turns once the CEO opens the office, under a lock so that only one Session runs an office.
- The database is created on first open.
- An office is identified by its repository's main checkout and resolves the same from any subdirectory or worktree. Two repositories with the same directory name get separate offices. State stays outside the project, under the owner's home directory.
- Closing the Session pauses the office. At the next open, turns that were running are queued again.
- The per-office cap on simultaneous turns stays at its default of three; the machine-wide cap is kept through the shared slots file.

### Launching a turn

- The launch command is corrected so the real `claude` accepts it, and a failed launch records its error output.
- A turn runs in its ticket's worktree.
- Turns do not receive blanket Bash permission; the allowlist is the only source of permitted commands.
- The gate hook turns every internal error into a block, and is importable wherever the tool is installed.
- Turns keep the isolation settled in sub-project 4: the normal config directory with a strict server list and an explicit tool list. Bare mode is not used because it loses the subscription login.
- A Role runs one turn at a time.

### The cast and role files

- Ten Roles, each with exactly one Person, seeded when the database is created:

  | Role | Name |
  |---|---|
  | assistant | Nibbler |
  | pm | Hermes |
  | engineering-lead | Kif |
  | fullstack-engineer | Bender |
  | frontend-engineer | Fry |
  | database-architect | Scruffy |
  | designer | Zoidberg |
  | prompt-engineer | Cubert |
  | eval-engineer | Morbo |
  | researcher | Amy |

- A Person is addressed by Role. Wherever a Person is shown, the Role comes first with the name beside it, as in `designer (Zoidberg)`. A message to an unknown Role is refused.
- Each Role has a core role file of roughly 40 to 80 lines in seven fixed parts: what the Role is; where it sits in the loop and what state the work arrives in; the one document it produces and its required sections; who receives it and what they need to start; what "done" must be backed by; what it leaves to a neighbouring Role, with the reason; what to write when blocked or when the ticket is unclear.
- Rules common to everyone (evidence before claims, staying inside the ticket, how a turn ends, post a question and stop when blocked) are written once and loaded into every brief.
- The pack's profile for a Role is an overlay appended to the core role file. Stack knowledge appears only there.
- Role files borrow patterns from public catalogues, not text (`docs/research/2026-10-01-role-definition-sources.md`).
- The brief is built in this order: charter, shared office rules, the Person's Role and name, core role file, pack overlay, Lessons in scope, the thread, the ticket, the working note.
- The Assistant has a role file too, loaded into the CEO's Session from both doors. It covers shaping a Mandate, naming the investigator, the setup interview, presenting gates, notifying the CEO and removing Lessons.

### How the loop moves

The server queues the next turn itself on every transition.

| Event | Who is woken |
|---|---|
| Mandate granted | The investigating Role, on the investigation ticket |
| Diagnosis submitted | The challenging Role |
| Challenge DISPUTED, first time | The investigating Role, with the reasons |
| Diagnosis gate YES | The pm |
| Epic gate YES | Each ticket's named Role |
| A pull request opens for a ticket | The engineering-lead |
| Ship-check FAIL, first time | The ticket's Role, with the reason |
| Ship-check FAIL, second time on a ticket | The investigating Role, with both reasons; the mandate returns to INVESTIGATING |
| Every ticket of the Mandate closed | The engineering-lead, to write the Retro |
| Any gate NO | Whoever produced the work, with the CEO's reason |

- The Assistant creates the investigation ticket and names the investigating Role and the challenging Role when the Mandate is granted. The investigator defaults to researcher and the challenger to engineering-lead.
- Each drafted ticket in an Epic names a Role. The server refuses a Role with no role file.
- A NO at any gate takes a one-line reason, which is stored and delivered.
- The move to LEARNING happens while the office runs, not only when the CEO opens it.
- A Ship-check verdict is accepted only from the engineering-lead.
- `send` keeps its meaning for questions and blocked work. No turn has to fan work out.

### Trustworthy diagnosis

- A Diagnosis has required sections: the measure it relies on and how much that measure varies across repeated runs of the unchanged system; the rival explanations at every level (the code, the prompts, the bars, the tests, the overall approach, something missing) with what was run to check each; the CEO's judged cases when the Mandate has them; the recommended strategy. The server refuses a Diagnosis missing a section.
- A fix counts only if it beats the measure's spread. When the measure is too noisy to judge, repairing the measure comes first. This is a shared office rule, and the engineering-lead's SHIP verdict rests on repeated runs.
- A Ship-check names any change the pull request makes to a bar, a threshold or a test's expectation.
- A Mandate has a challenging Role, different from the investigating Role, named at the grant where the CEO sees it. The Assistant names the eval-engineer when the problem is judged by a test or eval of AI behaviour.
- Submitting a Diagnosis wakes the challenging Role. The Diagnosis gate opens only after a Challenge is recorded: STANDS or DISPUTED, with reasons and with what the challenger ran. The server refuses a Challenge from any other Role.
- A DISPUTED Diagnosis returns to the investigating Role once. The next submission is challenged again and reaches the CEO with its verdict either way. The gate shows the verdict beside the Diagnosis.
- A ticket's second FAIL queues no further turn for the ticket's Role. The Mandate returns to INVESTIGATING, the investigating Role is woken with both reasons, and the CEO is notified. Work resumes only after a revised Diagnosis passes the Diagnosis gate.
- When a Mandate is about quality, the Assistant asks the CEO for a few judged cases (this is right, this is wrong, and why) and stores them with the Mandate.

### The mandate report

- `status` for a Mandate lists each Role that worked on it with its turns and usage, every NO and FAIL with its reason, every question or BLOCKED message, and where each turn's transcript is. It is a view over what the office already stores.

### Project knowledge

- Turns run inside the project, so they read its own agent instructions. At setup the Assistant checks whether such a file exists and offers to draft one.
- The setup interview asks for the project's unwritten rules and writes them into a house-rules section of the charter, which every brief loads.
- A pack overlay holds only a rule that applies to one Role. Overlays are not generated from a scan of the repository.
- When the CEO answers a specialist's question about the project, the Assistant offers to save the answer as a Lesson, which the CEO adopts directly within the same length limit.

### Worktrees and documents

- Each ticket gets one worktree and one branch, created by the server outside the main checkout and removed once the ticket's pull request is merged or closed.
- A Diagnosis lives in `.claudarama/company/diagnoses/<mandate>.md` and a Retro in `.claudarama/company/retros/<mandate>.md`. The server refuses a submitted path outside these.
- The author commits the document on the ticket's branch and opens a pull request. The CEO's YES at the Diagnosis gate or Lesson gate merges it; no Ship-check is required, because the CEO reads the document at that gate. The PR gate does not show document pull requests.
- The Diagnosis pull request closes the investigation ticket.

### Lessons

- A Lesson is a row in the office database: text of at most 300 characters, a scope (the company or one Role), a status and the Mandate it came from.
- A Retro is submitted together with at most three proposed Lessons. The Lesson gate shows the Retro and its Lessons and takes one answer.
- YES merges the Retro and adopts the Lessons. NO returns the Mandate to LEARNING with the CEO's reason.
- Every brief loads the adopted Lessons scoped to the company and to that Person's Role.
- The CEO removes a Lesson through the Assistant; only the owner token may do so.

### Reaching the CEO

- Opening a gate calls a notification sink. In the office this sends a macOS notification.
- While the Session is open, a background watcher wakes the Assistant when a gate opens, and the Assistant sends Claude Code's own push notification, which reaches the phone when Remote Control is connected.
- Messages addressed to the CEO are shown as a batch at open.
- Owner-only tools list open gates and answer them, so every gate, including DISCUSS, is resolved inside the Session.

### Setup

- `setup` scaffolds the pack with only the keys the code reads, and with `company/diagnoses` and `company/retros` as the only company directories.
- At the first open, when the charter is still a placeholder, the Assistant interviews the CEO for it and proposes the test commands found in the repository for confirmation.

### Schema changes

- People keep an identifier, a name and a Role. Level and manager are removed, along with the unused merge check that read them.
- Tickets gain the Role that will do them.
- Mandates gain the investigating Role, the challenging Role, the CEO's judged cases and the reason from the last NO. The stored lesson path becomes the Retro's path.
- A Challenge is stored with its verdict, its reasons, what was run and who recorded it.
- A FAIL verdict stores its reason, and FAILs are counted per ticket.
- A new table holds Lessons.

### Documentation

The blueprint, `ARCHITECTURE.md`, `COMPANY.md`, `PACK_SCHEMA.md`, `SCENARIOS.md` and the README are brought in line with this spec and ADR-0003.

## Testing Decisions

A good test here drives the office from the outside and asserts what the CEO or a specialist would observe: who was woken, what a brief contains, what was merged, what was refused. It does not assert internal function calls.

1. **The loop scenario (primary).** A whole office runs in a temporary git repository with the real server, turn runner, brief builder, database and worktrees. Three edges are replaced through hooks the code already has: a scripted `claude` standing in for each turn, which calls the office's tools through the real server it is handed; a fake `gh`; scripted CEO answers at the gates. One new edge is added: a notification sink. The existing multi-step scenario runner is made real for this: today its turn is refused before it starts and its CEO step never touches a gate. This seam asserts routing at every transition, the ticket's Role, a NO carrying its reason, the Ship-check restricted to the engineering-lead, documents merged at their gates, Lessons appearing in the next brief, pause and resume when the Session closes, and two offices side by side. It also asserts that no Diagnosis gate opens before a Challenge, that a Challenge from the wrong Role is refused, that a DISPUTED Diagnosis returns once, that a second FAIL stops the ticket and wakes the investigating Role, and that the mandate report shows each NO and FAIL reason against the right Role.
2. **The gate hook fed recorded input.** Prior art: the existing hook tests. Adds: an internal error blocks; a command outside the allowlist is denied without blanket Bash.
3. **Free static checks.** Prior art: the scenario validator. Each role file fits the seven-part template and length; the plugin manifest and its skills resolve; every key `setup` scaffolds is one the code reads.
4. **The real run (manual, paid, never in CI).** One real Mandate on a new private repository, `claudarama-sandbox`, holding a minimal web app with one page, one table, one prompt and one eval, run from a plugin session with the CEO answering only the gates. Its Epic holds a ticket for every craft, so all ten Roles run at least once. After each step the transcript is read and the role file corrected where the Role went wrong; a line stays only if removing it changes what the Role does. The sandbox's eval is noisy by design, so the run must show the Diagnosis reporting the spread, a Challenge recorded before the Diagnosis gate, and a ticket stopped after its second FAIL. A follow-up Mandate shows the Lesson in a brief. A smoke run passes through the terminal door.

The existing per-function tests stay. New behaviour is tested at seam 1.

## Out of Scope

- **Removed outright:** hiring, `retire`, departments, locked future departments, `claudarama up`, direct talk with a Role.
- **Deferred to sub-project 6 (Company rhythm), each to be re-decided:** levels, reviews, 1:1s, the per-person record, managers, key results and cycles, all-hands, a Mandate proposed from inside the office.
- **Not started:** an investigation carried out by several specialists at once, each testing their own suspect; ideas, objections, incidents, engineering team splits, persona commit authors on GitHub, an automated real-model test runner, a messaging-service push, running two specialists of one Role in parallel, per-scope Lesson caps and automatic retirement, a server that keeps working with no Session open.
- Spend caps stay with the Budget sub-project.

## Further Notes

### To verify during the build

Each has a fallback.

- Starting the plugin's Python server through `uv`. Fallback: a launcher script in the plugin's `bin`.
- A background watcher waking an idle Session reliably enough to send the phone push. Fallback: a messaging service called from the office, which is otherwise out of scope.
- The working directory Claude Code gives a plugin's server. The project directory variable is passed explicitly either way.

### Known breaks this spec closes

Traced on 2026-10-01 against the code as of commit `99f4aba`:

1. The server never runs turns, and the turn runner has no loop.
2. The real `claude` rejects the launch command, and the error output is discarded.
3. Nothing creates people, and a turn for an unknown person is silently never scheduled.
4. The project name resolves to an empty string or `..` in a normal clone.
5. No role content; the Assistant gets no prompt.
6. No way to discover who exists; `send` needs a raw identifier.
7. Nothing follows a grant.
8. Gate answers only flip flags; a NO carries no reason; LEARNING wakes no one.
9. A turn can send once, and tickets have no assignee, so an Epic cannot fan out.
10. Turns have no working directory, worktree or branch.
11. No channel from the office to the CEO, and DISCUSS cannot be resolved in the Session.
12. The gate hook can fail open, and blanket Bash removes the native wall.
13. One setting is read from the state directory instead of the pack, and the scaffold writes keys nothing reads.
14. Only the pack's listed commands are allowed, and the scaffold assumes one test tool.
15. GitHub prerequisites are undocumented.
16. A missing `gh` kills the sync thread.
17. Any caller's SHIP verdict passes the PR gate.
18. Lessons never reach a brief, and the milestone is never closed.
19. One office per port.
20. No recovery for turns left running; an escalated turn has its model overwritten.
21. No install documentation and no plugin manifest.

### Plugin facts relied on

- One repository may be both a marketplace and a plugin.
- A plugin's `bin` is on the path inside a session.
- An installed plugin also loads into headless runs, which is why its skills are user-invocable only and its hooks inert outside the CEO's Session.
- A hook that exits with a code other than 0 or 2 does not block.
- A plugin with a `bin` directory cannot be installed through claude.ai or Cowork; this matters only for distribution through organization settings.

### Cost of the proof

The real run uses subscription usage: roughly one to two Mandates' worth of turns across all ten Roles, plus reruns of the steps whose role files are corrected.
