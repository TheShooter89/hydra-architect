---
description: Manage the active Hydra model profile.
agent: hydra-profile
---

The user invoked `/hydra-profile $ARGUMENTS`.

- If "$1" is one of [default, cheap, free, max-quality, free-week]:
  call the `hydra_profile` tool with action="set" and profile="$1".
- If "$1" is "show":
  call `hydra_profile` with action="show" and profile="$2" (omit profile to show the active one).
- If "$1" is "diff" and "$2" and "$3" are provided:
  call `hydra_profile` with action="diff", profile="$2", other="$3".
- Otherwise explain the usage.

Do not perform any other action.
