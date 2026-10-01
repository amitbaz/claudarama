---
description: Open the office in this session. It becomes the CEO's Session and Claude becomes the Assistant. The same as running claudarama open in a terminal.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/claudarama open --attach), mcp__plugin_claudarama_claudarama__attach
---

The CEO opened the office in this session. Below is your brief as the Assistant, followed by an attach code.

1. Call the `attach` tool of the `claudarama` office server with that code, before anything else. It makes this session the CEO's Session: the office server speaks for the CEO from then on, and the office starts working.
2. Then follow the brief. It is your Role for the rest of this session.

If `attach` is refused, tell the CEO what it said and stop.

!`${CLAUDE_PLUGIN_ROOT}/bin/claudarama open --attach`
