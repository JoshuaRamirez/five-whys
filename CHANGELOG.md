# Changelog

Codes such as IMP-37 refer to the self-improvement ledgers in
`docs/self-improvement/`. Evidence for each release gate goes here; see
[RELEASING.md](RELEASING.md).

## Unreleased

Changes derived from round 2, the v0.2.0 full run on its own 8/10 rating, and
round 3, the full run of this checkout on its 7.4/10 rating
(`docs/self-improvement/round-3/design.md`). The version stays 0.2.0 until
every gate has a status that allows the bump (see Evidence).

### Changed

- `/five-whys` arguments are parsed by `fivewhys.py parse` instead of by the
  model reading a table; unknown or invalid options are errors, and `--` ends
  the options (IMP-37).
- `init` returns `confirm`, so the more-than-5-agents rule lives in code (IMP-38).
- Waves default to 5 agents instead of 20 (IMP-43). A resumed run can change
  its wave size with `--resume RUN_DIR --max-parallel N` or `plan --max-parallel N`.
- Branch prompts in later waves list the first-level reasons of branches that
  already finished (IMP-42).
- Hygiene stems words, lists `cross_branch` leads at 0.45 between different
  level-1 branches, includes the texts in every flag and reports its filters
  (IMP-45). It moved to `scripts/hygiene.py` (IMP-52). `exact_duplicates`
  entries are now objects with `ids` and `text`.
- `check` compares a branch fragment against the root's real reasons (IMP-46).
- `run.json` records the plugin version, the options given and the estimate
  shown; `index.md` opens with the settings and ends with byte-sized Read
  windows (IMP-33, IMP-39, IMP-48).
- `duration_seconds` runs from creation to the newest fragment, so assembling
  again no longer stretches it (found outside the tree).
- The estimate is a range from two measured runs (IMP-32). The high end
  (`agent_tokens`: 39.6k per agent plus 152 per reason) comes from the v0.2.0
  full run inside this repository. The low end (`agent_tokens_low`: 8.4k plus
  98 per reason) comes from a root and one branch on a problem naming no files.
  Output stays at 38 tokens per reason.
- Agent instructions cover non-software problems, problems with nothing to read,
  and leaves that must stay concrete (IMP-49).
- A replay test walks the skill's dispatch loop with synthetic fragments the
  test writes itself (not recorded agent output), and a labeled pair fixture
  from the v0.2.0 tree measures hygiene (IMP-44, IMP-47).
- A second eval case runs a one-line non-software problem (IMP-50).
- RELEASING.md gates releases by kind of change and documents
  `claude --plugin-dir .` and `usage.py` (IMP-35, IMP-36).

Requested by the maintainer on 2026-09-14, the product change:

- The plugin is now **five-ws**. `/five-ws` asks any combination of why, what,
  when, where and how, chosen with `--ask` (why by default) or with a leading
  phrase such as "ask how and where for:". Each input gets one tree per
  question, and every answer is asked the same question again down to `--depth`.
- `/five-whys` stays as a shortcut for `/five-ws --ask why`.
- `--model-level 1-5` sets a model mix from all haiku to all opus. Root agents
  step up first, at levels 2 and 4.
- Output is `five-ws.json` (schema `five-ws/1`) in `.five-ws/`. Nodes hold
  `answer` and `answers`, and ids carry the input and the question, as in
  `2.how.4.1`. Hygiene marks leads `across_questions` as well as
  `across_inputs`, and `show`, `usage.py`, `quality.py` and `ledger.py` read
  both five-ws and five-whys files.
- The agent is `five-ws:expander`, with guidance for each question, and the
  script is `scripts/fivews.py`.
- A fourth eval case asks what and how at depth 1. The first two cases run
  through `/five-whys`, and the input-list case through `/five-ws`.
- The rename changes the RedJay marketplace entry, so existing five-whys
  installs need `/plugin install five-ws@RedJay`.

Requested by the maintainer earlier on 2026-09-14:

