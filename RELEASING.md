# Releasing five-whys

A version is not bumped until every gate that applies below has a status that
allows it (see [Gate results](#gate-results)). Record each result in the
version's entry in [CHANGELOG.md](CHANGELOG.md).

## Every release

1. **Unit tests pass:** `python3 -m unittest discover tests`. This includes the
   orchestration replay test (synthetic fragments, so it checks orchestration
   only) and the labeled hygiene pairs.
2. **Manifest validates:** `claude plugin validate .`
3. **CHANGELOG.md** has an entry for the new version with its date, the
   changes (with ledger codes when they came from a self-run), removed options
   and one Evidence bullet per gate below, in the format under Gate results.
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
- **Eval.** Run it where Docker Desktop isn't installed, such as a second
  account or another machine. The eval refuses Bash-granting cases when
  `~/.docker` holds symbolic links, which Docker Desktop creates, and Docker
  configuration is not altered to get around that. Preflight:
  `find "${DOCKER_CONFIG:-$HOME/.docker}" -type l 2>/dev/null | head` must print
  nothing. Then run
  `claude plugin eval . --allow-tools Bash Write Edit --judge-model sonnet --runs 1 --ablation none`.
  `--ablation none` skips the no-plugin comparison arm, which can't pass and doubles the cost.
  Results may be published; record where the eval says they went.
  The cases and their pass criteria are in `evals/*/graders/criteria.md`; the
  eval passes when every case passes. With no such environment available,
  record it as `blocked`.

## Gate results

Every gate ends in one status:

| Status | Meaning | Allows the bump |
|--------|---------|-----------------|
| `passed` | Ran and met its pass condition | Yes |
| `failed` | Ran and missed it | Never; fix and run again |
| `blocked` | Could not run, for a reason outside the change | Only once waived |
| `waived` | The maintainer's written decision on a blocked gate | Yes |

Gate names: `unit`, `validate`, `model-run`, `interactive`, `eval`,
`measured-branch`, `full-run`, `ledger-audit`, `quality-sample`.

Each Evidence bullet names the status, the gate, the commit it ran against and
the date:

```
- [passed] model-run @3f2a1b0 2026-09-13: /five-whys --smoke --yes ... 39/39, 4 checks, 0 failed
- [blocked] eval @3f2a1b0 2026-09-13: refused, ~/.docker symlinks. [waived] by the maintainer: <reason>
```

A result is stale once a later commit changes the files it covers, and a stale
gate runs again. Until a tool does this, check by hand with
`git log --oneline <commit>..HEAD -- <paths>`:

| Gate | Covers |
|------|--------|
| `unit`, `validate` | `scripts/`, `tests/`, `skills/`, `agents/`, `.claude-plugin/` |
| `model-run`, `interactive` | `skills/`, `agents/`, `scripts/` |
| `eval` | `skills/`, `agents/`, `scripts/`, `evals/` |
| `measured-branch`, `full-run`, `quality-sample` | `agents/`, `scripts/fivewhys.py` |
| `ledger-audit` | The audited round's `ledger/` and `catalog.json` |
- **Measured single branch.** Create a full-shape run, dispatch the root and
  one branch with `plan <run> --only 1.1`, then run
  `python3 docs/self-improvement/usage.py <run>`. Compare the root's and the
  branch's reported totals with the low and high constants in
  `scripts/fivewhys.py`, using the end that matches the setting (a problem
  naming no files in a clean directory is low; a run inside a large repository
  whose files agents read is high). If they differ from that end by more than
  15%, run a full measurement in that setting.
- **Full measurement.** A full run in a dedicated session, then `usage.py`.
  It passes when the tree is complete, nothing got stuck and `check-log.jsonl`
  shows every fragment checked. Update `MEASURED` and the three token
  constants from the `fit` output, and the README cost table (the docs test
  checks they agree).
