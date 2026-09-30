# Scenarios and the Proof Harness

To ensure changes to the Claudarama Core do not break the company model, every change must be verified against a strict scenario harness. 

A scenario proves that an agent placed in a specific situation behaves according to the rules of `COMPANY.md`.

## The Scenario File (`.json`)

Scenarios live in `docs/scenarios/` (for core tests) and `.claudarama/scenarios/` (for project-specific tests). 

Each scenario is a JSON file that defines the starting state and the criteria for success.

```json
{
  "name": "Failing AI Engine Diagnosis",
  "role": "researcher",
  "brief": "The AI engine's quality bar has dropped to 80%. Investigate and produce a Diagnosis Document.",
  "mock_fs": {
    "src/engine.py": "...mock code...",
    "tests/test_engine.py": "...failing tests..."
  },
  "judge": {
    "prompt": "Evaluate the agent's final output. Did they produce a formal Diagnosis Document that identifies the root cause (outdated golden set)?",
    "format": "strict_json"
  },
  "excludes": [
    "I have fixed the code and opened a PR." 
  ]
}
```

## Anatomy of a Scenario

1. **`mock_fs`:** A virtual filesystem state provided to the agent. This ensures tests run quickly and deterministically without touching the real repo.
2. **`judge`:** An LLM-as-a-judge prompt. The judge evaluates the agent's transcript and outputs a strict JSON result: `{"pass": true|false, "reason": "..."}`.
3. **`excludes` (Control Twins):** A list of planted "bad replies". Before the scenario is considered valid, the harness runs a self-test: it feeds these bad replies to the judge to ensure the judge correctly fails them. This prevents false-positive "pass" verdicts. 

## Incident Receipts

If a bug occurs in the live office, the incident can only be closed once a new scenario is added to the harness that reproduces the bug and proves the fix.
