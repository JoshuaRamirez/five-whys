---
name: five-whys
description: >-
  Run an exhaustive Five Whys root-cause expansion: ask "why?" five levels deep
  with five reasons at every step (5x5x5x5x5 = 3,905 reasons) and write the
  full tree to a single JSON file, plus an index and mechanical hygiene flags.
  Use when the user says "five whys", "5 whys", "why tree", "exhaustive root
  cause tree", or runs /five-whys with a problem statement. Supports a cheap
  --smoke rehearsal and --model choice. Generates the tree only; analysis is
  left to the user.
argument-hint: "[--smoke] [--model sonnet|opus|haiku] [--breadth N --depth N] [--yes] [--resume <run-dir>] <problem statement>"
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

`S="${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py"` decides what runs, validates
every fragment and assembles the output. Don't generate reasons yourself, and
don't hand-edit fragments.

**What this plugin does not do.** It never ranks, prunes, summarizes or picks
root causes; analysis belongs to the user. It does compute mechanical aids:
hygiene flags (duplicates, restatements, over-long reasons), an index of the
top levels and measurements. Report those as facts, not verdicts.

## Step 1: Read the invocation

Leading options in `$ARGUMENTS`; everything after them is the problem statement.

| Option | Pass to `init` |
|--------|----------------|
| `--smoke` | `--preset smoke` (3 wide x 3 deep, 39 reasons, 4 agents) |
| `--model X` | `--model X` |
| `--breadth N`, `--depth N` | same flags |
| `--yes` | nothing; skips the questions in Steps 1 and 3 |
| `--resume <run-dir>` | nothing; skip straight to Step 4 for that run directory |

If there is no problem statement, ask for it and stop.

If the statement is thin (a short sentence with no specifics about the system,
the symptoms or what has been tried) and `--yes` is absent, ask the user once,
in one message, for those specifics, then stop. Treat the reply as context.

## Step 2: Create the run

If you have context, write it verbatim to `.five-whys/context.md`, then:

```bash
python3 "$S" init [options] [--context-file .five-whys/context.md] <<'FIVE_WHYS_PROBLEM'
<problem statement>
FIVE_WHYS_PROBLEM
```

It prints JSON with `run`, `shape`, `model` and `estimate`.

## Step 3: Confirm full-size runs

If `estimate.agents` is more than 5 and `--yes` was not given, tell the user in
one line: agents, reasons, `estimate.agent_tokens` and `estimate.output_tokens`
(an estimate scaled from a measured run), and ask whether to proceed. Stop until
they answer. Mention `--smoke` as the cheap alternative.

## Step 4: Dispatch wave by wave

Repeat:

1. Run `python3 "$S" plan <run> --record`.
2. If `state` is `ready`, go to Step 5. If `state` is `stuck`, stop and report
   each stuck id with its first error; offer `python3 "$S" assemble <run> --partial`.
3. Otherwise dispatch every task in `tasks` in a single message, one Agent call
   per task, all in parallel:
   - `subagent_type`: the plan's `agent` value (`five-whys:why-expander`)
   - `description`: `five whys <task id>`
   - `prompt`: the task's `prompt`, verbatim (a short pointer to the full prompt file)
   - `model`: the task's `model`, only when it is not null

   `tasks` never exceeds the concurrency cap (20 by default); ids in `waiting`
   go out in later waves.
4. When all of them have returned, run `python3 "$S" status <run>` and tell the
   user one line: `<done>/<total> fragments`. Loop back to 1.

## Step 5: Assemble

```bash
python3 "$S" assemble <run>
```

Report in two to four lines: the `file` path, `present_reasons`/`total_reasons`,
`approx_tokens`, and the hygiene counts as plain counts (for example
"hygiene flags: 2 exact duplicates, 14 near-duplicates, 0 restatements"). Do
**not** read, summarize or analyze the tree unless the user asks.

## Resuming, subsets and partial trees

- `--resume <run-dir>` continues an interrupted run by repeating Step 4;
  `plan` skips fragments that already validate.
- `plan <run> --only 2.3,4.1` dispatches chosen branches. Assemble the result
  with `assemble <run> --partial`, which marks missing branches in the tree.

## Loading a finished tree

When the user asks to load or analyze a tree, read `index.md` in the run
directory first, then read `five-whys.json` **whole** before drawing any
conclusion: page through it with Read in consecutive 400-line windows (`offset`
1, 401, 801, ...) until the final `]}` line; much larger windows exceed Read's
token limit. For one branch, `python3 "$S" show <run> --id <id>` prints it with
its ancestors, and `python3 "$S" show <run> --sample 10` prints random reasons
with their ancestors for spot checks. `hygiene.json` lists mechanical flags; treat them as leads for
the user's analysis, not as judgments.
