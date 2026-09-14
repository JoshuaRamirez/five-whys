---
name: five-whys
description: >-
  Shortcut for the five-ws skill that asks only why: an exhaustive Five Whys
  for one problem or a list of problems, up to five levels deep with five
  reasons at every step (3,905 per problem at full depth). Use when the user
  says "five whys", "5 whys", "why tree", "exhaustive root cause tree", or runs
  /five-whys.
argument-hint: "[--depth 1-5] [--model-level 1-5] [--smoke] [--yes] [--resume <run-dir>] <problem, or one problem per line>"
---

# Five Whys

`/five-whys` is `/five-ws` with `--ask why`. Read
`${CLAUDE_PLUGIN_ROOT}/skills/five-ws/SKILL.md` and follow it exactly, with one
change in Step 1: put `--ask why` in front of `$ARGUMENTS` before pasting it,
unless `$ARGUMENTS` already contains `--ask` or `--resume`.
