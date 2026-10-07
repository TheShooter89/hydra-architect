---
name: hydra-final-verifier
description: Run final deterministic checks for the Hydra swarm.
mode: subagent
permission:
  edit: deny
  bash: allow
---
# hydra-final-verifier

This agent is configured by the Hydra plugin. Its prompt is injected from the installed workflow's `prompts/` folder at OpenCode startup.
