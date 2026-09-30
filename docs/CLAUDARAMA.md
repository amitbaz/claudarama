# Claudarama: The System & Vision

This document defines what the Claudarama plugin is and what it aims to achieve. It is the technical companion to `COMPANY.md` (which defines how the resulting organization behaves).

## 1. The Vision

Claudarama is a Claude Code plugin designed to run an autonomous AI startup around a software project. 

The goal is to move beyond AI as a pure "coding assistant" that requires the human to prescribe every task. Instead, Claudarama provides a complete, structured organization where the human acts as the CEO, and the AI assumes specialized roles (PM, Researcher, Lead, Engineer) to investigate, plan, build, verify, and learn.

## 2. The Proof Scenario

Any changes to the Core must be proven to work via strict scenario harnesses. 

The primary scenario that proves the viability of this model is the **Failing AI Engine**:
1.  **Setup:** A dummy project pack containing a mock AI engine and a failing test suite.
2.  **Trigger:** The CEO tells the Assistant: "The AI engine is failing its quality bars, I don't know why. Get it fixed."
3.  **Validation:** The core office must sequentially produce a Diagnosis Document, an Epic, a verified Pull Request via `ship-check`, and a proposed Lesson, pausing for the CEO's approval at each gate. 
