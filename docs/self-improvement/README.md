# Self-improvement record

The plugin is improved by running it on its own rating and accounting for every
reason it produces. Each round lives in its own folder.

| Round | Input run | Rating | Result |
|-------|-----------|--------|--------|
| [round-1](round-1/README.md) | v0.1.0 on "rated only 6/10" | 6/10 | v0.2.0: 31 improvements |
| [round-2](round-2/README.md) | v0.2.0 full run on "rated 8/10" | 8/10 | v0.3.0 changes: 22 improvements, 2 options removed |

Tools shared by the rounds:

| File | Does |
|------|------|
| `ledger.py <round> check <fragment>` | Validate one ledger fragment (per-reason JSON or rule lines) |
| `ledger.py <round> merge` | Prove every reason in the round's tree has exactly one disposition; write `ledger.json` and `summary.md` |
| `ledger.py <round> sample N --seed S` | Print random ledger entries with their ancestor chain, code and note, for audits |
| `usage.py <run-dir>` | Read Claude Code's subagent logs for a run and fit the estimate constants |
