# Self-improvement record

On 2026-09-13 the plugin was run on its own rating: "The five-whys Claude Code
plugin (v0.1.0) is rated only 6/10 instead of 10/10." It produced 3,905
reasons. Every one of them is accounted for here, and version 0.2.0 is what
came out of it.

| File | What it is |
|------|------------|
| `tree.json` | The run on the plugin's own rating (26 agents, 3,905 reasons) |
| `catalog.json` | Improvements (IMP), declined remedies (R) and non-actionable dispositions (X) derived from reading the whole tree |
| `ledger/` | 26 fragments written by classification agents, one per scope |
| `ledger.json` | One line per reason: id, disposition code, a note explaining the choice, and the reason text |
| `summary.md` | Reasons per code |
| `ledger.py` | `check` validates a fragment against its scope; `merge` proves every reason is covered exactly once |

## How it was done

1. The whole tree was read, and `catalog.json` was written from it: IMP-01 to
   IMP-19, R-01 to R-07, and the X codes.
2. 26 agents classified every reason in their scope against the catalog.
   `ledger.py check` required exactly one valid code and a note for each.
3. 28 reasons came back NEW (actionable but not in the catalog). Each was
   reconciled: 18 map to new improvements IMP-20 to IMP-31, 8 to new declines
   R-08 to R-10, and 2 to existing codes.
4. `ledger.py merge` confirmed 3,905 of 3,905 reasons covered once, with no NEW
   entries left.

## Totals

| Disposition | Reasons |
|-------------|---------|
| Addressed by an improvement (IMP-01 to IMP-31) | 1,786 |
| Remedy declined or deferred, with the reason (R-01 to R-10) | 549 |
| Already resolved (X-DONE) | 155 |
| Premise untrue of the plugin (X-FALSE) | 117 |
| Outside the plugin's control (X-ENV) | 616 |
| Past motivation or process, nothing further to change (X-HIST) | 682 |
| **Total** | **3,905** |

Per-code counts are in `summary.md`.

## Caveats

- Classification is agent judgment against the catalog. Notes explain every
  choice, so any line can be checked: `grep '"id":"3.4.2.1"' ledger.json`.
- X-FALSE mostly marks premises the tree got wrong about v0.1.0, for example
  that it had no git repository or that `plan` couldn't resume.
- An X-HIST or X-ENV reason may be accurate; it just implies no further change
  to the plugin.
