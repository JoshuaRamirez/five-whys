# five-whys

A Claude Code plugin that runs an **exhaustive** Five Whys on one problem or a
list of problems. It asks "why?" up to five levels deep, and every answer is
five reasons, each asked "why?" again. At the full depth, each problem gets:

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

A list of problems, one per line, each asked why two levels deep:

```
/five-whys --depth 2
1. Deploys keep failing on Friday afternoons
2. Login is slow after 9am
3. Nightly backups skip runs
```

`--depth` sets the levels for every input, from 1 to 5:

| Depth | Reasons per input | 10 inputs |
|-------|-------------------|-----------|
| 1 | 5 | 50 |
| 2 | 5 + 25 = 30 | 300 |
| 3 | 155 | 1,550 |
| 4 | 780 | 7,800 |
| 5 | 3,905 | 39,050 |

Options go before the inputs; `--` ends them if an input itself starts with
dashes. The script parses them, so a typo is an error rather than part of an
input. Each line is one input, and list markers such as `- ` or `2. ` are
dropped. When it's unclear whether the text is one problem or several, the
skill shows the items it sees and asks which should get their own five whys.

| Option | Effect | Why it exists |
|--------|--------|---------------|
| `--smoke` | 3 wide x 3 deep: 39 reasons from 4 agents | Rehearse cheaply before paying for a full run |
| `--model NAME` | Run the expander agents on `sonnet`, `opus` or `haiku` | Trade cost against depth; the quality effect is unmeasured |
| `--breadth N` | Reasons per why | Size the tree to the problem |
| `--depth N` | Levels of why for every input, 1 to 5 | Size the tree to the problem |
| `--split N` | Levels the root agent writes (default: half the depth) | Balance fragment size against agent count for unusual shapes |
| `--max-parallel N` | Agents per wave, 5 by default, up to 20 | Choose between speed and machine load; smaller waves also let later branches see earlier ones |
| `--context-file PATH` | Put a file's text in every agent prompt | Give specifics without being asked for them |
| `--base DIR` | Write runs somewhere other than `.five-whys/` | Keep test runs apart from real ones |
| `--yes` | Skip the context question and the cost confirmation | Unattended runs such as the eval |
| `--resume RUN_DIR` | Continue an interrupted run; add `--max-parallel N` to change the wave size | Recover without losing finished fragments |

If the inputs are thin, the skill asks once for specifics (the system, the
symptoms, what has been tried) and puts them in every agent prompt. Runs of
more than five agents show how many inputs get the initial whys, the reasons,
the agents and an estimate, and ask before dispatching.

Agents are packed so each writes at most 155 reasons. At depths 1 and 2, one
agent covers several inputs, and at depth 3 each input gets one agent. Depth 4
takes 6 agents per input and depth 5 takes 26.

### Test an unpublished checkout

Claude Code loads installed plugins from its cache. To run the skill and agent
text in a working copy instead, start a fresh session with
`claude --plugin-dir /path/to/five-whys`.

## What a full run costs

Cost depends first on the session that dispatches the agents. Each agent
inherits that session's context, such as its tools and MCP server instructions,
before it reads anything. Second is how much the agents read. Three runs were
measured on 2026-09-13 with claude-opus-5, read from Claude Code's subagent
logs with `docs/self-improvement/usage.py`:

| | v0.2.0 full run, interactive session with many tools, in this repository | v0.3.0 full run, headless `claude -p`, in this repository | Root and one branch, headless, clean directory, a problem naming no files |
|---|---|---|---|
| Session context at an agent's first turn | about 21k tokens | about 4.9k tokens | about 4.6k tokens |
| Evidence reading | local files and Bash exploration | local files and Bash exploration | none beyond the prompt |
| Turns per branch agent | 10-22 | 8-20 | 5 |
| Tokens per agent, as reported | root 44.1k; branches 57.5k-72.5k, mean 63.1k | root 14.8k; branches 28.4k-61.7k, mean 38.1k | root 11.3k; branch 23.6k |
| Agent tokens in total | about 1.62M | about 0.97M | not a full run |
| Output tokens per branch, including thinking | 15k-22k | mean 18.9k | 15k |
| Context re-read across a branch's turns, billed on top | 0.4M-1.0M, mostly cache reads | 0.13M-0.54M | 69k |
| Output file | 595 KB | 607 KB | not a full run |
| Wall clock, creation to last fragment | not measured (a restart interrupted it) | 29 minutes in waves of 5 | not a full run |

