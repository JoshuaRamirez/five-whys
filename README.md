# five-ws

A Claude Code plugin that runs an **exhaustive** Five Ws on one problem or a
list of problems. Choose any combination of five questions (why, what, when,
where and how), and each problem gets one tree per question. Each question is
asked up to five levels deep: every answer gets five answers of its own, each
asked the same question again. At the full depth, each tree holds:

```
5 + 25 + 125 + 625 + 3,125 = 3,905 answers
```

Asking only why gives a classic exhaustive Five Whys, and `/five-whys` stays
as a shortcut for exactly that.

The whole run goes into one JSON file you can read into context in full. The
plugin also writes mechanical aids: an index, hygiene flags and measurements.
It never ranks, prunes, summarizes or picks answers. Analysis is up to you.

## Install

```
/plugin marketplace add JoshuaRamirez/claude-code-plugins
/plugin install five-ws@RedJay
```

## Use

```
/five-ws Our deploys keep failing on Friday afternoons
```

That asks why. Name other questions with `--ask`, or in words at the start:

```
/five-ws --ask what,when,how Our deploys keep failing on Friday afternoons
/five-ws ask how and where for: Our deploys keep failing on Friday afternoons
```

When the questions come from your words, the skill says which set it understood.

A list of problems, one per line, each asked why and how two levels deep:

```
/five-ws --ask why,how --depth 2
1. Deploys keep failing on Friday afternoons
2. Login is slow after 9am
3. Nightly backups skip runs
```

| Question | Each answer is | Level 1 asks |
|----------|----------------|--------------|
| `why` | a cause | Why does this happen? |
| `what` | a fact or component | What exactly is happening, and what does it involve? |
| `when` | a time or condition | When does this happen, and under what conditions? |
| `where` | a place, system, stage or group | Where does this happen: in which places, systems, stages or groups? |
| `how` | a mechanism or step | How does this happen: by what mechanism or sequence of steps? |

Deeper levels ask the same question of each answer, such as "How does this
come about: <answer>?".

`--depth` sets the levels for every tree, from 1 to 5. A run's size is inputs ×
questions × answers per tree:

| Depth | Answers per tree | 1 input, all 5 questions | 10 inputs, 1 question |
|-------|------------------|--------------------------|-----------------------|
| 1 | 5 | 25 | 50 |
| 2 | 30 | 150 | 300 |
| 3 | 155 | 775 | 1,550 |
| 4 | 780 | 3,900 | 7,800 |
| 5 | 3,905 | 19,525 | 39,050 |

`--model-level` places the agents on a low-to-high continuum of models. Root
agents are few and write the top levels, so they step up first; branch agents
are many and write the deep levels:

| Level | Root agents | Branch agents |
|-------|-------------|---------------|
| 1 | haiku | haiku |
| 2 | sonnet | haiku |
| 3 | sonnet | sonnet |
| 4 | opus | sonnet |
| 5 | opus | opus |

Without it, agents run on the session's model. At depth 3 or less one agent
writes a whole tree, so only the root column applies.

Options go before the inputs; `--` ends them if an input itself starts with
dashes. The script parses them, so a typo is an error rather than part of an
input. Each line is one input, and list markers such as `- ` or `2. ` are
dropped. When it's unclear whether the text is one problem or several, the
skill shows the items it sees and asks which should get their own trees.

| Option | Effect | Why it exists |
|--------|--------|---------------|
| `--smoke` | 3 wide x 3 deep: 39 answers from 4 agents | Rehearse cheaply before paying for a full run |
| `--ask QUESTIONS` | Questions to ask, comma-separated (`why` by default) | Look at a problem from more than one angle |
| `--model-level N` | Model mix from 1 (all haiku) to 5 (all opus) | Trade cost against quality in one step; the quality effect is unmeasured |
| `--breadth N` | Answers per question | Size the tree to the problem |
| `--depth N` | Levels for every tree, 1 to 5 | Size the tree to the problem |
| `--split N` | Levels root agents write (default: sized so no agent writes more than 155 answers) | Balance fragment size against agent count for unusual shapes |
| `--max-parallel N` | Agents per wave, 5 by default, up to 20 | Choose between speed and machine load; smaller waves also let later branches see earlier ones |
| `--context-file PATH` | Put a file's text in every agent prompt | Give specifics without being asked for them |
| `--base DIR` | Write runs somewhere other than `.five-ws/` | Keep test runs apart from real ones |
| `--yes` | Skip the questions about inputs and context, and the cost confirmation | Unattended runs such as the eval |
| `--resume RUN_DIR` | Continue an interrupted run; add `--max-parallel N` to change the wave size | Recover without losing finished fragments |

