# The Pack Schema

Every project using Claudarama has a `.claudarama/` directory, the Pack. It injects project-specific context into the project-agnostic Core. `claudarama setup` scaffolds it, and nothing in it is a setting the code ignores.

Run `claudarama setup` in the project. It needs `gh` installed and signed in, and says which of the two to fix if not. If the Pack already exists, setup leaves it untouched.

## What setup writes

```
.claudarama/
  company.md
  org.yaml
  stack.yaml
  gates.yaml
  profiles/
  scenarios/
  company/diagnoses/
  company/retros/
```

A test fails if setup writes a key the settings loader, the allowlist builder or the gate hook does not parse.

## `company.md`
The charter and current company goal, loaded first into every brief. It can be a full document or a pointer to the project's existing charter.

## `org.yaml`
Flat `key: value` lines. Setup writes the first two; the rest are optional and take their defaults when absent.

| Key | Default | Effect |
|---|---|---|
| `concurrency` | 3 | How many turns this office runs at once. |
| `stall_timeout_minutes` | 20 | A turn with no output for this long is killed. |
| `escalate_stuck_turns` | false | `true` retries a stalled turn on a higher model. |
| `escalation_model` | opus | The model used for that retry. |
| `resume_per_ticket` | false | `true` resumes a ticket's earlier conversation instead of starting fresh. |
| `limit_fallback_minutes` | 60 | How long to pause when a usage limit gives no reset time. |

## `stack.yaml`
The commands a Turn may run, under a `commands:` block. Each becomes an allowed Bash rule, with and without arguments. Setup writes the block empty.
```yaml
commands:
  test: "npm run test"
  lint: "npm run lint"
```

## `gates.yaml`
Extra commands to deny, under a `deny_rules:` list, added to the Core's own deny rules. Setup writes one rule that keeps a Turn from switching the `gh` account.
```yaml
deny_rules:
  - "Bash(npm publish *)"
```

## `profiles/<role>.md`
Overlays appended to a Role's brief. This is the only place project stack knowledge belongs. For example, `.claudarama/profiles/frontend-engineer.md` might contain:
> *Always use Tailwind CSS for styling in this project. Do not write custom CSS.*

## `scenarios/`
Scenario files that `claudarama eval` runs when given no paths.

## `company/diagnoses/` and `company/retros/`
The fixed places for a Diagnosis and a Retro, one file per Mandate. The office accepts a Diagnosis only at `company/diagnoses/<name>.md` and a Retro only at `company/retros/<name>.md`, submitted by its path from the project's root, and refuses any other path.
