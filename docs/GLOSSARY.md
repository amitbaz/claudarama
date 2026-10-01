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
A named member with one role, a level, a manager and a record.
_Avoid_: Agent, bot, AI

**Turn**:
One headless run the server starts for one person on one piece of work. Continuity comes from the brief, the person's record and the ticket's working note.
_Avoid_: Run, prompt

**Session**:
An interactive conversation the CEO opens with a person (`open` for the Assistant, `talk` for anyone else), seeded with the same brief a turn would get. A person never has a turn and a session at the same time.

**Thread**:
The messages about one ticket, or about one topic when there is no ticket. A turn's brief loads only the thread that woke it.

**Working note**:
A short note (at most 500 characters) a person leaves at the end of a turn: the files involved, what they found, the next step. The next turn on that ticket loads it.

**Mandate**:
A body of work toward a key result, which breaks into epics and tickets. Proposed by a head; the office works on it only once the CEO grants it.

**Grant**:
The CEO's approval of one mandate. Only turns for tickets under a granted mandate (replies included), rituals and the Assistant may start; other work needs a ticket first.

**Office day**:
A day on which the CEO opened the office. Rituals count office days, never calendar weeks.

**Gate**:
An action only the CEO may take or approve.

**Diagnosis**:
The investigators' written finding on a granted mandate. Submitting it moves the mandate from INVESTIGATING to PLANNING and pauses it at the Diagnosis gate.

**Diagnosis gate**:
A Gate where the CEO answers YES, NO or DISCUSS on a Diagnosis. YES unblocks the mandate to plan, staying PLANNING; NO returns it to INVESTIGATING; DISCUSS leaves it paused. While paused (`blocked_on_ceo`) the scheduler starts no turns for its tickets.

**Epic**:
The drafted tickets of a PLANNING mandate, tied to it in the database; there is no epics table. Submitting it moves the mandate from PLANNING to EXECUTING and pauses it at the Epic gate.

**Epic gate**:
A Gate where the CEO answers YES, NO or DISCUSS on an Epic, shown with its tickets. YES unblocks the mandate so its tickets can start; NO discards the drafted tickets and returns it to PLANNING; DISCUSS leaves it paused. While paused (`blocked_on_ceo`) the scheduler starts no turns for its tickets.

**Gate hook**:
The PreToolUse hook that checks every tool call of a turn against the turn's allowlist and denies what is not on it. It enforces the allowlist; it is not itself a Gate.
