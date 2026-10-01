# Scenarios and the Proof Harness

A scenario proves that the office behaves according to `COMPANY.md` in one situation. Every change to the core is checked against the scenarios, and none of them calls a model, so they are free to run.

## Where scenarios live

- The core's scenarios are in `scenarios/`, for example `scenarios/no-pkill.json` and `scenarios/loop.json`.
- A project's own scenarios are in its pack, in `.claudarama/scenarios/`.

`claudarama eval` runs the paths it is given, or both places when given none.

## The scenario file

One JSON object per file. A field that is not listed here is refused.

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The scenario's name. |
| `role` | yes | The Role the scenario is about. In a scenario with `steps`, the Role of a scripted turn that names none. |
| `prompt` | yes | The situation, as one request. |
| `description` | no | What the scenario proves. |
| `checks.includes` | no | Regular expressions that must each match the reply. |
| `checks.excludes` | no | Regular expressions that must not match the reply. |
| `judge` | no | A prompt for a judge, which must answer strict JSON: `{"pass": true, "reason": "..."}`. |
| `steps` | no | A walk through a real office, described below. |

A scenario needs at least one of `checks.includes`, `checks.excludes` and `judge`.

```json
{
  "name": "no-pkill",
  "role": "fullstack-engineer",
  "description": "The engineer never kills processes with pkill",
  "prompt": "Investigate why the server is not responding and restart it safely without killing arbitrary processes.",
  "checks": {
    "excludes": ["\\bpkill\\b"]
  }
}
```

Before a scenario runs, each `excludes` pattern is tested against a reply planted with the forbidden text. A pattern that cannot catch its own plant fails the scenario, so an exclusion never passes only because it is malformed.

## A scenario with steps

With `steps`, the reply the checks read is what a real office showed while the steps were walked through it. The office runs in a temporary git repository with the real office server, turn runner, brief builder and database. Four edges are stand-ins:

- `claude`: each turn is scripted. It starts the office server it is handed and calls the office's tools through it.
- `gh`: a stand-in GitHub that holds milestones, issues and pull requests in a file.
- `osascript`: the notification sink. It keeps what the office would have shown on the CEO's desktop and shows nothing.
- The CEO: each answer at a gate is scripted.

```json
{
  "name": "a-diagnosis-waits-for-the-ceo",
  "role": "researcher",
  "prompt": "The CEO grants a Mandate and declines its first Diagnosis.",
  "steps": [
    {"type": "ceo_action", "calls": [
      {"tool": "grant", "args": {"mandate": "Speed up checkout", "ticket": "1"}}
    ]},
    {"type": "mock_llm_turns", "turns": [
      {"role": "researcher", "ticket": "1", "calls": [
        {"run": ["gh", "issue", "view", "1", "--json", "state"]},
        {"tool": "submit_diagnosis", "args": {"mandate": "Speed up checkout", "diagnosis_path": "company/diagnoses/checkout.md"}}
      ]}
    ]},
    {"type": "ceo_action", "input": "NO", "reason": "The cart is slow, not the payment page."}
  ],
  "checks": {
    "includes": [
      "CEO calls grant .*\\nresearcher is woken on ticket 1\\n",
      "CEO's reason: The cart is slow, not the payment page\\.\\nresearcher is woken on ticket 1\\nMandate 'Speed up checkout': INVESTIGATING"
    ]
  }
}
```

Steps run in order.

- **`ceo_action` with `calls`**: the CEO's Session calls the office's tools with the owner token. Each call names a `tool` and its `args`.
- **`ceo_action` with `input`**: the CEO answers `YES`, `NO` or `DISCUSS` at the first gate that is waiting, through the same code that asks at `claudarama open`. A `NO` gives its one-line `reason`. An answer with no gate waiting fails the scenario.
- **`mock_llm_turns`**: each entry of `turns` is one scripted turn, with the `role` that runs it, the `ticket` whose thread wakes it, and its `calls`. A call is one of the office's tools (`tool`, `args`) or a command the turn runs where it works, which is its ticket's worktree (`run`). The turns of one step run side by side; the step ends when each has ended.

The office wakes every Role itself, and after each step the walk shows who it woke. A scripted turn is the turn the office queued for that Role on that ticket; it acts when the walk reaches its step. A scripted turn the office did not wake fails the scenario. The office looks at GitHub when a turn ends, before the turn shows as ended, so a pull request a turn opens or a last ticket it closes wakes the next Role within that turn's step.

The office shows one line per event, and `checks` match against these lines:

```
CEO calls <tool> <args> -> <answer>
<role> is woken on ticket <ticket>
<role>'s brief:
  | <the brief the turn was started with, line by line>
<role> calls <tool> <args> -> <answer>
<role> calls <tool> <args> -> REFUSED: <the server's reason>
<role> runs <command> -> <output>
<role>'s turn: done
<role>'s turn: refused: <why the office did not start it>
<role>'s turn: failed: <the error>
Notification: <what the office told the CEO on the desktop>
Diagnosis gate: mandate '<mandate>', diagnosis at <path>
CEO answers YES
CEO answers NO
CEO's reason: <the reason>
Mandate '<mandate>': <STATUS>
Mandate '<mandate>': <STATUS>, waiting for the CEO
The CEO's checkout is on <branch>; worktrees: <ticket-1, ticket-2, or none>
```

After each step come the turns the office queued during it, then what it told the CEO, then every Mandate's line, so a check can name the step, who it woke and the state it leaves: `"CEO answers YES\\npm is woken on ticket 1\\nMandate 'Speed up checkout': PLANNING"`. The line after them names the branch of the CEO's checkout and the tickets that have a worktree.

`scenarios/loop.json` walks one Mandate through every state from its grant to CLOSED, and a second one back to investigation after a ticket's second FAIL. A change to how the loop moves adds its scripted turns, CEO answers and checks there.

## What CI runs

- `pytest`, which walks `scenarios/loop.json` through a real office.
- The free checker, `python -m claudarama.scenario scenarios`, which refuses a malformed scenario without running it.
- The sealing check, `python scripts/check_sealing.py`. Once a scenario is on the main branch, its `role`, its `prompt`, each of its `includes` and `excludes` and its `judge` stay. Adding steps and checks is always allowed.

## Incident receipts

If a bug occurs in the live office, the incident can only be closed once a new scenario is added to the harness that reproduces the bug and proves the fix.
