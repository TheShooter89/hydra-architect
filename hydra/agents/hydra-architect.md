---
name: hydra-architect
description: Produce candidate designs for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: ask
---
# hydra-architect

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