If the inputs are thin, the skill asks once for specifics (the system, the
symptoms, what has been tried) and puts them in every agent prompt. Runs of
more than five agents show the inputs, questions, depth, answers, agents and an
estimate, and ask before dispatching.

Agents are packed so each writes at most 155 answers. At depths 1 and 2, one
agent covers several trees, and at depth 3 each tree gets one agent. Depth 4
takes 6 agents per tree and depth 5 takes 26.

### Test an unpublished checkout

Claude Code loads installed plugins from its cache. To run the skill and agent
text in a working copy instead, start a fresh session with
`claude --plugin-dir /path/to/five-ws`.

## What a full run costs

Cost depends first on the session that dispatches the agents. Each agent
inherits that session's context, such as its tools and MCP server instructions,
before it reads anything. Second is how much the agents read. Three runs of why
trees were measured on 2026-09-13 with claude-opus-5, read from Claude Code's
subagent logs with `docs/self-improvement/usage.py`:

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
context small. These figures are for one tree (one input, one question); more
inputs and questions multiply them, and the skill shows the total before
dispatching. Other questions and lower model levels haven't been measured.

Claude Code runs at most 20 subagents at once by default. This plugin sends
waves of 5 unless you choose otherwise, so a full single tree takes six waves.
When measuring a run, use a dedicated session so other work doesn't mix into
the totals.

## Output

Each run lives in `.five-ws/<timestamp>-<slug>/`:

| File | Contents |
|------|----------|
| `five-ws.json` | Every input, its trees and their answers, one answer per line |
| `index.md` | The settings used, each input's trees to level 2 with ids, and the Read windows for loading the whole file |
| `hygiene.json` | Mechanical flags, each with the texts involved: exact duplicates, near-duplicates, answers restating a parent or ancestor, cross-branch leads, over-long answers |
| `run.json` | Plugin version, options given, inputs, questions, shape, model level, estimate shown, dispatch attempts, each wave's start time and ids, duration, output size |
| `fragments/` | Raw agent output |
| `prompts/` | The full prompt each agent was dispatched with |
| `check-log.jsonl` | Every check an agent ran, with the kinds of errors and warnings, so repair cycles are countable |

`.five-ws/.gitignore` keeps runs out of git, since problem statements can be sensitive.

The layout, shown with answers from an earlier self-run:

```json
{"schema":"five-ws/1", ... ,"input_count":1,"questions":["why"], ... ,"inputs":[
{"id":"1","depth":0,"input":"The five-whys Claude Code plugin (v0.2.0) is rated 8/10 instead of 10/10.","trees":[
 {"id":"1.why","question":"why","answers":[
  {"id":"1.why.3","depth":1,"answer":"Hygiene flags rely on Jaccard word overlap, which misses paraphrases and deep cross-branch convergence.","answers":[
   {"id":"1.why.3.4","depth":2,"answer":"Branch agents in one wave run concurrently, so sibling-aware prompts cannot show reasons being written simultaneously elsewhere.","answers":[
```

- A tree's level-1 `answers` answer its question about the input. Every answer's
  `answers` answer the same question about it.
- `id` is the dotted path from the top: input number, question, then positions.
  `2.how.4.1` is the 1st answer under `2.how.4`, the 4th how-answer about input 2.
- The header records the plugin version, questions, shape, model level,
  per-level counts and average words, duration from creation to the last
  fragment, each wave's fragment count and seconds, any assumptions the agents
  stated, and whether the run is complete.

To load a run, ask Claude to read it. The skill reads `index.md`, then the
whole file in the windows `index.md` lists, which are sized in bytes to stay
under the Read tool's limit. `show --id <id>` prints a single input, tree or
branch with its ancestors.

## What validation covers

- **`check` (enforced):** every fragment is valid JSON with exactly the right
  number of answers at every level, and no answer over 30 words. Agents repair and re-check, at most 3 times.
  After `OK`, `check` also prints non-blocking warnings (repeated text,
  restatements, over-long answers). For a branch fragment it compares against
  its tree's real top answers, so restating an ancestor is caught before assembly.
- **`hygiene.json` (advisory):** word overlap on stemmed words, from the
  standard library. Near-duplicates need a similarity of 0.6. Pairs under
  different level-1 answers scoring 0.45 or more are listed as `cross_branch`
  leads, because one thing may be stated in two places; leads between inputs or
  questions are marked `across_inputs` and `across_questions`. Flags annotate;
  nothing is removed.
- **References (advisory):** file paths and commit hashes the answers cite are
  checked against the project the run was assembled in (`assemble --root`).
  Ones not found are listed under `references` in `hygiene.json`, with how many
  answers in each tree cite something concrete. In the first five-ws run,
  every cited path and commit existed, and the answers later found wrong cited
  nothing.
