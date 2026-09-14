# Self-improvement rubric

Version: 1

Each round's rating is graded against this rubric and committed as
`round-N/rating*.md` before the self-run starts, so the criteria are fixed
before the grader sees what the run produces. `tests/test_rubric.py` checks
the tables and every rating file.

## Criteria

Weights put the plugin's promise first: complete trees that run reliably and
hold reasons worth reading (15 each). Then come what makes a run trustworthy:
hygiene, cost, testing and release practice (10 each). Last are what shapes
future work (5 each).

| # | Criterion | Weight | Evidence it reads |
|---|-----------|--------|-------------------|
| 1 | Requirement fidelity | 15 | Tree headers of the latest full and smoke runs; each run's final reply |
| 2 | Orchestration reliability | 15 | `check-log.jsonl`, `run.json` attempts and waves, model-invoked and interactive run transcripts |
| 3 | Reason quality | 15 | `quality.py report` output for the latest scored samples |
| 4 | Hygiene | 10 | Labeled pair results (`tests/fixtures/pairs.json`), `hygiene.json` of the latest full run |
| 5 | Cost transparency | 10 | README cost section, `usage.py` output, wave timing in the latest full run |
| 6 | Testing | 10 | Unit test and CI results, eval results |
| 7 | Release process and docs | 10 | `RELEASING.md`, the CHANGELOG Evidence list, the marketplace entry |
| 8 | Maintainability | 5 | Docs consistency tests, module sizes, what the round added and removed |
| 9 | Self-improvement process | 5 | Round folders: ledger, audit verdict files, ratings |
| 10 | Readiness for other users | 5 | Marketplace entry, issues and reports from people other than the maintainer |

A score is a whole number from 0 to 10. Scores between anchors are allowed when
the evidence sits between them. The weighted total is the sum of score times
weight, divided by 100 and rounded to one decimal.

## Anchors

### 1. Requirement fidelity

- **4:** A full run of the code being rated left reasons missing, or a reply interpreted the tree.
- **6:** Smoke runs of the code being rated are complete, but no full run of that code exists.
- **8:** A full run of the code being rated is complete, and its reply leaves analysis to the user.
- **10:** Complete full runs on at least two problems, one of them non-software, with no interpretation in any reply.

### 2. Orchestration reliability

- **4:** A run needed hand repair of a fragment or of `run.json`.
- **6:** Runs complete, but a skill step was skipped or improvised, such as a relative script path or a fragment written by the orchestrator.
- **8:** Every documented scenario (smoke, thin problem, full-size confirmation, resume) followed the skill at least once, with nothing stuck.
- **10:** Every scenario followed the skill in at least two separate runs, and the eval passed.

### 3. Reason quality

- **4:** No scored sample exists, or any criterion's mean is below 1.0 of 2.
- **6:** One scorer's sample, with causal, specific and distinct means of at least 1.0.
- **8:** Two scorers, at least one independent, with every mean at least 1.5 and exact agreement of at least 60%.
- **10:** As 8, on both a software and a non-software problem, with no level's mean below 1.5.

### 4. Hygiene

- **4:** Only exact duplicates are caught.
- **6:** Word variants are caught, but fewer than half of the labeled convergent pairs are detected.
- **8:** At least half of the labeled convergent pairs are detected, at most 1 in 8 distinct pairs is listed, and the pairs come from more than one tree.
- **10:** At least 80% are detected, at most 1 in 8 distinct pairs is listed, and the pairs come from at least three trees labeled by someone other than the author.

### 5. Cost transparency

- **4:** The estimate is not based on a measured run.
- **6:** The estimate is a measured range, but the latest full run falls outside it or wall clock is unmeasured.
- **8:** The latest full run falls inside the range, and its per-wave timing is recorded.
- **10:** As 8, with measurements from at least two dispatch settings and two models.

### 6. Testing

- **4:** Unit tests miss a documented behavior.
- **6:** Unit tests cover every subcommand, but the eval has not run on the code being rated.
- **8:** The eval passed once on the code being rated.
- **10:** The eval passed on the code being rated on two machines or in CI.

### 7. Release process and docs

- **4:** Releases record no evidence.
- **6:** Evidence is recorded, but some is stale or a blocked gate has no decision.
- **8:** Every gate for the code being rated has a current `passed` or `waived` status.
- **10:** As 8, and that code is released with the marketplace entry matching.

### 8. Maintainability

- **4:** Changing one documented fact needs edits in several files that no test ties together.
- **6:** Docs tests tie the main facts to the code, but the script grows every round.
- **8:** Every documented number and option is pinned by a test, and each module has one job.
- **10:** As 8, and the round removed more code or options than it added.

### 9. Self-improvement process

- **4:** Not every reason of the round's tree is accounted for.
- **6:** Every reason is accounted for, but only its author audited the ledger.
- **8:** An independent reviewer audited a stratified sample, with the wrong-code rate and its interval recorded.
- **10:** As 8, with two reviewers agreeing on at least 80% of verdicts and the rating graded by two graders.

### 10. Readiness for other users

- **4:** Unreleased, or it fails to install from the marketplace.
- **6:** Released and installable, with no run by anyone else.
- **8:** One person other than the maintainer ran it, and their report is recorded.
- **10:** Several people ran it on their own problems, and their reports led to changes.

## Rating files

One file per grader, `round-N/rating.md` or `round-N/rating-<grader>.md`:

```
# Round N rating

Rubric version: 1
Grader: <who; model and what context they had>
Date: YYYY-MM-DD

| # | Criterion | Score | Evidence |
|---|-----------|-------|----------|
| 1 | Requirement fidelity | 8 | <what the score rests on> |
...

Weighted total: 7.4
```

Ratings written before this rubric start with `Pre-rubric:` and are not
comparable with rubric scores.

## Changes

Edit this file only between rounds: raise the version and add a line.

- 1 (2026-09-13): First version. Criteria and weights come from the round-3
  rating, and anchors were written before round 4's grading.