A full 5x5 run is estimated at about 0.60M-1.62M agent tokens and 148k output
tokens. Expect the low end from a headless or lightly loaded session on a
self-contained problem. Expect the high end from an interactive session with
many plugins and MCP servers, inside a large project whose files agents read.
Starting a full run from `claude -p` in a fresh session keeps inherited
context small. These figures are for one input; a list multiplies them, and the
skill shows the total before dispatching.

Claude Code runs at most 20 subagents at once by default. This plugin sends
waves of 5 unless you choose otherwise, so a full run takes six waves. When
measuring a run, use a dedicated session so other work doesn't mix into the
totals.

## Output

Each run lives in `.five-whys/<timestamp>-<slug>/`:

| File | Contents |
|------|----------|
| `five-whys.json` | The tree, one reason per line |
| `index.md` | The settings used, levels 1-2 with ids, and the Read windows for loading the whole tree |
| `hygiene.json` | Mechanical flags, each with the texts involved: exact duplicates, near-duplicates, reasons restating a parent or ancestor, cross-branch leads, over-long reasons |
| `run.json` | Plugin version, options given, shape, model, estimate shown, dispatch attempts, each wave's start time and ids, duration, output size |
| `fragments/` | Raw agent output |
| `prompts/` | The full prompt each agent was dispatched with |
| `check-log.jsonl` | Every check an agent ran, with the kinds of errors and warnings, so repair cycles are countable |

`.five-whys/.gitignore` keeps runs out of git, since problem statements can be sensitive.

The layout, shown with reasons from an earlier self-run:

```json
{"schema":"five-whys/3", ... ,"input_count":1, ... ,"inputs":[
{"id":"1","depth":0,"input":"The five-whys Claude Code plugin (v0.2.0) is rated 8/10 instead of 10/10.","whys":[
 {"id":"1.3","depth":1,"reason":"Hygiene flags rely on Jaccard word overlap, which misses paraphrases and deep cross-branch convergence.","whys":[
  {"id":"1.3.4","depth":2,"reason":"Branch agents in one wave run concurrently, so sibling-aware prompts cannot show reasons being written simultaneously elsewhere.","whys":[
   {"id":"1.3.4.1","depth":3,"reason":"plan builds the written list only from the root fragment, so later-wave branches never see finished wave-one branch reasons.","whys":[
```

- An input's `whys` answer "Why does this happen?" about that input. A reason's
  `whys` answer "Why <that reason>?".
- `id` is the dotted path from the top and starts with the input number.
  `2.4.1` is the 1st reason under `2.4`, the 4th reason about input 2.
- The header records the plugin version, shape, model, per-level counts and
  average words, duration from creation to the last fragment, each wave's
  fragment count and seconds, any assumptions
  the agents stated, and whether the tree is complete.

To load a tree, ask Claude to read it. The skill reads `index.md`, then the
whole file in the windows `index.md` lists, which are sized in bytes to stay
under the Read tool's limit. `show --id <id>` prints a single branch with its
ancestors.

## What validation covers

- **`check` (enforced):** every fragment is valid JSON with exactly the right
  number of reasons at every level. Agents repair and re-check, at most 3 times.
  After `OK`, `check` also prints non-blocking warnings (repeated text,
  restatements, over-long reasons). For a branch fragment it compares against
  the root's real reasons, so restating an ancestor is caught before assembly.
- **`hygiene.json` (advisory):** word overlap on stemmed words, from the
  standard library. Near-duplicates need a similarity of 0.6. Pairs under
  different level-1 reasons scoring 0.45 or more are listed as `cross_branch`
  leads, because one cause may be stated in two places. Flags annotate;
  nothing is removed.
- **Measured on a real tree:** among 16 pairs from the v0.2.0 self-run that
  state the same cause twice, 7 score as leads and 9 use different words and
  are missed; 2 of 8 pairs that only share vocabulary are listed as leads.
  v0.2.0's scoring flagged none of the 16. Labeled pairs: `tests/fixtures/pairs.json`.
- **Not covered:** whether a reason is true, causal or useful. That judgment is
  yours.

## Known limitations

- Reasons are hypotheses written by a model, not verified causes. Checking them
  against evidence is part of your analysis.
- Hygiene sees shared wording only; paraphrases in different words go unflagged.
- Branches in the same wave can't see each other. Later waves see only the
  first-level reasons of finished branches.
- One input's agents never see another input's reasons. A cause shared by
  several inputs appears once per input; hygiene lists close wordings as
  `cross_branch` leads marked `across_inputs`.
