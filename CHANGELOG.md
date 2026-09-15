# Changelog

Codes such as IMP-37 refer to the self-improvement ledgers in
`docs/self-improvement/`. Evidence for each release gate goes here; see
[RELEASING.md](RELEASING.md).

## 0.3.0 — 2026-09-14

Changes derived from round 2, the v0.2.0 full run on its own 8/10 rating;
round 3, the full run of the round-2 checkout on its 7.4/10 rating
(`docs/self-improvement/round-3/design.md`); and the maintainer's requests of
2026-09-14.

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

From the goal run on 2026-09-14 (`docs/self-improvement/round-3/goal-2026-09-14.md`):

- Agent guidance says where-answers name where things happen rather than the
  files that describe them, what-answers name things, and how-answers lead
  with the action. On the same 8 inputs × 5 questions, where-answers citing a
  file fell from 47.5% to 2.5%, and hygiene leads from 8 to 1.
- `assemble` checks every file path and commit hash an answer cites against
  the project (`--root`) and lists the ones not found in `hygiene.json`, with
  a per-tree count of concrete answers.
- `check` rejects answers over 30 words. Haiku's how-answers had run to 34.
- Agents skip hidden and git-ignored folders unless the input names them,
  after one read the session notes in `.remember/`.

Requested by the maintainer on 2026-09-14, the question change:

- `/five-whys` asks why, or any combination of why, what, when, where and how,
  chosen with `--ask` (why by default) or with a leading phrase such as "ask
  how and where for:". Each input gets one tree per question, and every answer
  is asked the same question again down to `--depth`.
- `--model-level 1-5` sets a model mix from all haiku to all opus. Root agents
  step up first, at levels 2 and 4.
- Output is still `five-whys.json` in `.five-whys/`, now with schema
  `five-whys/4`: inputs hold one tree per question, nodes hold `answer` and
  `answers`, and ids carry the input and the question, as in `2.how.4.1`.
  Hygiene marks leads `across_questions` as well as `across_inputs`, and
  `show`, `usage.py`, `quality.py` and `ledger.py` read every earlier layout.
- The agent is `five-whys:expander`, with guidance for each question.
- A fourth eval case asks what and how at depth 1.
- On the branch, the plugin was briefly renamed five-ws. The maintainer kept
  the name five-whys before release, so the command, the install and the
  marketplace entry are unchanged.

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

Statuses as defined in RELEASING.md, run against 0c210bf, the last commit that
changes a skill, agent or script. It follows the goal run
(`docs/self-improvement/round-3/goal-2026-09-14.md`), the rename back to
five-whys (efac61e) and a label fix. Gates recorded on 07f6439 before the
rename back passed as well; their files stay under
`docs/self-improvement/round-3/gates/`.

- [passed] unit @07d016c 2026-09-14: 109 unit tests pass on the release commit, after the version bump, (Python 3.14 locally;
  CI covers 3.9 and 3.12).
- [passed] validate @07d016c 2026-09-14: `claude plugin validate .` passes on the release commit.
- [passed] model-run @0c210bf 2026-09-14: headless `claude -p --plugin-dir` in
  a fresh directory, claude-opus-5. `/five-whys --smoke --yes` on the
  nightly-backup problem ran `parse`, `init`, `plan`, `check`, `status` and
  `assemble` through the absolute script path, with agents labeled
  `five whys <task id>`. Results: 39 of 39 answers, 4 checks with 0 failures,
  0 hygiene flags, 0 unverified references and 13 stated assumptions. Waves
  took 20 and 46 seconds. The reply left analysis to the user. Files:
  `docs/self-improvement/round-3/gates/model-run-0c210bf/`.
- [passed] interactive @0c210bf 2026-09-14: without `--yes`, with the Agent
  tool blocked as a safeguard. "Deploys fail." got one question about the
  system, symptoms and attempts. A one-line numbered list got its three items
  back as a numbered question about which should get trees. Neither created a
  run. `--ask why,how` on the payments-deploy problem showed 51 agents, 7,810
  answers and the token range, said how runs are unmeasured, and asked
  before dispatching.
- [passed] quality-sample @0c210bf 2026-09-14: 22 answers from the model-run
  tree, drawn with `quality.py draw --stratify level --seed 7`, were scored by
  a fresh-context agent that saw only the packet and `quality-rubric.md`.
  Means: causal 1.68, specific 1.95, distinct 1.68 of 2. Two answers scored 0
  for restating their parent in other words: `1.why.1.2` and `1.why.2.2.2`.
  Level 3 is lowest, at causal 1.50. The 07f6439 sample scored distinct 1.82
  with no zeros. With 22 items, one scorer and no threshold yet, this is
  recorded, not judged. The implementing session's second scores of the
  round-3 baseline agree with the agent's on 79-97% of items; that session
  isn't independent. Files: `docs/self-improvement/round-3/quality/`.
- [passed] measured-branch @0c210bf 2026-09-14: headless `claude -p`, clean
  directory, the payments-deploy problem, root then `plan --only 1.why.1.1`.
  The root reported 12.3k tokens and the branch 27.8k, against 11.3k and
  23.6k at the estimate's low end: 8% and 18% above. The implied full run is
  0.71M, inside the 0.60M-1.62M range. The branch is past the 15% trigger for a
  full measurement, which the maintainer excused for 0.3.0 on 2026-09-13 (see
  Deferred). On 07f6439 the same agent text measured 8% and 6% above. Waves took
  62 and 251 seconds, and both fragments passed their first check. Files:
  `docs/self-improvement/round-3/gates/measured-branch-0c210bf/`.
- [passed] ledger-audit @4044694 2026-09-13: the independent, stratified audit
  of the round-2 ledger found 19 fit, 9 adjacent and 2 wrong, and both wrong
  codes were corrected. The implementing session's second review agrees on 27
  of 30 verdicts. The ledger and catalog haven't changed since, so the result
  is current.
- [blocked] eval @0c210bf 2026-09-14: the preflight finds 32 symbolic links
  under `~/.docker`, and the plugin-eval container has no saved token, so no
  eval ran. [waived] by the maintainer on 2026-09-14 for 0.3.0: the eval
  cases were covered by the model-run and interactive checks. The eval is
  required for the next release.

### Deferred

- The eval, waived for 0.3.0 and required for the next release. `plugin-eval`
  runs it in a container once a token is saved.
- A full measurement in the low-cost setting, excused for 0.3.0 by the
  maintainer on 2026-09-13. Two measured branches of identical agent text
  came in 6% and 18% above the low end, so the 15% trigger sits near run-to-run
  noise; repeated measurements should back it before the next release.
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
