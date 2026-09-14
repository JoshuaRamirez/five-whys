# Round 2: the v0.2.0 full run

On 2026-09-13 the plugin was rated 8/10 with seven written points of evidence
and run at full size on that rating: "The five-whys Claude Code plugin (v0.2.0)
is rated 8/10 instead of 10/10." The run produced 3,905 reasons. Every one is
accounted for here, and the unreleased changes in `CHANGELOG.md` came out of it.

| File | What it is |
|------|------------|
| `tree.json` | The run's `five-whys.json` (26 agents, 3,905 reasons) |
| `hygiene.json`, `check-log.jsonl` | That run's v0.2.0 hygiene output (0 flags) and check log (19 checks, 0 failures) |
| `hygiene-v0.3.json` | The same tree scored by the new hygiene: 3 near-duplicates, 11 cross-branch leads |
| `catalog.json` | Facts checked against the repository, precedence rules, improvements IMP-32 to IMP-53, declines R-11 to R-22 plus reused R codes, and X codes |
| `ledger/` | Rule fragments: `branch-N.txt` from the first pass, `branch-N-depth4.txt` from the second |
| `ledger.json` | One line per reason: id, code, note, `via` when inherited from the parent's line, and the reason text |
| `summary.md` | Reasons per code |
| `audit.md`, `audit-sample-*.txt` | Two sampled audits of the ledger and what they found |
| `verification.json` | Written in round 3: whether each improvement's effect was observed, blocked or never run (`ledger.py <round> verify`) |

## How it was done

1. **Read the whole tree.** One session read all 3,905 reasons and the 102
   stated assumptions. No subagents were used for reading, classifying or
   implementing, at the user's request.
2. **Checked the premises.** Facts in `catalog.json` were checked against the
   repository, the run directory and the subagent logs, for example per-agent
   token totals and whether `show --sample` already existed.
3. **Wrote the catalog** from the tree: 22 improvements, 11 new declines and 5
   reused ones, X codes, and rules for choosing between them (IMP beats R beats X;
   X notes cite the code that handles any actionable part).
4. **Classified every reason** with rule lines. A line covers its reason and
   any descendant without a line of its own. Notes allow up to 30 words
   (`max_note_words` in `catalog.json`; `ledger.py` defaults to 25).
5. **Audited by sampling.** The first 30-reason sample found that inheriting
   across several levels gave leaves notes that didn't describe them, and 2 wrong
   codes. A second pass gave all 298 affected level-4 reasons their own lines, so
   every reason now has its own line or inherits from its direct parent. A second
   sample found 3 more wrong codes. All 5 were fixed (`audit.md`).
6. **Committed the ledger before changing any code**, then implemented the
   improvements.

## Totals

| Disposition | Reasons |
|-------------|---------|
| Addressed by an improvement (IMP-32 to IMP-53) | 1,167 |
| Remedy declined or deferred, with the reason (R codes) | 565 |
| Already resolved (X-DONE) | 134 |
| Premise untrue or causal link does not hold (X-FALSE) | 14 |
| Outside the plugin's control (X-ENV) | 564 |
| Past motivation or process, nothing further to change (X-HIST) | 1,461 |
| **Total** | **3,905** |

1,172 reasons have their own line; 2,733 inherit their parent's. Two of the own
lines are corrections from round 3's independent audit (`audit.md`). Per-code
counts are in `summary.md`.

## Found outside the tree

Round 1 drew only on its tree. This round also reviewed the code, the docs and
this session's run for problems no reason named:

- **Reassembling stretched the duration.** `duration_seconds` was measured up
  to the moment of assembly, so assembling the v0.2.0 run again reported 5,692
  seconds instead of about 3,000. It now ends at the newest fragment.
- **A resumed run could not change its wave size.** Going to 5 at a time after
  the restart meant editing `run.json` by hand. `--resume RUN_DIR --max-parallel N`
  and `plan --max-parallel N` now do it.
- **Token usage was only in logs.** The estimate constants had been copied by
  hand. `usage.py` now reads the subagent logs and fits them. It also showed
  that 7 wave-1 agents (1.4, 2.2, 2.3, 3.2, 3.3, 3.4, 4.4) wrote valid
  fragments but were stopped by the restart before their check returned, so
  their totals are left out of the fit.
- **Hygiene flags had no text.** Every flag pointed at ids only; they now carry
  the texts involved.
- **Known Five Whys failure modes** were checked against the design. Complete
  trees counter single-cause bias. The agent rules forbid stopping at symptoms,
  and stated assumptions expose analyst dependence. Nothing verifies a reason
  against evidence, so the README now says reasons are hypotheses.

## Caveats

- One model family wrote the tree, the catalog, the ledger and the audit.
  Sampling catches misapplied codes, not blind spots the family shares.
- The author's samples found a wrong-code rate of about 8%. In round 3, an
  independent, stratified audit found 2 wrong codes in 30 (6.7%, 95% interval
  1.9%-21.3%) and 9 adjacent ones, concentrated on inherited leaves; both
  wrong codes were corrected. Unsampled reasons likely carry errors at a
  similar rate. Any line can be checked:
  `python3 docs/self-improvement/ledger.py docs/self-improvement/round-2 sample 5 --seed 1`.
- X-HIST grew relative to round 1. This tree explains how v0.2.0 was built in
  one afternoon, and most of those reasons describe that history.
- The changes are unreleased. Their skill and prompt gates need agent runs:
  a model-invoked run of the checkout, an interactive run, the eval, and a
  measured branch.
