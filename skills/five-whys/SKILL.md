---
name: five-whys
description: >-
  Run an exhaustive Five Whys expansion for one problem or a list of problems:
  ask why, or any combination of why, what, when, where and how, each up to
  five levels deep with five answers at every step (5x5x5x5x5 = 3,905 answers
  per tree), and write every tree to a single JSON file, plus an index and
  mechanical hygiene flags. Use when the user says "five whys", "5 whys", "why
  tree", "exhaustive root cause tree", "five Ws", "what when where how", "ask
  how and where about", or runs /five-whys. Supports --ask, --depth 1-5,
  --model-level 1-5 and a cheap --smoke rehearsal. Generates the trees only;
  analysis is left to the user.
argument-hint: "[--ask why,what,when,where,how] [--depth 1-5] [--model-level 1-5] [--smoke] [--yes] [--resume <run-dir>] <problem, or one problem per line>"
---

# Five Whys

Build a complete answer tree for each input and each chosen question in
`$ARGUMENTS`. Inputs are one problem, or a list with one problem per line.
Questions are `why`, `what`, `when`, `where` and `how`, in any combination
(`why` by default). At the full depth of 5, each tree holds:

| Level | Question asked                               | Answers |
|-------|----------------------------------------------|---------|
| 1     | The tree's question about the input          | 5       |
| 2     | The same question of each level-1 answer     | 25      |
| 3     | The same question of each level-2 answer     | 125     |
| 4     | The same question of each level-3 answer     | 625     |
| 5     | The same question of each level-4 answer     | 3,125   |

`S="${CLAUDE_PLUGIN_ROOT}/scripts/fivewhys.py"` parses the invocation, decides
what runs, validates every fragment and assembles the output. Don't generate
answers yourself, and don't hand-edit fragments.

**What this plugin does not do.** It never ranks, prunes, summarizes or picks
answers; analysis belongs to the user. It does compute mechanical aids:
hygiene flags (duplicates, restatements, cross-branch leads, over-long
answers), an index of the top levels and measurements. Report those as facts,
not verdicts. The README's design decisions separate run output and reading
aids, which never judge answers, from development measurement in
`docs/self-improvement/`, where the maintainer scores them; a run never does.

## Step 1: Parse the invocation

Paste `$ARGUMENTS` unchanged between the markers:

```bash
python3 "$S" parse <<'FIVE_WHYS_ARGS'
$ARGUMENTS
FIVE_WHYS_ARGS
```

It prints `script`, `questions`, `questions_from_words`, `problem`, `inputs`,
`input_hints`, `init_flags`, `plan_flags`, `yes`, `resume`, `errors` and
`notes`. Leading options come first; everything after them (or after `--`) is
the input text. Each non-empty line is one input, with list markers such as
`- ` or `2. ` removed. A leading phrase such as "ask how and where for:"
chooses the questions and is removed from the inputs. `script` is the absolute
path of `fivewhys.py`: use it as `$S` in every later command, never a shortened
relative path such as `scripts/fivewhys.py`.

