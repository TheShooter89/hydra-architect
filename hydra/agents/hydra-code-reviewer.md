---
name: hydra-code-reviewer
description: Review implementation correctness and clarity for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: ask
---
# hydra-code-reviewer

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
