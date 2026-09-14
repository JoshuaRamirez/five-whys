# Releasing five-whys

A version is not bumped until every gate that applies below holds. Record the
evidence in the version's entry in [CHANGELOG.md](CHANGELOG.md).

## Every release

1. **Unit tests pass:** `python3 -m unittest discover tests`. This includes the
   orchestration replay test and the labeled hygiene pairs.
2. **Manifest validates:** `claude plugin validate .`
3. **CHANGELOG.md** has an entry for the new version with its date, the
   changes (with ledger codes when they came from a self-run), removed options
   and the evidence for each gate below.
4. **Options:** the option count in `tests/test_docs.py` still matches, and
   every option in the README table still has a reason to exist. Say in the
   changelog if one was added or removed.
5. **Known limitations** in the README were reread; close, keep or add.
6. **Version matches** in `.claude-plugin/plugin.json` and the RedJay
   marketplace entry.

## By kind of change

| Change | Required before the bump |
|--------|--------------------------|
| Wording or docs only | Every-release gates |
| `SKILL.md` steps, `parse`, confirmation or the wave loop | A model-invoked run of the checkout (below), plus one interactive run without `--yes` when Steps 1 or 3 changed: a thin problem must get the question, and a full-size run must ask before dispatching |
| Agent instructions or prompt text | A model-invoked smoke run whose tree was read with `show --sample 20`, and a measured single branch (below) |
| Dispatch, waves or estimate constants | A measured single branch, or a full run when wave logic changed |
| `evals/` or this file | Run the eval |
| A release derived from a self-run | Review `ledger.py <round> sample 30` and record wrong codes in the round's `audit.md` |

## How to run each check

- **Model-invoked run of the checkout.** In a fresh session, load the working
  copy instead of the marketplace install, so new skill and agent text is what
  runs: `claude --plugin-dir .`, then `/five-whys --smoke --yes <any problem>`.
  It passes when `parse` and `init` ran from the checkout, 39/39 reasons
  assemble, `index.md` and `hygiene.json` exist, and the reply leaves analysis
  to the user. Record the run directory.
- **Eval.** `claude plugin eval . --allow-tools Bash Write Edit --judge-model sonnet --runs 1`.
  The cases and their pass criteria are in `evals/*/graders/criteria.md`; the
  eval passes when every case passes. Record the date and result.
- **Measured single branch.** Create a full-shape run, dispatch the root and
  one branch with `plan <run> --only 1.1`, then run
  `python3 docs/self-improvement/usage.py <run>`. Compare the branch's reported
  total and output tokens with the constants in `scripts/fivewhys.py`. If they
  differ by more than 15%, run a full measurement.
- **Full measurement.** A full run in a dedicated session, then `usage.py`.
  It passes when the tree is complete, nothing got stuck and `check-log.jsonl`
  shows every fragment checked. Update `MEASURED` and the three token
  constants from the `fit` output, and the README cost table (the docs test
  checks they agree).
