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

**Seat**:
A position in the org chart with a role file, such as CTO or PM.

**Craft**:
A staff profile (`agents/*.md`), such as fullstack-engineer or designer.

**Person**:
A named member with one craft or seat, a level, a manager and a record.
_Avoid_: Agent, bot, AI

**Turn**:
One headless run of a person's conversation, started by the server.
_Avoid_: Session, run, prompt

**Office day**:
A day on which the CEO opened the office. Rituals count office days, never calendar weeks.

**Gate**:
An action only the CEO may take or approve.
