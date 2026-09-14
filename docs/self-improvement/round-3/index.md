# Five Whys index

Problem: The five-whys Claude Code plugin (unreleased v0.3.0 on branch improve/v0.3.0) is rated 7.4/10 instead of 10/10.

Settings: 5 wide x 5 deep, root writes 2 level(s), model inherit, waves of 5, plugin 0.2.0.

Levels 1-2 of 5. Each level-2 reason heads a branch of 155 deeper reasons. Print one branch with:

```
python3 /Users/joshua/Developer/Plugins/ClaudeCodeCLI/FiveWhys/scripts/fivewhys.py show /Users/joshua/Developer/Plugins/ClaudeCodeCLI/FiveWhys/.five-whys/20260913-192317-the-five-whys-claude-code-plugin-unrelea --id <id>
```

- 1 No full run of the v0.3.0 code has happened, and each live scenario was exercised only once.
  - 1.1 A full 3,905-reason run costs 0.60M-1.62M agent tokens, so the session verified with a 39-reason smoke run instead.
  - 1.2 Round 2 spent its effort classifying all 3,905 v0.2.0 reasons against the catalog, leaving little budget for live verification.
  - 1.3 No clean-directory harness exists, so every live run is launched by hand via claude --plugin-dir, discouraging repeats.
  - 1.4 run.json stores no wave timestamps, so a timed run needs separate instrumentation nobody has built yet.
  - 1.5 RELEASING.md accepts a measured single branch for most dispatch changes, so a full run was never strictly forced.
- 2 The eval never ran because claude plugin eval refuses Bash-granting cases on this machine.
  - 2.1 Symlinks in ~/.docker/cli-plugins trip the eval's safety check whenever a case grants the Bash tool.
  - 2.2 Every eval case must grant Bash because the skill calls scripts/fivewhys.py for parse, init and check.
  - 2.3 No CI job or second machine runs the eval, so one local environment fault blocks it entirely.
  - 2.4 The ~/.docker configuration lies outside the repository, so the session left it untouched rather than repairing it.
  - 2.5 The eval gate only applies to evals/ changes, so skill changes could proceed without waiting for it.
- 3 Reason quality and hygiene are judged only by a self-read sample and lexical matching.
  - 3.1 No rubric scores causality, specificity or distinctness, so a 20-reason read yields no comparable number.
  - 3.2 The no-dependencies rule limits hygiene.py to stdlib stemming, excluding embedding-based paraphrase detection.
  - 3.3 The labeled fixture holds only 24 pairs from one tree, too few to tune or trust detection thresholds.
  - 3.4 The non-software eval case never ran, so quality was only read on software-shaped problems.
  - 3.5 Leaving analysis to the user bars the plugin from judging its own reasons, so no quality signal is generated per run.
- 4 Version 0.3.0 is unreleased and no one outside the author has run the plugin.
  - 4.1 The manifest and RedJay marketplace entry stay at 0.2.0 until every RELEASING.md gate, including the eval, passes.
  - 4.2 Round 2 added per-change-kind gates, multiplying the checks a release must clear before the version bump.
  - 4.3 No feedback channel collects reports from marketplace installs, so any outside use of 0.2.0 stays invisible.
  - 4.4 The output is an unanalyzed 3,905-reason tree, a heavy first artifact for a newcomer deciding whether to adopt.
  - 4.5 Outreach to a first outside user was deferred until round 2 improvements shipped.
- 5 One Claude session wrote the code, the ledger, the audit, the gates and the 7.4 grade itself.
  - 5.1 Round 2 ran in one session without subagents, so no separate context challenged its classifications or code.
  - 5.2 The maintainer works alone, so no second human reviews the rubric, the evidence or the gate results.
  - 5.3 The rubric weights and scores were chosen by the grader, so criteria were never fixed before the evidence.
  - 5.4 2,735 reasons inherit their parent's disposition line, so the ledger echoes top-level judgments instead of independent checks.
  - 5.5 Dispatch only reaches Claude models, so bringing in a second model family requires tooling outside the plugin.

## Reading five-whys.json whole

Read these 13 windows in order; each stays under the Read tool's size limit:

- offset 1, limit 233
- offset 234, limit 386
- offset 620, limit 389
- offset 1009, limit 390
- offset 1399, limit 380
- offset 1779, limit 377
- offset 2156, limit 388
- offset 2544, limit 382
- offset 2926, limit 377
- offset 3303, limit 380
- offset 3683, limit 373
- offset 4056, limit 377
- offset 4433, limit 255
