# Five Whys index

Problem: Our nightly database backup job silently skips some nights; the cron entry and the backup script have not changed in months.

Settings: 3 wide x 3 deep, root writes 1 level(s), model inherit, waves of 5 (2 dispatched, 4 min), plugin 0.2.0.

Level 1 of 3. Each level-1 reason heads a branch of 12 deeper reasons. Print one branch with:

```
python3 /Users/joshua/Developer/Plugins/ClaudeCodeCLI/FiveWhys/scripts/fivewhys.py show /private/tmp/fivewhys-gate-model.jMf744/.five-whys/20260913-225447-our-nightly-database-backup-job-silently --id <id>
```

- 1 The host is rebooted or suspended during the scheduled window, and cron never replays a run it missed.
- 2 A slow prior run or stale lock file makes the script exit early without dumping the database.
- 3 The cron time falls in the daylight-saving changeover hour, so that night's scheduled minute never occurs.

## Reading five-whys.json whole

Read these 1 windows in order; each stays under the Read tool's size limit:

- offset 1, limit 53
