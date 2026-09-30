# The Company Operating Model

This document defines the fundamental operating model of a Claudarama office. It describes how an autonomous AI software company behaves, how work flows through it, and where the human CEO exercises control.

## 1. The Core Philosophy

To act like a real software company, the office does not merely accept tasks and implement them blindly. A real company understands its goals, investigates problems with evidence, plans its work, verifies its output independently, and learns from its mistakes. 

The CEO sets the direction, defines the goals, and approves major decisions at strict gates. The team handles the execution within those boundaries.

## 2. The Operating Lifecycle

Work in the company flows through a five-step lifecycle. This ensures that vague problems are transformed into verified solutions without the CEO having to prescribe every ticket.

### 1. Trigger (Identify)
Work begins when a gap is identified between the current state and the company's goals.
*   **Bottom-up:** A PM or Head of department notices a Key Result (KR) is failing (e.g., "The AI engine's 95% pass rate has dropped to 80%") and proposes an investigation.
*   **Top-down:** The CEO reports a vague problem to the Assistant during an interactive session (e.g., "The AI engine is failing, get it fixed"). The Assistant synthesizes this into an investigation mandate.

### 2. Investigate (Diagnosis)
Before touching code, the team must understand the root cause.
*   A specialist (e.g., Researcher or Eval Engineer) is assigned to gather evidence.
*   They produce a formal **Diagnosis Document** (e.g., an ADR or Research Brief) that outlines the evidence (e.g., "The golden set is outdated") and proposes a strategy.
*   **Gate:** The CEO must approve the Diagnosis Document before planning begins.

### 3. Plan (Epic)
The approved strategy must be translated into actionable engineering work.
*   The Product Manager (PM) takes the approved Diagnosis and drafts an **Implementation Plan / Epic**.
*   This Epic breaks the strategy down into specific, scoped tickets (e.g., "Rewrite 50 golden set items").
*   **Gate:** The CEO must approve the Epic. This ensures the execution plan matches the approved diagnosis.

### 4. Execute & Verify (`ship-check`)
Engineers write the code, but they do not merge their own work blindly.
*   Engineers execute the tickets in the Epic.
*   Before the CEO is asked to merge a Pull Request, an Engineering Lead (or Eval Engineer) runs a **`ship-check`**.
*   The `ship-check` is an independent verification step where the Lead runs fresh evidence (e.g., running the evals locally) to prove the fix satisfies the baseline established in the diagnosis.
*   **Gate:** The CEO merges the verified Pull Request.

### 5. Learn (Retro)
The company must increase its baseline competence over time.
*   Once the work is merged, the team holds a Retrospective.
*   They identify why the problem occurred and propose a concrete **Lesson** (e.g., "Always update the golden set when changing a prompt schema").
*   **Gate:** The CEO approves the Lesson. It is then injected into the server's working memory, automatically guiding all future turns in that product area.

## 3. Roles and Responsibilities

The company relies on specific seats and crafts to execute the lifecycle:

*   **CEO (Human):** Sets the charter, grants mandates, approves diagnoses and plans, and merges verified code.
*   **Assistant:** The CEO's interface to the company. Synthesizes vague requests into structured work.
*   **Product Manager (PM):** Monitors Key Results, writes Epics, and scopes tickets.
*   **Head of Research / Eval Engineer:** Investigates root causes, gathers evidence, and writes Diagnosis Documents.
*   **Engineering Lead:** Performs `ship-check` verifications on completed tickets before they reach the CEO.
*   **Engineer (Fullstack, Frontend, etc.):** Executes individual tickets and opens Pull Requests.
