# Changelog

Codes such as IMP-37 refer to the self-improvement ledgers in
`docs/self-improvement/`. Evidence for each release gate goes here; see
[RELEASING.md](RELEASING.md).

## Unreleased

Changes derived from round 2, the v0.2.0 full run on its own 8/10 rating. The
version stays 0.2.0 until the gates that need model runs have passed (see
Evidence).

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
- A replay test walks the skill's dispatch loop with stand-in agents, and a
  labeled pair fixture from the v0.2.0 tree measures hygiene (IMP-44, IMP-47).
- A second eval case runs a one-line non-software problem (IMP-50).
- RELEASING.md gates releases by kind of change and documents
  `claude --plugin-dir .` and `usage.py` (IMP-35, IMP-36).

### Removed

- `init --root-model` and `--branch-model` (IMP-40). They were unmeasured and
  unreachable from `/five-whys`. Runs created by v0.2.0 with separate tiers
  still plan with them.

### Evidence

- 61 unit tests pass, including the replay and labeled-pair tests, and
  `claude plugin validate .` passes (2026-09-13, Python 3.14 locally; CI covers 3.9 and 3.12).
- Reassembling the v0.2.0 run with the new hygiene: 3 near-duplicates and 11
  cross-branch leads, where v0.2.0 reported 0 flags.
- Labeled pairs: 7 of 16 convergent pairs detected, 2 of 8 distinct pairs listed.
- Model-invoked run of the checkout (2026-09-13, headless `claude -p --plugin-dir .`,
  claude-opus-5): `/five-whys --smoke --yes` on the nightly-backup problem ran
  `parse`, `init`, two waves and `assemble` from the checkout. 39 of 39 reasons,
  complete, 4 checks with 0 failures, 11 stated assumptions, 0 hygiene flags,
  58 seconds from creation to the last fragment. The orchestrator wrote no
  fragments; branches 2 and 3 removed empty `whys` lists from their own leaves.
  A 20-reason `show --sample` read found concrete mechanisms such as
  `flock -n ... || exit 0` and debug-level skip logging. The reply left analysis
  to the user.
- Interactive checks without `--yes`, with the Agent tool blocked as a safeguard:
  "Deploys fail." got one question about system, symptoms and attempts, and no
  run was created. A specific full-size problem ran `parse` and `init`, showed
  26 agents, 3,905 reasons and about 1.62M agent tokens, asked before
  dispatching, and dispatched nothing.
- Measured single branch (2026-09-13, headless, clean directory, the
  payments-deploy problem): root 11.3k and branch 1.1 23.6k reported tokens,
  63-74% below the v0.2.0 constants; branch output 14.9k tokens, inside
  v0.2.0's range. First-turn context was 4.6k tokens against 20.9k in the
  repository session, with no evidence reading and 5 turns instead of 12, so
  the gap comes from the setting, not the new prompts. The estimate became a
  range instead of a full remeasurement.
- Eval: blocked on this machine. `claude plugin eval` refuses Bash-granting
  cases because `~/.docker/cli-plugins` holds symbolic links (created by Docker
  Desktop). Both cases recorded 0 turns.

### Deferred

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