| Option | Effect |
|--------|--------|
| `--smoke` | 3 wide x 3 deep: 39 answers, 4 agents |
| `--ask QUESTIONS` | Questions, comma-separated: `why`, `what`, `when`, `where`, `how` (`why` by default) |
| `--model-level N` | Model mix from 1 to 5, below (the session's model by default) |
| `--breadth N` | Answers per question (5 by default) |
| `--depth N` | Levels for every tree, 1 to 5 (5 by default) |
| `--split N` | Levels root agents write |
| `--max-parallel N` | Agents per wave (5 by default) |
| `--context-file PATH` | Context included in every prompt |
| `--base DIR` | Where runs are written |
| `--yes` | Skip the questions in Steps 1 and 3 |
| `--resume RUN_DIR` | Continue an interrupted run |

| Level | Root agents | Branch agents |
|-------|-------------|---------------|
| 1 | haiku | haiku |
| 2 | sonnet | haiku |
| 3 | sonnet | sonnet |
| 4 | opus | sonnet |
| 5 | opus | opus |

- If `errors` is not empty, show the errors and these option lists, then stop.
- If `notes` is not empty, mention them in one line and continue.
- If `resume` is set, go to Step 4 with that run directory, adding `plan_flags`
  to the first `plan` call.
- Settle the questions. `init_flags` already carries `--ask` with the questions
  parse found. If `questions_from_words` is true, or the user named questions in
  words parse didn't catch (for example "and also where"), say in one line
  which questions you'll ask and put that set in `--ask`. If the words are
  ambiguous and `yes` is false, ask instead of guessing, then stop.
- Settle the inputs. If `yes` is false and `input_hints` is not empty, or the
  text reads differently from `inputs` (several problems on one line, or one
  problem broken across lines), ask the user once, in one friendly message:
  show the items you see as a numbered list and ask whether each should get
  its own trees, or which items to use. Stop until they answer, then use
  their list. With `yes` true, use `inputs` as parsed.
- If `yes` is false and the inputs are thin, ask the user once, in one message,
  for specifics about the system, the symptoms and what has been tried, then
  stop. Thin: "Deploys fail." Specific enough: "Deploys of the payments service
  fail on Friday afternoons since CI moved to self-hosted runners; retries pass."
  When the user replies, write the reply verbatim to `.five-whys/context.md`
  and continue with Step 2, adding `--context-file .five-whys/context.md`.

## Step 2: Create the run

`init_flags` is already shell-quoted; paste it as is, then the settled inputs,
one per line:

```bash
python3 "$S" init <init_flags> [--context-file .five-whys/context.md] <<'FIVE_WHYS_INPUTS'
<input 1>
<input 2>
FIVE_WHYS_INPUTS
```

It prints JSON with `run`, `inputs`, `questions`, `trees`, `shape`,
`model_level`, `models`, `max_parallel`, `estimate` and `confirm`.

## Step 3: Confirm when init asks

`confirm` is true for runs of more than 5 agents. If it is true and `yes` is
false, tell the user in one line: how many inputs, which questions and how
deep, the model level if one was chosen, agents, answers, the agent-token range
from `estimate.agent_tokens_low` to `estimate.agent_tokens`, and
`estimate.output_tokens` (scaled from measured why runs), and ask whether to
proceed. Stop until they answer. Mention `--smoke` as the cheap alternative.

## Step 4: Dispatch wave by wave

Repeat:

1. Run `python3 "$S" plan <run> --record`.
2. If `state` is `ready`, go to Step 5. If `state` is `stuck`, stop and report
   each stuck id with its first error; offer `python3 "$S" assemble <run> --partial`.
3. Otherwise dispatch every task in `tasks` in a single message, one Agent call
   per task, all in parallel:
   - `subagent_type`: the plan's `agent` value (`five-whys:expander`)
   - `description`: `five ws <task id>`
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

Report in two to four lines: the `file` path, the number of `inputs`, the
`questions`, `present_answers`/`total_answers`, `approx_tokens`, and the
hygiene counts as plain counts (for example "hygiene flags: 0 exact duplicates,
3 near-duplicates, 0 restatements, 11 cross-branch leads"). Do **not** read,
summarize or analyze the answers unless the user asks.

## Resuming, subsets and partial trees

- `--resume <run-dir>` continues an interrupted run by repeating Step 4;
  `plan` skips fragments that already validate. `--max-parallel N` with
  `--resume` changes the wave size for the rest of the run.
- `plan <run> --only 1.why.2,2.how.4` dispatches chosen branches. Assemble the
  result with `assemble <run> --partial`, which marks missing branches.

## Loading a finished run

When the user asks to load or analyze a run, read `index.md` in the run
directory first, then read `five-whys.json` **whole** before drawing any
conclusion, using the Read windows listed at the end of `index.md` (each stays
under Read's size limit). Ids are the input number, the question, then
positions, so `2.how.4.1` is the 1st answer under `2.how.4`, the 4th how-answer
about input 2. For one input, tree or branch, `python3 "$S" show <run> --id <id>`
prints it with its ancestors, and `python3 "$S" show <run> --sample 10` prints
random answers with their ancestors for spot checks. `hygiene.json` lists
mechanical flags, including `cross_branch` pairs, marked `across_inputs` and
`across_questions`, that may state one thing in two places; treat them as leads
for the user's analysis, not as judgments.
