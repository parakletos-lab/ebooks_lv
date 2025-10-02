# Custom Chat Modes

This workspace defines custom Copilot chat modes in `.github/chatmodes/`.

## Available Modes
- `engineering-agent.chatmode.md` – Autonomous engineering + QA + analysis agent (plans, edits, docker tests, DevTools UI inspection) respecting `AGENTS.md` Rule 0.

## Usage
1. Open VS Code with Copilot Chat enabled.
2. Copilot should auto-discover workspace chat modes (in preview builds) located here.
3. Select the mode from the chat mode dropdown (may appear after reload).
4. Provide a concise request; the mode will generate criteria, a plan, and then act.

## Conventions
- Only add additional modes with clear, distinct scopes.
- Keep YAML frontmatter `description` short; it becomes placeholder text.
- Favor minimal tool lists (principle of least privilege) but include what the mode needs.

## Adding Another Mode
Copy the pattern:
```
---
description: One-line summary
tools: ['codebase','search']
model: Claude Sonnet 4
---
# Title
Instructions...
```

Avoid duplicating features of existing modes unless you intentionally want divergence.
