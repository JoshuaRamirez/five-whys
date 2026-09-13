---
name: five-whys
description: >-
  Run an exhaustive Five Whys root-cause expansion: ask "why?" five levels deep
  with five reasons at every step (5x5x5x5x5 = 3,905 reasons) and write the
  full tree to a single JSON file. Use when the user says "five whys",
  "5 whys", "why tree", "exhaustive root cause tree", or runs /five-whys with a
  problem statement. Generates the tree only; analysis is left to the user.
argument-hint: <problem statement>
---

# Five Whys (5 x 5 x 5 x 5 x 5)

Build the complete why-tree for the problem in `$ARGUMENTS`:

| Level | Question asked                 | Reasons |
|-------|--------------------------------|---------|
| 1     | Why does the problem occur?    | 5       |
| 2     | Why <level-1 reason>? (each)   | 25      |
| 3     | Why <level-2 reason>? (each)   | 125     |
| 4     | Why <level-3 reason>? (each)   | 625     |
| 5     | Why <level-4 reason>? (each)   | 3,125   |

Total: 3,905 reasons in one JSON file.

The work is split into 26 agent tasks: 1 root task (levels 1-2), then 25 branch
tasks (levels 3-5 under each level-2 reason). The script
`${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py` decides what runs, validates every
fragment, and assembles the output. Don't generate reasons yourself, and don't
hand-edit fragments.

## Step 1: Get the problem

If `$ARGUMENTS` is empty, ask the user for the problem statement and stop until
they answer. Otherwise use it verbatim.

## Step 2: Create the run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py" init <<'FIVE_WHYS_PROBLEM'
<problem statement>
FIVE_WHYS_PROBLEM
```

It prints the run directory (under `.five-whys/` in the current working
directory). Tell the user in one line that the run has started and roughly
26 agents will be dispatched.

## Step 3: Dispatch until ready

Repeat:

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py" plan <run-dir>`.
2. If `state` is `ready`, go to Step 4.
3. Otherwise, dispatch the tasks in `tasks` in a single message, one Agent
   call per task, all in parallel, **at most 20 per message**. Claude Code
   caps concurrent subagents at 20 by default, and calls over the cap are
   refused.
   - `subagent_type`: the plan's `agent` value (`five-whys:why-expander`)
   - `description`: `five whys <task id>`
   - `prompt`: the task's `prompt`, verbatim
4. When all of them have returned, loop back to 1. The next plan re-lists only
   the fragments that are still missing or invalid, including any tasks left
   over from the cap.

Round one is the root task alone. The 25 branch tasks follow in two rounds
(20, then 5). If a task that was actually dispatched is still listed after
three rounds, stop and report its `errors` to the user instead of looping.

## Step 4: Assemble

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py" assemble <run-dir>
```

Report the output path, `total_reasons`, and `approx_tokens` in two or three
lines. Do **not** read, summarize, or analyze the tree unless the user asks.
What to do with it is the user's call.

## Loading a finished tree into context

When the user asks to load or analyze a `five-whys.json`, read it **whole**
before drawing any conclusion. The file puts one reason per line, so page
through it with the Read tool in consecutive 400-line windows
(`offset` 1, 401, 801, ...) until you reach the final `]}` line. The header
line explains how ids map to the tree.