- `--depth` accepts 1 to 5.
- A run takes a list of inputs, one per line, with list markers removed.
  Each input gets its own tree to the chosen depth, and all of them assemble
  into one `five-whys.json` (schema `five-whys/3`). Inputs sit at the top, and
  ids start with the input number. When the split into inputs is unclear,
  `parse` returns `input_hints` and the skill asks which items to use.
- Root agents take groups of inputs, and the default split keeps every agent at
  155 reasons or fewer. Depths 1-3 need at most one agent per input, and depth
  4 drops from 26 agents per input to 6. Depth 5 keeps its 26.
- Hygiene marks leads between inputs as `across_inputs`. `usage.py`,
  `quality.py` and `ledger.py` read trees with inputs.
- A third eval case runs a three-item list at depth 1.
- Runs started by earlier versions can't be resumed or assembled; `show`
  still reads their trees.

From round 3 (sections of `docs/self-improvement/round-3/design.md`):

- `parse` prints the script's absolute path, and the skill uses it for every
  later step (5f).
- Agents are told not to run network commands; nothing enforces it (5e).
- `plan --record` stores each wave's start time and ids. `status`, the tree
  header and `index.md` report each wave's seconds (5a).
- `check-log.jsonl` names the kinds of errors and warnings, and `status` sums
  them per fragment (5b).
- The README says where your analysis begins: run output and reading aids
  never judge reasons, while development measurement may score them (Fix 2).
- Every release gate ends `passed`, `failed`, `blocked` or `waived`, with the
  commit it ran against, and a docs test enforces the format. The eval runs
  where Docker Desktop isn't installed, and its results may be published (4a,
  Fix 1).
- The cost section says base cost follows the dispatching session's context,
  and adds the v0.3.0 full run (5c).
- The replay test is described as synthetic fragments, not recorded agent
  output (5g).
- Maintainer tooling in `docs/self-improvement/`:
  - `rubric.md` fixes rating criteria, weights and anchors (3a).
  - `ledger.py sample` gains `--via`, `--level`, `--stratify` and `--json`.
  - `ledger.py audit` reads reviewer verdict files, and `reviewer-prompt.md`
    tells reviewers how to write them (3b).
  - `quality.py` and `quality-rubric.md` score reason samples (3c).
  - `ledger.py verify` and round 2's `verification.json` record whether each
    improvement was observed working (4c).
  - Deferred dispositions need a trigger in schema-3 catalogs (4d).
  - `usage.py --out` reports first-turn context (5c).

### Removed

- `--model NAME`, replaced by `--model-level 1-5` (2026-09-14).
- `init --root-model` and `--branch-model` (IMP-40). They were unmeasured and
  unreachable from `/five-whys`. Runs created by v0.2.0 with separate tiers
  still plan with them.

### Measurements

- Reassembling the v0.2.0 run with the new hygiene: 3 near-duplicates and 11
  cross-branch leads, where v0.2.0 reported 0 flags.
- Labeled pairs: 7 of 16 convergent pairs detected, 2 of 8 distinct pairs listed.

### Evidence

Statuses as defined in RELEASING.md, run against 5ee0915. The depth and
input-list change came later and touches the files every gate covers, so
these results are stale. Every gate runs again before release.

- [passed] unit @5ee0915 2026-09-13: 84 unit tests pass, including the replay,
  labeled-pair, rubric, ledger, quality and usage tests (Python 3.14 locally;
  CI covers 3.9 and 3.12).
- [passed] validate @5ee0915 2026-09-13: `claude plugin validate .` passes.
- [passed] model-run @5ee0915 2026-09-13: headless `claude -p --plugin-dir`
  in a fresh directory, claude-opus-5. `/five-whys --smoke --yes` on the
  nightly-backup problem ran `parse`, `init`, `plan`, `status` and `assemble`
  through the absolute script path. 39 of 39 reasons assembled, and all 4
  fragments passed their first check. There were 14 stated assumptions and 0
  hygiene flags. Waves took 69 and 90 seconds, 210 seconds in total. The 4
  agents ran 4 Bash commands, all checks, and none touched the network. The
  reply left analysis to the user. Output and transcript:
  `docs/self-improvement/round-3/gates/model-run-5ee0915/`.
