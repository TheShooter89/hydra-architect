---
name: hydra-adjudicator
description: Resolve review conflicts for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: ask
---
# hydra-adjudicator

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
