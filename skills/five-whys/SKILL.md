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

`S="${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py"` parses the invocation, decides
what runs, validates every fragment and assembles the output. Don't generate
reasons yourself, and don't hand-edit fragments.

**What this plugin does not do.** It never ranks, prunes, summarizes or picks
root causes; analysis belongs to the user. It does compute mechanical aids:
hygiene flags (duplicates, restatements, cross-branch leads, over-long
reasons), an index of the top levels and measurements. Report those as facts,
not verdicts. The README's design decisions separate run output and reading
aids, which never judge reasons, from development measurement in
`docs/self-improvement/`, where the maintainer scores them; a run never does.

## Step 1: Parse the invocation

Paste `$ARGUMENTS` unchanged between the markers:

```bash
python3 "$S" parse <<'FIVE_WHYS_ARGS'
$ARGUMENTS
FIVE_WHYS_ARGS
```

It prints `problem`, `init_flags`, `plan_flags`, `yes`, `resume`, `errors` and
`notes`. Leading options come first; everything after them (or after `--`) is
the problem statement.

| Option | Effect |
|--------|--------|
| `--smoke` | 3 wide x 3 deep: 39 reasons, 4 agents |
| `--model NAME` | `sonnet`, `opus` or `haiku` for the expander agents |
| `--breadth N`, `--depth N` | Any complete shape |
| `--split N` | Levels the root agent writes |
| `--max-parallel N` | Agents per wave (5 by default) |
| `--context-file PATH` | Context included in every prompt |
| `--base DIR` | Where runs are written |
| `--yes` | Skip the questions in Steps 1 and 3 |
| `--resume RUN_DIR` | Continue an interrupted run |

- If `errors` is not empty, show the errors and this option list, then stop.
- If `notes` is not empty, mention them in one line and continue.
- If `resume` is set, go to Step 4 with that run directory, adding `plan_flags`
  to the first `plan` call.
- If `yes` is false and the problem is thin, ask the user once, in one message,
  for specifics about the system, the symptoms and what has been tried, then
  stop. Thin: "Deploys fail." Specific enough: "Deploys of the payments service
  fail on Friday afternoons since CI moved to self-hosted runners; retries pass."
  When the user replies, write the reply verbatim to `.five-whys/context.md`
  and continue with Step 2, adding `--context-file .five-whys/context.md`.

## Step 2: Create the run

`init_flags` is already shell-quoted; paste it as is:

```bash
python3 "$S" init <init_flags> [--context-file .five-whys/context.md] <<'FIVE_WHYS_PROBLEM'
<problem>
FIVE_WHYS_PROBLEM
```

It prints JSON with `run`, `shape`, `model`, `max_parallel`, `estimate` and
`confirm`.

## Step 3: Confirm when init asks

`confirm` is true for runs of more than 5 agents. If it is true and `yes` is
false, tell the user in one line: agents, reasons, the agent-token range from
`estimate.agent_tokens_low` to `estimate.agent_tokens`, and
`estimate.output_tokens` (scaled from measured runs), and ask whether to
proceed. Stop until they answer. Mention `--smoke` as the cheap alternative.

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

   `tasks` never exceeds the run's wave size (5 by default); ids in `waiting`
   go out in later waves, and their prompts include what earlier waves wrote.
4. When all of them have returned, run `python3 "$S" status <run>` and tell the
   user one line: `<done>/<total> fragments`. Loop back to 1.

## Step 5: Assemble

```bash
python3 "$S" assemble <run>
```

Report in two to four lines: the `file` path, `present_reasons`/`total_reasons`,
`approx_tokens`, and the hygiene counts as plain counts (for example
"hygiene flags: 0 exact duplicates, 3 near-duplicates, 0 restatements, 11
cross-branch leads"). Do **not** read, summarize or analyze the tree unless the
user asks.

## Resuming, subsets and partial trees

- `--resume <run-dir>` continues an interrupted run by repeating Step 4;
  `plan` skips fragments that already validate. `--max-parallel N` with
  `--resume` changes the wave size for the rest of the run.
- `plan <run> --only 2.3,4.1` dispatches chosen branches. Assemble the result
  with `assemble <run> --partial`, which marks missing branches in the tree.

## Loading a finished tree

When the user asks to load or analyze a tree, read `index.md` in the run
directory first, then read `five-whys.json` **whole** before drawing any
conclusion, using the Read windows listed at the end of `index.md` (each stays
under Read's size limit). For one branch, `python3 "$S" show <run> --id <id>`
prints it with its ancestors, and `python3 "$S" show <run> --sample 10` prints
random reasons with their ancestors for spot checks. `hygiene.json` lists
mechanical flags, including `cross_branch` pairs that may state one cause in
two places; treat them as leads for the user's analysis, not as judgments.
