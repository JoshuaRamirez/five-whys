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

## Independent audit (round 3, seed 11, stratified)

Samples 1 and 2 were drawn uniformly and read by the ledger's author. In round
3, a fresh-context Claude agent audited a sample drawn with
`sample 30 --stratify --seed 11 --json`. The draw took equal shares per level
and per own or inherited line. The agent saw only `audit/packet.json`,
`reviewer-prompt.md` and the plugin's code, not the ledger files or the
session. Its verdicts are in `audit/agent-fresh-context.json`, and the report
it produced is `audit/report-agent.json`, taken before the corrections below.
The maintainer's review of the same packet is still to come.

| Group | Sampled | Fit | Adjacent | Wrong |
|-------|---------|-----|----------|-------|
| Level 1, own line | 5 | 3 | 2 | 0 |
| Level 2, own line | 5 | 5 | 0 | 0 |
| Level 3, inherited | 4 | 3 | 1 | 0 |
| Level 3, own line | 4 | 3 | 1 | 0 |
| Level 4, own line | 4 | 2 | 2 | 0 |
| Level 5, inherited | 4 | 0 | 2 | 2 |
| Level 5, own line | 4 | 3 | 1 | 0 |
| **Total** | **30** | **19** | **9** | **2** |

The wrong-code rate is 2 of 30 (6.7%), with a 95% interval of 1.9%-21.3%, in
line with the author's 8%. Adjacent verdicts, 9 of 30, are far more common
than the author's samples found (4 of 60). Both wrong codes, and 3 of the 9
adjacent ones, sit on reasons that inherited their parent's line. None of the
4 inherited level-5 leaves fit cleanly, which confirms that inherited leaves
are where the ledger is weakest.

Both wrong codes were checked against the catalog and corrected with their own
lines in `ledger/zz-audit-round-3.txt`:

- **5.5.4.1.3:** IMP-52 became IMP-41. The reason is about hand-kept option
  tables, which the options docs test covers, not the hygiene module split.
- **5.4.2.4.5:** X-ENV became R-17. Treating the tree as the finished product
  is the plugin's choice, which the telemetry decline covers.

The adjacent verdicts are left unchanged. The reviewer gave each one a
defensible alternative, and none moves a reason between addressed and
declined. One points to a factual error in a note: 2.3.3.5.4 says the eval
reruns every release, but RELEASING.md runs it only when its covered files
change. The next catalog should cite R-13 for the part in scope and X-ENV for
platform drift without commits.
