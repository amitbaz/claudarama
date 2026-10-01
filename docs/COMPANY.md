# The Company Operating Model

This document defines the fundamental operating model of a Claudarama office. It describes how an autonomous AI software company behaves, how work flows through it, and where the human CEO exercises control.

## 1. The Core Philosophy

To act like a real software company, the office does not merely accept tasks and implement them blindly. A real company understands its goals, investigates problems with evidence, plans its work, verifies its output independently, and learns from its mistakes. 

The CEO sets the direction, defines the goals, and approves major decisions at strict gates. The team handles the execution within those boundaries.

## 2. The Operating Lifecycle

Work flows through a five-step loop. A Mandate moves through the states INVESTIGATING, PLANNING, EXECUTING, LEARNING and CLOSED, and pauses at each Gate until the CEO answers YES, NO or DISCUSS. The office notifies the CEO when a Gate opens.

### 1. Trigger (Mandate)
Work begins when the CEO tells the Assistant about a problem in a Session.
*   The Assistant shapes it into a **Mandate**, opens its investigation ticket and names two Roles: the investigating Role, the researcher unless another fits better, and a different challenging Role, the engineering-lead unless another fits better. When the Mandate is about quality, the Assistant asks the CEO for judged cases and stores them with the Mandate at the grant.
*   **Gate:** The CEO grants the Mandate. The grant wakes the investigating Role on the investigation ticket.

### 2. Investigate (Diagnosis)
Before touching code, the team must understand the cause.
*   The investigating Role gathers evidence and submits a **Diagnosis**: the measure it relies on, the rival explanations and what was run to check each, and a recommended strategy.
*   A Diagnosis is a file in the pack's `company/diagnoses/` directory. Its author commits it on the investigation ticket's branch and opens a Pull Request from that branch. The office refuses a Diagnosis at any other path, one that is not committed there, one with no open Pull Request, and one that lacks a required section: the measure and its spread, the rival explanations with what was run to check each, the CEO's judged cases when the Mandate has them, and the recommended strategy.
*   Submitting it wakes the challenging Role, which tries to refute it by regenerating the evidence and records a **Challenge**: STANDS or DISPUTED, with reasons and with what was run. A Mandate's first DISPUTED returns the Diagnosis to the investigating Role with the reasons; the next submission reaches the CEO with its verdict either way.
*   **Gate:** The CEO answers at the Diagnosis gate, which opens only once a Challenge is recorded and shows it beside the Diagnosis. YES merges the Diagnosis's Pull Request, closes the investigation ticket and wakes the pm. NO returns the Mandate to INVESTIGATING and wakes the investigating Role with the CEO's reason.

### 3. Plan (Epic)
The approved strategy is cut into work.
*   The pm drafts an **Epic**: a set of tickets, each naming the one Role that will do it. The office refuses a ticket that names a Role with no role file.
*   **Gate:** The CEO answers at the Epic gate, which shows each ticket with its Role. YES wakes each ticket's Role. NO discards the drafted tickets and wakes the pm with the CEO's reason.

### 4. Execute and verify (Ship-check)
Each ticket's Role does the work, and nobody approves their own.
*   The ticket's Role works on the ticket's own branch and opens a Pull Request that closes the ticket.
*   The opened Pull Request wakes the engineering-lead, who runs a **Ship-check**: an independent verification that regenerates the evidence, recorded as SHIP or FAIL on the Pull Request's head commit. The office accepts a verdict only from the engineering-lead. A new push to the Pull Request wakes the engineering-lead again.
*   A FAIL carries a one-line reason and wakes the ticket's Role with it.
*   A ticket's second FAIL stops the ticket. No further turn is queued for its Role. The Mandate returns to INVESTIGATING, the investigating Role is woken with both reasons, and the CEO is notified. While the Mandate is INVESTIGATING only its investigation ticket is worked on; work on its other tickets resumes once a revised Diagnosis passes the Diagnosis gate, and the pm plans what remains in a new Epic.
*   **Gate:** The CEO answers at the PR gate. YES merges the Pull Request, but only with a SHIP verdict on its head commit. NO closes it and wakes the ticket's Role with the CEO's reason.
*   The Pull Request of a Diagnosis or a Retro is not shown at the PR gate and gets no Ship-check: the CEO reads the document at the Diagnosis gate or the Lesson gate, and the YES there merges it.

### 5. Learn (Retro)
The company raises its own baseline over time.
*   When every ticket of the Mandate is closed, the Mandate moves to LEARNING while the office runs, and the engineering-lead is woken to write the **Retro**, which proposes **Lessons**.
*   A Retro is a file in the pack's `company/retros/` directory, committed on the investigation ticket's branch with a Pull Request from that branch. The office refuses a Retro at any other path.
*   **Gate:** The CEO answers at the Lesson gate. YES merges the Retro's Pull Request and closes the Mandate. NO returns it to LEARNING and wakes the engineering-lead with the CEO's reason.
*   **Lessons:** A Retro proposes at most three, each a rule of at most 300 characters scoped to the company or to one Role. The gate shows the Retro and its Lessons, and the CEO's YES adopts them. From then on every brief loads the adopted Lessons scoped to the company and to its Role. Through the Assistant the CEO can also adopt a Lesson directly, such as an answer to a specialist's question about the project, and remove one.

### How the loop moves

The office queues the next turn itself at every transition, so no turn has to hand work on. A Role still uses `send` to ask a question or to report blocked work.

| Event | Who is woken |
|---|---|
| Mandate granted | The investigating Role, on the investigation ticket |
| Diagnosis submitted | The challenging Role |
| Challenge DISPUTED, first on a Mandate | The investigating Role, with the reasons |
| Diagnosis gate YES | The pm |
| Epic gate YES | Each ticket's Role |
| A Pull Request opens for a ticket, or takes a new push | The engineering-lead |
| Ship-check FAIL, first on a ticket | The ticket's Role, with the reason |
| Ship-check FAIL, second on a ticket | The investigating Role, with both reasons; the Mandate returns to INVESTIGATING and the CEO is notified |
| Every ticket of the Mandate closed | The engineering-lead, to write the Retro |
| Any Gate NO | Whoever produced the work, with the CEO's reason |

The office looks at GitHub for opened Pull Requests and closed tickets each time a turn ends, and once a minute for changes made outside a turn.

## 3. Roles and Responsibilities

The office has a fixed cast: one Person for each Role.

*   **CEO (Human):** Sets the charter, grants Mandates and answers at every Gate.
*   **assistant:** The CEO's interface to the company in a Session. Shapes a vague request into a Mandate.
*   **researcher** (or another investigating Role, such as the **eval-engineer**): Finds the cause and writes the Diagnosis.
*   **pm:** Cuts an approved Diagnosis into an Epic and names each ticket's Role.
*   **fullstack-engineer, frontend-engineer, database-architect, designer, prompt-engineer, eval-engineer:** Each does the tickets that name it and opens their Pull Requests.
*   **engineering-lead:** Runs the Ship-check on each Pull Request and writes the Retro.
