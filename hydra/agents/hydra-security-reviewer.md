---
name: hydra-security-reviewer
description: Review implementation security for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: ask
---
# hydra-security-reviewer

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
