# Self-improvement record

The plugin is improved by running it on its own rating and accounting for every
reason it produces. Each round lives in its own folder.

| Round | Input run | Rating | Result |
|-------|-----------|--------|--------|
| [round-1](round-1/README.md) | v0.1.0 on "rated only 6/10" | 6/10 | v0.2.0: 31 improvements |
| [round-2](round-2/README.md) | v0.2.0 full run on "rated 8/10" | 8/10 | v0.3.0 changes: 22 improvements, 2 options removed |
| [round-3](round-3/design.md) | v0.3.0 checkout full run on "rated 7.4/10" | 7.4 (no fixed rubric) | Design written; fixes not yet coded, no per-reason ledger |

Each round's rating is graded against [rubric.md](rubric.md), one file per
grader, committed before the self-run starts. Scoring happens here, in
development measurement, never inside a run (see the README's design
decisions).

Tools shared by the rounds:

| File | Does |
|------|------|
| `rubric.md` | Criteria, weights, anchors and the rating file format |
| `ledger.py <round> check <fragment>` | Validate one ledger fragment (per-reason JSON or rule lines) |
| `ledger.py <round> merge` | Prove every reason in the round's tree has exactly one disposition; write `ledger.json` and `summary.md` |
| `ledger.py <round> sample N --seed S [--via own\|inherited] [--level L] [--stratify] [--json]` | Print random ledger entries with their ancestor chain, code and note; `--stratify` draws equally per level and own or inherited line, `--json` prints a reviewer packet |
| `ledger.py <round> audit VERDICTS [VERDICTS]` | Validate reviewer verdict files and report wrong-code rates with a 95% interval per group; two files add agreement |
| `ledger.py <round> verify` | Report which of the round's improvements were observed working, blocked or never run, from `verification.json` |
| `reviewer-prompt.md` | What an independent ledger reviewer receives, and the verdict file format |
| `quality.py draw\|score\|report` | Draw a shuffled packet of reasons without ids, validate a scorer's file, and report means per criterion and level, with agreement between two scorers |
| `quality-rubric.md` | Anchors for scoring a reason 0-2 as causal, specific and distinct, and the score file format |
| `usage.py <run-dir> [--out FILE]` | Read Claude Code's subagent logs for a run, report each agent's first-turn context and fit the estimate constants; `--out` keeps the JSON with the round |