- **Measured on a real tree:** among 16 pairs from the v0.2.0 self-run that
  state the same cause twice, 7 score as leads and 9 use different words and
  are missed; 2 of 8 pairs that only share vocabulary are listed as leads.
  v0.2.0's scoring flagged none of the 16. Labeled pairs: `tests/fixtures/pairs.json`.
- **Not covered:** whether an answer is true, relevant or useful. That judgment
  is yours.

## Known limitations

- Answers are hypotheses written by a model, not verified facts. Checking them
  against evidence is part of your analysis.
- Hygiene sees shared wording only; paraphrases in different words go unflagged.
- Branches in the same wave can't see each other. Later waves see only the
  first-level answers of finished branches.
- One tree's agents never see another tree's answers. Something that answers
  two questions or two inputs appears in each; hygiene lists close wordings as
  `cross_branch` leads.
- Only why trees have been measured for cost and scored for quality. What,
  when, where and how are new, and so are model levels.
- Runs started by earlier versions (five-whys) can't be resumed or assembled,
  because their fragments are laid out differently. `show` still reads their
  finished trees.
- Deep levels drift toward generic answers. Agents are told to stay specific,
  name concrete things from their chain and state their assumptions, which
  reduces generic answers but doesn't prevent them.
- How much a cheaper model changes answer quality is unmeasured, and so is how
  much two runs of the same model differ.
- The eval cases have not been run yet.
- A full run spends a large share of subscription quota in a short burst.
- Agents are told to skip hidden folders and anything git ignores unless the
  input names it, because an earlier run read the session notes in `.remember/`.
  Like the network rule below, this is an instruction, not enforced.
- Agents are told not to run network commands such as `gh` or `curl`, but they
  have Bash, so nothing enforces it. In the v0.3.0 self-run, three of 25 branch
  agents ran `gh` before this instruction existed.

## Resuming, subsets and partial runs

- `/five-ws --resume <run-dir>` continues an interrupted run; `plan` skips
  fragments that already validate. A task that fails 3 dispatches is reported
  as stuck.
- `plan --only 1.why.2,2.how.4` dispatches selected branches.
- `assemble --partial` writes a valid file with missing trees and branches marked.

## Script

`scripts/fivews.py` (Python 3.9+, standard library only), with similarity
scoring in `scripts/hygiene.py`:

| Command | Does |
|---------|------|
| `parse` (arguments on stdin) | Split `/five-ws` arguments into questions, inputs, `init` flags and skill options, with errors for unknown or invalid options and hints when the split into inputs is unclear |
| `init` (inputs on stdin, one per line) | Create a run: `--preset`, `--ask`, `--model-level`, `--breadth`, `--depth` (1-5), `--split`, `--max-parallel`, `--context-file`, `--base`; prints the estimate and whether to confirm |
| `plan <run>` | Next wave of missing fragments with prompts and models; `--record` counts attempts; `--only` selects branches; `--max-parallel` changes the wave size |
| `status <run>` | Done, missing and stuck fragments, check cycles and error kinds per fragment, each wave's seconds, and the plugin version that created the run |
| `check <fragment> --breadth N --depth N` | Validate one fragment; warnings never block |
| `assemble <run>` | Write `five-ws.json`, `index.md`, `hygiene.json`; `--partial` allows missing trees and branches; `--root` sets the project cited references are checked against (default: the current directory) |
| `show <file-or-run>` | Print a subtree (`--id`), the top levels (`--levels`) or a random sample with ancestors (`--sample N --seed S`); reads five-whys files too |

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
- **Complete trees.** Every node gets exactly `breadth` answers down to `depth`;
  there is no early stopping or pruning.
- **One tree per question.** Each question stays coherent from top to bottom,
  and size grows in step with the number of questions instead of multiplying.
- **Script for control, agents for content.** The script parses the
  invocation, decides what runs and verifies it; agents only write fragments.

### Where your analysis begins

| Zone | For | Allowed | Not allowed |
|------|-----|---------|-------------|
| Run output: `five-ws.json`, `index.md`, `hygiene.json`, the skill's final reply | You | Answers verbatim, counts, mechanical flags, measurements | Ranking, summaries, selecting or pruning answers |
| Reading aids: this README, the skill's loading section, `show` | You | How to load and navigate a run, and a generic reading method | Examples that pick answers from a real run |
| Development measurement: `docs/self-improvement/` | The maintainer | Scored samples, audits, reviews by a model or a person | Writing a score into a run directory or anything a run shows you |

Scoring answers is how the maintainer measures whether a change made the plugin
better. It never happens inside a run.

## How this version was made

Each version comes from running the plugin on its own rating and accounting for
every one of the answers. Rounds 1-3 used why trees of 3,905 reasons.
`docs/self-improvement/` holds each round's tree, the catalog of dispositions
derived from it, the per-reason ledger, audits and a summary.

## License

MIT
