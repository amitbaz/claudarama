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
One headless conversation the server starts for one person and one piece of work. Never resumed; continuity comes from the brief and the record.
_Avoid_: Run, prompt

**Session**:
An interactive conversation the CEO opens with a person (`open` for the Assistant, `talk` for anyone else), seeded with the same brief a turn would get. A person never has a turn and a session at the same time.

**Thread**:
The messages about one ticket, or about one topic when there is no ticket. A turn's brief loads only the thread that woke it.

**Mandate**:
A body of work toward a key result, which breaks into epics and tickets. Proposed by a head; the office works on it only once the CEO grants it.

**Grant**:
The CEO's approval of one mandate. Only turns for tickets under a granted mandate (replies included), rituals and the Assistant may start; other work needs a ticket first.

**Office day**:
A day on which the CEO opened the office. Rituals count office days, never calendar weeks.

**Gate**:
An action only the CEO may take or approve.
