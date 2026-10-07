---
name: hydra-test-scout
description: Inventory tests and define test strategy for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: ask
---
# hydra-test-scout

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