- Runs started before 0.3.0 can't be resumed or assembled by this version,
  because their fragments are laid out differently. `show` still reads their
  finished trees.
- Deep levels drift toward systemic causes. Agents are told to stay specific,
  name concrete things from their chain and state their assumptions, which
  reduces generic reasons but doesn't prevent them.
- How much a cheaper model changes reason quality is unmeasured, and so is how
  much two runs of the same model differ.
- The eval cases have not been run yet.
- A full run spends a large share of subscription quota in a short burst.
- Agents are told not to run network commands such as `gh` or `curl`, but they
  have Bash, so nothing enforces it. In the v0.3.0 self-run, three of 25 branch
  agents ran `gh` before this instruction existed.

## Resuming, subsets and partial trees

- `/five-whys --resume <run-dir>` continues an interrupted run; `plan` skips
  fragments that already validate. A task that fails 3 dispatches is reported
  as stuck.
- `plan --only 2.3,4.1` dispatches selected branches.
- `assemble --partial` writes a valid tree with missing branches marked.

## Script

`scripts/fivewhys.py` (Python 3.9+, standard library only), with similarity
scoring in `scripts/hygiene.py`:

| Command | Does |
|---------|------|
| `parse` (arguments on stdin) | Split `/five-whys` arguments into inputs, `init` flags and skill options, with errors for unknown or invalid options and hints when the split into inputs is unclear |
| `init` (inputs on stdin, one per line) | Create a run: `--preset`, `--breadth`, `--depth` (1-5), `--split`, `--model`, `--max-parallel`, `--context-file`, `--base`; prints the estimate and whether to confirm |
| `plan <run>` | Next wave of missing fragments with prompts; `--record` counts attempts; `--only` selects branches; `--max-parallel` changes the wave size |
| `status <run>` | Done, missing and stuck fragments, check cycles and error kinds per fragment, each wave's seconds, and the plugin version that created the run |
| `check <fragment> --breadth N --depth N` | Validate one fragment; warnings never block |
| `assemble <run>` | Write `five-whys.json`, `index.md`, `hygiene.json`; `--partial` allows missing branches |
| `show <tree-or-run>` | Print a subtree (`--id`), the top levels (`--levels`) or a random sample with ancestors (`--sample N --seed S`) |

Tests: `python3 -m unittest discover tests`. They include the labeled hygiene
pairs and a replay of the skill's dispatch loop. The replay's fragments are
synthetic filler written by the test itself, not recorded agent output, so it
checks orchestration, not what agents write.
Eval: `claude plugin eval . --allow-tools Bash Write Edit --judge-model sonnet --runs 1 --ablation none`,
run where Docker Desktop isn't installed (see RELEASING.md).
CI runs the unit tests on every push. Release steps: [RELEASING.md](RELEASING.md).
Changes: [CHANGELOG.md](CHANGELOG.md).

## Design decisions

- **Standard library only, no network.** Installs anywhere `python3` exists
  and keeps problem statements on your machine. This rules out embeddings, so
  duplicate detection is heuristic.
- **Generation only.** The plugin must not steer your analysis. The index,
  hygiene flags and measurements are mechanical aids, not judgments. The zones
  below say where that rule applies.
- **Complete trees.** Every node gets exactly `breadth` reasons down to `depth`;
  there is no early stopping or pruning.
- **Script for control, agents for content.** The script parses the
  invocation, decides what runs and verifies it; agents only write fragments.

### Where your analysis begins

| Zone | For | Allowed | Not allowed |
|------|-----|---------|-------------|
| Run output: `five-whys.json`, `index.md`, `hygiene.json`, the skill's final reply | You | Reasons verbatim, counts, mechanical flags, measurements | Ranking, summaries, selecting or pruning causes |
| Reading aids: this README, the skill's loading section, `show` | You | How to load and navigate a tree, and a generic reading method | Examples that pick causes from a real tree |
| Development measurement: `docs/self-improvement/` | The maintainer | Scored samples, audits, reviews by a model or a person | Writing a score into a run directory or anything a run shows you |

Scoring reasons is how the maintainer measures whether a change made the plugin
better. It never happens inside a run.

## How this version was made

Each version comes from running the plugin on its own rating and accounting for
every one of the 3,905 reasons. `docs/self-improvement/` holds each round's
tree, the catalog of dispositions derived from it, the per-reason ledger, audits
and a summary.

## License

MIT
