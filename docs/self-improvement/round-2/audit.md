# Round-2 ledger audit

One reader classified this round, so the ledger was checked by sampling it with
`ledger.py round-2 sample 30 --seed S` and reading each sampled reason against
its ancestor chain, code and note.

## Sample 1 (seed 20260913), before the second pass

`audit-sample-before.txt`. The first ledger had 854 written lines; the other
3,051 reasons inherited a line from an ancestor up to three levels above.

| Result | Count | Ids |
|--------|-------|-----|
| Code and note fit | 24 | |
| Wrong code | 2 | 5.3.2.4.2 (IMP-44, should be X-HIST), 1.5.2.3.1 (R-18, should be IMP-34) |
| Right code, inherited note does not describe the reason | 2 | 5.4.4.3.1, 5.4.4.5.2 |
| Adjacent code, defensible either way | 2 | 2.5.4.4.5, 4.2.2.3.3 |

All four problems came from inheriting across more than one level. Fix: a
second pass gave every level-4 reason that inherited from level 1-3 its own
line (298 lines), so every reason now has its own line or inherits from its
direct parent. Both wrong codes were corrected.

## Sample 2 (seed 7), after the second pass

`audit-sample-after.txt`.

| Result | Count | Ids |
|--------|-------|-----|
| Code and note fit | 25 | |
| Wrong code | 3 | 3.5.1.1.5 (R-18, should be IMP-47), 5.4.5.2.1 (IMP-40, should be X-HIST), 5.2.4.2.4 (R-16, should be IMP-40) |
| Adjacent code or loosely fitting note | 2 | 4.3.1.2.2, 2.5.3.5.3 |

The three wrong codes were corrected with their own lines.

## What this says

- Across 60 sampled reasons, 5 carried a wrong code (about 8%), all corrected.
  Unsampled reasons likely carry errors at a similar rate; the notes make each
  choice checkable.
- The errors were leaves whose parent's code fit the parent but not the leaf,
  mostly where a leaf is history under an actionable parent or the reverse.
- The same model family wrote the tree and this ledger. Sampling catches
  misapplied codes, not shared blind spots.
