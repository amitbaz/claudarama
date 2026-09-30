# The Pack Schema

Every project using Claudarama must include a `.claudarama/` directory. This "Pack" injects project-specific context into the project-agnostic Core.

Below is the required schema for the files inside a Pack.

## `company.md`
The charter and current company goal. It can be a full document or a pointer to the project's existing charter. It must list the active Key Results (KRs) that the company is currently optimizing for (e.g., "AI engine must achieve a 95% pass rate").

## `org.yaml`
Defines the structure and limits of the company for this specific project.
```yaml
concurrency:
  max_active_turns: 3  # How many members can work simultaneously
departments:
  active:
    - engineering
    - product
    - research
  locked:
    - name: marketing
      milestone: "v1.0 launch"
```

## `stack.yaml`
Defines the technical environment so the Core knows how to operate the codebase.
```yaml
paths:
  main_checkout: "."
commands:
  test: "npm run test"
  lint: "npm run lint"
  build: "npm run build"
rules:
  - "Always use single quotes in TypeScript files"
```

## `gates.yaml`
Defines the mechanical enforcement boundaries for the CEO. This generates the allowlist for the PreToolUse hook.
```yaml
deny:
  - "aws *"          # Block all AWS CLI commands
  - "npm publish"    # Only the CEO can publish
allow:
  - "gh issue *"     # Allow issue manipulation
  - "git *"
budget:
  max_spend_per_turn: 2.50
```

## `profiles/*.md`
Markdown files that overlay specific domain knowledge onto the core crafts. For example, `.claudarama/profiles/frontend-engineer.md` might contain:
> *Always use Tailwind CSS for styling in this project. Do not write custom CSS.*