- [passed] quality-sample @5ee0915 2026-09-13: 22 reasons from the model-run
  tree, drawn with `quality.py draw --stratify level --seed 7`, were scored by
  a fresh-context agent that saw only the packet and `quality-rubric.md`.
  Means: causal 1.68, specific 1.95, distinct 1.82 of 2. Only one item scored
  0: it restated its parent. The round-3 baseline (29 reasons from the 5x5 tree
  written before these fixes, same scorer setup) had causal 1.72, specific
  2.00 and distinct 1.69. On the levels both trees have, the changes run in
  both directions: level 2 causal 1.50 to 1.56 and distinct 1.83 to 1.67;
  level 3 causal 2.00 to 1.70 and distinct 1.83 to 1.90. With 3-10 items per
  level, different problems and one scorer, this shows no measurable
  regression, and no improvement either. The maintainer's scores of both
  packets are pending. Files are in `docs/self-improvement/round-3/quality/`.
- [passed] interactive @5ee0915 2026-09-13: headless `claude -p --plugin-dir`
  in fresh directories, without `--yes`, with the Agent tool blocked as a
  safeguard. "Deploys fail." got one question about the system, the symptoms and
  what has been tried, and no run was created. The payments-deploy problem ran
  `parse` and `init` through the absolute script path. It showed 26 agents,
  3,905 reasons and 601k-1.62M agent tokens, asked before dispatching, and
  dispatched nothing.
- [passed] measured-branch @7c8cd8f 2026-09-13: the covered files are identical
  to 5ee0915. Headless `claude -p` in a clean directory, on the payments-deploy
  problem, ran `plan --only 1.1`. The root reported 8.8k tokens and branch 1.1
  reported 22.1k, against 11.3k and 23.6k at the estimate's low end: 22% and 6%
  below. The implied full run is about 0.56M, 7% below the 0.60M low end.
  First-turn context was 4.7k tokens, and the branch wrote 14.3k output tokens.
  Waves took 73 and 224 seconds, and both fragments passed their first check.
  RELEASING.md calls for a full measurement when either total is more than 15%
  off, and the root is. The maintainer deferred that run for this version as a
  one-time exception (2026-09-13); the rule is unchanged. Files:
  `docs/self-improvement/round-3/gates/measured-branch-5ee0915/`.
- [blocked] eval @5ee0915 2026-09-13: the only machine available has Docker
  Desktop. The RELEASING.md preflight found 32 symbolic links under
  `~/.docker`, which `claude plugin eval` refuses for Bash-granting cases; at
  91b5637 both cases recorded 0 turns for that reason. Docker configuration was
  not altered. Not waived: it needs a machine or account without Docker
  Desktop, or the maintainer's written waiver.

### Deferred

- A full measurement in the low-cost setting. The measured root came in 22%
  below the estimate's low end, past RELEASING.md's 15% trigger, while the
  implied full run was 7% below. The maintainer made a one-time exception for
  this version; the rule stands for the next.
- Release of 0.3.0 is on hold until the eval runs on a machine without Docker
  Desktop and the maintainer has reviewed the audit and quality packets.
- Model-tier quality and same-model variance (R-18).
- A multi-domain benchmark of problems (R-18).
- Grader reliability for the eval cases (R-18).
- Evals in CI (R-13).

## 0.2.0 — 2026-09-13

Derived from round 1, the v0.1.0 run on its own 6/10 rating: configurable
shape and a smoke preset, capped waves, attempt tracking, model choice, cost
estimates with confirmation, hygiene flags, sibling-aware prompts, rewritten
agent instructions, prompt files, `status`, `show`, partial assembly, a check
log, unit tests with CI, an eval case and a release checklist (IMP-01 to IMP-31).

Evidence: 35 unit tests; `claude plugin validate .`; a hand-driven smoke run
assembling 39 of 39 reasons with 0 failed checks. After release, a full run on
the same day completed 3,905 of 3,905 reasons and became round 2's input.

## 0.1.0 — 2026-09-13

First release: a skill, a why-expander agent and a script that generate and
assemble a complete 5x5x5x5x5 tree.
