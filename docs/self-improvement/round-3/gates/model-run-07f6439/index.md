# Five Ws index

1 input × 1 question (why), each asked 3 level(s) deep with 3 answers per question: 39 answers.

Settings: 3 wide x 3 deep, root writes 1 level(s), models inherit, waves of 5 (2 dispatched, 1 min), plugin 0.2.0.

Levels 1-1 of 3 are listed. Print an input, a tree or an answer with everything beneath it:

```
python3 /Users/joshua/Developer/Plugins/ClaudeCodeCLI/FiveWhys/scripts/fivews.py show /private/tmp/g4-model.QCFSxm/.five-ws/20260914-182646-our-nightly-database-backup-job-silently --id <id>
```

- 1 [input] Our nightly database backup job silently skips some runs, and nobody notices until a restore is needed.
  - 1.why [why]
    - 1.why.1 The wrapper script exits 0 on a stale lock file or missed cron window, so skipped runs look like successes.
    - 1.why.2 Alerting fires only on errors the job emits, so a run that never starts sends no signal and no expected-heartbeat check exists.
    - 1.why.3 No one owns scheduled restore drills, so backup files are never opened or counted until an actual outage forces a restore.

## Reading five-ws.json whole

Read these 1 windows in order; each stays under the Read tool's size limit:

- offset 1, limit 57
