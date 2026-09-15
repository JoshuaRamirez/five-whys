# Five Whys index

1 input × 1 question (why), each asked 3 level(s) deep with 3 answers per question: 39 answers.

Settings: 3 wide x 3 deep, root writes 1 level(s), models inherit, waves of 5 (2 dispatched, 1 min), plugin 0.2.0.

Levels 1-1 of 3 are listed. Print an input, a tree or an answer with everything beneath it:

```
python3 /Users/joshua/Developer/Plugins/ClaudeCodeCLI/FiveWhys/scripts/fivewhys.py show /private/tmp/g4-model.uNBicb/.five-whys/20260914-185928-our-nightly-database-backup-job-silently --id <id>
```

- 1 [input] Our nightly database backup job silently skips some runs, and nobody notices until a restore is needed.
  - 1.why [why]
    - 1.why.1 Alerting fires only on a failed exit code, so a run that never starts or exits early emits no signal at all.
    - 1.why.2 A stale lock from an overrunning or crashed previous run makes the next night's job exit cleanly with success, skipping the backup.
    - 1.why.3 No scheduled restore drill or check for tonight's backup file exists, so missing backups are first discovered during a real restore.

## Reading five-whys.json whole

Read these 1 windows in order; each stays under the Read tool's size limit:

- offset 1, limit 57
