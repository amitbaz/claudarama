# Claudarama Core

The claudarama plugin core.

## Language

**Office**:
One company, for one project. Comprises the Claudarama core plus one project pack.
_Avoid_: Workspace, instance

**Core**:
The `claudarama` plugin. Identical for every project.

**Pack**:
The project's `.claudarama/` directory, which adapts the core to that project.
_Avoid_: Config

**Role**:
The Seat or Craft a Person holds. Names the role file their brief loads.

**Seat**:
A kind of role: a position in the org chart, such as CTO or PM.

**Craft**:
A kind of role: a staff profile (`agents/*.md`), such as fullstack-engineer or designer.

**Person**:
A named member holding one Role. Every Role has exactly one Person, present from the office's first day.
_Avoid_: Agent, bot, AI

**Turn**:
One headless run the server starts for one person on one piece of work. Continuity comes from the brief and the ticket's working note.
_Avoid_: Run, prompt

**Session**:
The CEO's interactive conversation with the Assistant, opened from the terminal or from inside Claude Code. The office works only while a Session is open; closing it pauses the office.

**Thread**:
The messages about one ticket, or about one topic when there is no ticket. A turn's brief loads only the thread that woke it.

**Working note**:
A short note (at most 500 characters) a person leaves at the end of a turn: the files involved, what they found, the next step. The next turn on that ticket loads it.

**Mandate**:
A body of work the office takes on for the CEO, which breaks into an Epic of tickets. The office works on it only once the CEO grants it.

**Grant**:
The CEO's approval of one mandate, naming its investigation ticket, its investigating Role (researcher unless another is named), who is woken on that ticket, and its challenging Role (engineering-lead unless another is named, and never the investigating Role), and carrying the CEO's judged cases when the mandate has them. Only turns for tickets under a granted mandate (replies included), rituals and the Assistant may start; other work needs a ticket first.

**Office day**:
A day on which the CEO opened the office. Rituals count office days, never calendar weeks.

**Gate**:
An action only the CEO may take or approve. A NO at any Gate takes a one-line reason, which joins the ticket's thread and wakes whoever produced the work.

**Diagnosis**:
The investigating Role's written finding on a granted mandate: the measure it relies on and how much that measure varies, the rival explanations and what was run to check each, the CEO's judged cases when the mandate has them, and the recommended strategy. It is a file in the pack's `company/diagnoses/` directory, committed on the investigation ticket's branch with a Pull Request from that branch; the office refuses one at any other path, one not committed there, and one that lacks a section. Submitting it wakes the challenging Role and leaves the mandate INVESTIGATING; it reaches the Diagnosis gate, and the mandate moves to PLANNING, only after a Challenge.

**Challenge**:
A second Role's attempt to refute a Diagnosis before the CEO sees it, recorded with `record_challenge` as STANDS or DISPUTED with reasons and with what was run, and accepted only from the mandate's challenging Role. The challenger regenerates the evidence rather than trusting the author's. A mandate's first DISPUTED returns the Diagnosis to its author with the reasons; every later Challenge opens the Diagnosis gate with its verdict either way.
_Avoid_: Review, critique

**Diagnosis gate**:
A Gate where the CEO answers YES, NO or DISCUSS on a Diagnosis, shown with its Challenge. YES merges the Diagnosis's Pull Request with no Ship-check, closes the investigation ticket, unblocks the mandate to plan, staying PLANNING, and wakes the pm; NO returns it to INVESTIGATING; DISCUSS leaves it paused. While paused (`blocked_on_ceo`) the scheduler starts no turns for its tickets.

**Epic**:
A set of drafted tickets for a PLANNING mandate, each naming the Role that will do it, tied to it in the database and marked `drafted` until the CEO approves; there is no epics table. A ticket naming a Role with no role file is refused, and tickets that already exist cannot be drafted. Submitting it moves the mandate from PLANNING to EXECUTING and pauses it at the Epic gate.

**Epic gate**:
A Gate where the CEO answers YES, NO or DISCUSS on an Epic, shown with its tickets and each ticket's Role. YES unblocks the mandate and wakes each ticket's Role; NO discards the drafted tickets and returns it to PLANNING; DISCUSS leaves it paused. While paused (`blocked_on_ceo`) the scheduler starts no turns for its tickets.

**Ship-check**:
The Engineering Lead's independent verification of a Pull Request, logged with `record_ship_check` as a SHIP or FAIL verdict on the PR's head commit, together with the path of a submitted Diagnosis and the command that was run. The Engineering Lead is woken for it when a Pull Request opens for a ticket or takes a new push. The PR gate requires a SHIP verdict for the head commit. A FAIL carries a one-line reason, which joins the ticket's thread and wakes the ticket's Role. A ticket's second FAIL stops the ticket: no turn is queued for its Role, the mandate returns to INVESTIGATING, the investigating Role is woken with both reasons, and the CEO is notified. Work on the mandate's other tickets waits until a revised Diagnosis passes the Diagnosis gate.

**PR gate**:
A Gate where the CEO answers YES, NO or DISCUSS on an open Pull Request that closes an office ticket. The Pull Request of a Diagnosis or a Retro is not shown here: its own Gate merges it. YES merges it, but only when a SHIP verdict is recorded for its head commit; otherwise the merge is refused. NO closes the PR; DISCUSS leaves it. When every ticket of an EXECUTING mandate is closed on GitHub, the mandate moves to LEARNING while the office runs, and the Engineering Lead is woken to write the Retro.

**Retro**:
The written look back on a LEARNING mandate, which proposes Lessons. It is a file in the pack's `company/retros/` directory, committed on the investigation ticket's branch with a Pull Request from that branch; the office refuses one at any other path. Submitting it moves the mandate to CLOSED and pauses it at the Lesson gate.

**Lesson**:
One short rule a Retro proposes, scoped to the whole company or to one Role. Once the CEO approves it at the Lesson gate, every brief in its scope loads it.

**Lesson gate**:
A Gate where the CEO answers YES, NO or DISCUSS on the Lessons a Retro proposes. YES merges the Retro's Pull Request with no Ship-check, adopts its Lessons and unblocks the mandate, finally CLOSED; NO returns it to LEARNING; DISCUSS leaves it paused (`blocked_on_ceo`).

**Gate hook**:
The PreToolUse hook that checks every tool call of a turn against the turn's allowlist and denies what is not on it. It enforces the allowlist; it is not itself a Gate.
