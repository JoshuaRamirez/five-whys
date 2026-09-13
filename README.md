# five-whys

A Claude Code plugin that runs an **exhaustive** Five Whys. It asks "why?" five
levels deep, and every answer is five reasons, each asked "why?" again:

```
5 + 25 + 125 + 625 + 3,125 = 3,905 reasons
```

The whole tree goes into one JSON file you can read into context in full. The
plugin also writes mechanical aids: an index, hygiene flags and measurements.
It never ranks, prunes, summarizes or picks root causes. Analysis is up to you.

## Install

```
/plugin marketplace add JoshuaRamirez/claude-code-plugins
/plugin install five-whys@RedJay
```

## Use

```
/five-whys Our deploys keep failing on Friday afternoons
```

| Option | Effect |
|--------|--------|
| `--smoke` | 3 wide x 3 deep: 39 reasons from 4 agents. A cheap rehearsal. |
| `--model sonnet\|opus\|haiku` | Run the expander agents on that model instead of your session's model. |
| `--breadth N --depth N` | Any complete shape, for example `--breadth 4 --depth 3`. |
| `--yes` | Skip the context question and the cost confirmation. |

If the problem statement is thin, the skill asks once for specifics (the
system, the symptoms, what has been tried) and puts them in every agent prompt.
Full-size runs show an estimate and ask before dispatching.

## What a full run costs

Measured on the plugin's run on its own rating (2026-09-13, session default model):

| | |
|---|---|
| Agents | 26 (1 root + 25 branches) |
| Subagent tokens | about 1.2M |
| Wall clock | about 7 minutes |
| Output | 511 KB, about 128k tokens |

Claude Code runs at most 20 subagents at once by default, so branches go out in
waves (20, then 5). `--model sonnet` costs less; its effect on quality has not
been measured.

## Output

Each run lives in `.five-whys/<timestamp>-<slug>/`:

| File | Contents |
|------|----------|
| `five-whys.json` | The tree, one reason per line |
| `index.md` | Levels 1-2 with ids, and the command that prints any branch |
| `hygiene.json` | Mechanical flags: exact duplicates, near-duplicates, reasons restating a parent or ancestor, over-long reasons |
| `run.json` | Shape, model, dispatch attempts, timing, output size |
| `fragments/` | Raw agent output |

An excerpt from the self-run:

```json
{"schema":"five-whys/1","problem":"The five-whys Claude Code plugin (v0.1.0) is rated only 6/10 ...","whys":[
 {"id":"3","depth":1,"reason":"Branch agents run in isolation, so each cannot see what siblings produced and likely repeats causes.","whys":[
  {"id":"3.1","depth":2,"reason":"Each branch prompt carries only its own ancestor chain, never reasons generated in other branches.","whys":[
   {"id":"3.1.1","depth":3,"reason":"All branch agents launch simultaneously, so no sibling output exists when each prompt is generated.","whys":[
```

- Top-level `whys` answer "Why does the problem occur?". A node's `whys` answer
  "Why <that node's reason>?".
- `id` is the dotted path from the top. `2.4.1` is the 1st reason under `2.4`.
- The header records the shape, model, per-level counts and average words,
  duration, any assumptions the agents stated, and whether the tree is complete.

To load a tree, ask Claude to read it. The skill reads `index.md`, then the
whole file in 400-line windows (Read rejects much larger windows at this
density). `show --id <id>` prints a single branch with its ancestors.

## What validation covers

- **`check` (enforced):** every fragment is valid JSON with exactly the right
  number of reasons at every level. Agents repair and re-check, at most 3 times.
- **`hygiene.json` (advisory):** word-overlap heuristics from the standard
  library. They catch copies and close rewordings, miss paraphrases that use
  different words, and sometimes flag legitimately similar siblings. Flags
  annotate; nothing is removed.
- **Not covered:** whether a reason is true, causal or useful. That judgment is
  yours.

## Known limitations

- Branch agents see the other level-1 and level-2 reasons, but not each other's
  deeper output, so deep causes can still converge across branches.
- Deep levels drift toward systemic causes. Agents are told to stay specific and
  state their assumptions, which reduces generic reasons but doesn't prevent them.
- How much a cheaper model changes reason quality is unmeasured.
- A full run spends a large share of subscription quota in a short burst.

## Resuming, subsets and partial trees

- Re-running `plan` on an interrupted run skips fragments that already validate.
  A task that fails 3 dispatches is reported as stuck.
- `plan --only 2.3,4.1` dispatches selected branches.
- `assemble --partial` writes a valid tree with missing branches marked.

## Script

`scripts/fivewhys.py` (Python 3.9+, standard library only):

| Command | Does |
|---------|------|
| `init` (problem on stdin) | Create a run: `--preset`, `--breadth`, `--depth`, `--split`, `--model`, `--max-parallel`, `--context-file` |
| `plan <run>` | Next wave of missing fragments with prompts; `--record` counts attempts; `--only` selects branches |
| `status <run>` | Done, missing and stuck fragments |
| `check <fragment> --breadth N --depth N` | Validate one fragment |
| `assemble <run>` | Write `five-whys.json`, `index.md`, `hygiene.json`; `--partial` allows missing branches |
| `show <tree-or-run>` | Print a subtree (`--id`) or the top levels (`--levels`) |

Tests: `python3 -m unittest discover tests`

## Design decisions

- **Standard library only, no network.** Installs anywhere `python3` exists.
  This rules out embeddings, so duplicate detection is heuristic.
- **Generation only.** The plugin must not steer your analysis. The index,
  hygiene flags and measurements are mechanical aids, not judgments.
- **Complete trees.** Every node gets exactly `breadth` reasons down to `depth`;
  there is no early stopping or pruning.
- **Script for control, agents for content.** The script decides what runs and
  verifies it; agents only write fragments.

## How this version was made

Version 0.2.0 came from running the plugin on its own 6/10 rating and
accounting for every one of the 3,905 reasons. `docs/self-improvement/` holds
the tree, the improvement catalog derived from it, the per-reason ledger and a
summary of how each reason was handled.

## License

MIT
