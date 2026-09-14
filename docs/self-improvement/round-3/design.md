# Round 3 design: fixes from the v0.3.0 self-run

Status: design only. Nothing here is coded yet. Written 2026-09-13 on branch
`improve/v0.3.0`, where 0.3.0 is still unreleased.

Ids like 2.4.1.3 refer to reasons in `tree.json` in this folder.

## Evidence in this folder

| File | What it is |
|------|------------|
| `tree.json`, `index.md` | Full run of the v0.3.0 checkout on "rated 7.4/10": 3,905 of 3,905 reasons, 26 agents, each on its first attempt, waves of 5, 1,731 s from creation to the last fragment |
| `rating.md` | The 7.4 grading, passed to every agent as context. It was composed without a fixed rubric (see Fix 3) |
| `hygiene.json` | 0 exact duplicates, 3 near-duplicates, 14 cross-branch leads |
| `check-log.jsonl` | 27 checks, 0 failures |
| `usage.json` | Root 14.8k tokens; branches 28.4k-61.7k, mean 38.1k; 0.97M in total |

Context size at each agent's first turn, measured from Claude Code's subagent logs:

| Run | Dispatched from | First-turn context |
|-----|-----------------|--------------------|
| v0.2.0 full run | Interactive session with many plugins and MCP servers | 21.3k |
| v0.3.0 full run (this tree) | Headless `claude -p`, inside the repository | 4.9k |
| v0.3.0 measured branch | Headless `claude -p`, clean directory | 4.6k |

The session that dispatches the agents drives base cost, not the directory.
The current README and estimate basis attribute the gap to the directory,
which this evidence contradicts (Fix 5c).

This round has no per-reason ledger. The design works from the analysis's five
recurring causes. Full accounting can follow once Fix 3's audit tooling exists.

## Release sequencing

Decided 2026-09-13: every fix goes into 0.3.0 on this branch, and 0.3.0 is
released once. Bundling makes every applicable gate apply (4.1.1.3, 4.2.3).
To pay that cost once, the gates run together on the final commit, after the
last behavior change:

- the every-release gates
- a model-invoked run
- an interactive run
- a measured branch
- a scored quality sample by both scorers (Fix 3c)
- the independent ledger audit (Fix 3b)
- the eval (Fix 1)

Gate evidence goes stale when a later commit touches that gate's paths, and
stale evidence is rerun (4.1.4.4). Until the tool in 4b exists, check this by
hand with `git log <commit>..HEAD -- <paths>`.

---

## Fix 1: Unblock the eval

**Problem.** `claude plugin eval` refuses every case that grants Bash. It
reports that `~/.docker` holds symbolic links (2.1, 2.4).

**Findings (read-only checks, 2026-09-13):**

- Docker 29.5.2; its CLI supports `cliPluginsExtraDirs`.
- `~/.docker` holds 32 symlinks:
  - 15 in `cli-plugins` point into `/Applications/Docker.app/Contents/Resources/cli-plugins`.
  - 1 in `cli-plugins` points into `Docker.app/.../SecretsEngine/docker-pass.app`.
  - 16 in `bin/lib` are relative versioned dylib links (10 MB of llama and ggml libraries).
- `config.json` uses `credsStore: desktop` with 0 registries and no inline
  auth, token or password fields. Credentials live in the macOS keychain, not
  in `~/.docker`.

**Options:**

| Option | What | Verdict |
|--------|------|---------|
| A | Replace all 32 links with copies | Rejected. Plugin copies go stale after Desktop updates (2.4.1.5), Desktop may restore the links (2.1.3.3), and `cliPluginsExtraDirs` covers only the 16 plugin links, not the dylibs |
| B | Run the eval with `DOCKER_CONFIG` pointing at a plain folder holding only a copy of `config.json` | Rejected by the maintainer, 2026-09-13: no Docker workarounds |
| **C** | Run the eval where Docker Desktop isn't installed: a second macOS account or another machine | **Chosen** |

**Procedure for C.** Nothing under `~/.docker` on this Mac changes.

1. On the eval machine or account, confirm the guard has nothing to refuse:
   `find "${DOCKER_CONFIG:-$HOME/.docker}" -type l 2>/dev/null | head` prints nothing.
2. Check out the release commit and run the eval command from RELEASING.md.
3. Record the result with its commit, machine and date, in the Fix 4a format.

If no such environment exists once every other gate has passed, the eval is
recorded `[blocked]` and the maintainer decides whether to waive it (Fix 4a).
A waiver is never assumed.

- **Repository change:**
  - The RELEASING.md eval bullet gains the preflight check from step 1.
  - It says the eval runs where Docker Desktop's links are absent, and that
    Docker configuration is not altered to get there.
  - The note naming the symlink refusal moves under that preflight.
  - Eval results may be public (maintainer, 2026-09-13). The eval command in
    RELEASING.md and README.md drops `--no-publish`, and the recorded evidence
    links to the published result.
- **Acceptance:**
  - Both cases record more than 0 turns and receive a verdict.
  - Each verdict is recorded in CHANGELOG.md with the gate statuses from Fix 4.
- **Upstream:** report that the check refuses Docker Desktop's default layout.

---

## Fix 2: Write down the analysis boundary

**Problem.** "Analysis is up to the user" came to block quality measurement,
reading guidance and examples. No document says where the user's analysis ends
(3.5.1.3.1, 3.5.3.1.5, 3.1.3.3.2, 4.4.2.1, 4.4.4.1).

**Design.** Replace the README's "Generation only" design decision with three zones:

| Zone | Audience | Allowed | Not allowed |
|------|----------|---------|-------------|
| Run output: `five-whys.json`, `index.md`, `hygiene.json`, the final reply | User | Reasons verbatim, counts, mechanical flags, measurements | Ranking, summaries, selecting or pruning causes |
| Reading aids: README, SKILL.md loading section, `show` | User | How to load and navigate a tree, and a generic reading method | Examples that pick causes from a real tree |
| Development measurement: `docs/self-improvement/` | Maintainer | Scored samples, audits, reviews by a model or a person | Writing any score into a run directory or user-facing output |

- SKILL.md's "What this plugin does not do" gains one line pointing to the zones.
- Future catalogs narrow R-14 to "quality review inside the plugin at runtime".

**Tests.** A docs test checks that the README names all three zones and that
SKILL.md refers to them.

**Acceptance.** Fix 3's quality study is permitted by written policy.

---

## Fix 3: Break the closed loop

### 3a. Fixed rubric and rating records

**Problem.**
- Criteria were chosen after the evidence was in, and weights were never
  justified (5.3.1, 5.3.3).
- The rating lived only in conversation (5.2.5.1).

**Design:**

- **`docs/self-improvement/rubric.md` (version 1):**
  - A table of criterion, weight, and anchors describing what earns 4, 6, 8 and 10.
  - The evidence sources each criterion reads.
  - Weights sum to 100.
  - Edits happen only between rounds: bump the version and add a changelog
    line with the reason.
- **`round-N/rating.md`, committed before the self-run starts:**
  - Rubric version, per-criterion score and evidence links.
  - The grader's identity (for example "implementing session, claude-opus-5" or
    "fresh-context reviewer"), and the date.
- **Round 3's `rating.md`** is labeled *pre-rubric*. Its 7.4 isn't comparable
  with version-1 scores.
- **Two graders from round 4 on:** the implementing session and a
  fresh-context reviewer both grade. Both scores and their per-criterion
  differences are recorded.

**Tests (`tests/test_self_improvement.py`):**
- The rubric table parses, and its weights sum to 100.
- Every criterion has four anchors.
- Every `round-N/rating.md` from round 4 on names an existing rubric version.

### 3b. Independent, stratified ledger audit

**Problem.**
- The ledger's author audited it (5.1.2.2).
- Samples ignored inherited entries (5.4.3.4).
- Verdicts were typed into prose (5.1.2.2.1).

**Design, in `docs/self-improvement/ledger.py`:**

- **`sample N`** gains:
  - `--via own|inherited`
  - `--level L`
  - `--stratify`: equal draws per (level, own or inherited) group that exists,
    deterministic with `--seed`
  - `--json`, which writes a reviewer packet: id, reason, ancestor chain,
    code, code detail and note, with no other ledger context.
- **A new `audit <verdicts.json>` command** reads a verdict file shaped like this:

  ```json
  {"reviewer": "fresh-context Claude agent, claude-opus-5, no ledger or session history",
   "independent": true, "seed": 11, "stratified": true,
   "entries": [{"id": "5.4.4.3.1", "verdict": "fit|adjacent|wrong", "note": "..."}]}
  ```

  - It checks that every id exists in `ledger.json`.
  - It prints wrong and adjacent counts per group, plus the overall wrong rate
    with a 95% Wilson interval (standard library `math`).
  - It exits 1 on malformed files.
- **`docs/self-improvement/reviewer-prompt.md`** is what a reviewer receives:
  the catalog, the precedence rules and the packet, and nothing from the session.
- **RELEASING.md's self-run gate** requires a committed verdict file with
  `independent: true` and `stratified: true`.
- **First use:** audit the round-2 ledger, whose inherited leaves are the gap
  cause 5 names.

**Reviewers (decided 2026-09-13): both.**
- A fresh-context Claude agent reviews every audit draw and quality sample.
- The maintainer reviews the same draw when available.
- Each reviewer writes a separate verdict or score file. Given two files,
  `audit a.json b.json` prints per-id agreement next to each file's wrong rate.
- A fresh Claude agent is the same model family as the author (5.5), and its
  file records that.

**Tests.** Filter and group counts are deterministic for a seed, verdict
validation works, the Wilson interval matches known values, and two-file
agreement is computed on fixed inputs.

### 3c. Scored quality sample

**Problem.** Reason quality has no number, so 6.5/10 is a guess (3.1).

**Design:**

- **`docs/self-improvement/quality.py`:**
  - **`draw <tree> --n 30 --seed S --stratify level`** writes a packet of
    reasons with their ancestor chains, in shuffled order, with ids replaced by
    packet numbers so reviewers see nothing about position.
  - **`score <packet> <scores.json>`** validates a filled score file: each item
    gets causal, specific and distinct, each scored 0, 1 or 2, with an optional
    note.
  - **`report <scores...>`** prints per-criterion and per-level means, and for
    two scorers, exact agreement and mean absolute difference.
- **`docs/self-improvement/quality-rubric.md`** gives anchors for 0, 1 and 2
  on each criterion, taken from why-expander.md's rules.
- **Outputs** go to `round-N/quality/`, never into run directories (Fix 2).
- **Gate:** the prompt-text row in RELEASING.md replaces "read with `show
  --sample 20`" with "scored sample of 30 by two scorers, one independent;
  record means and agreement".
- **No pass threshold yet.** The first two studies set the baseline, and the
  regression rule is written after them (decision recorded in `rubric.md`).

**Tests.** Draws are deterministic, packets hold no ids, invalid scores are
rejected, and the agreement math is checked on fixed inputs.

---

## Fix 4: Make "done" mean observed

### 4a. Gate statuses

**Problem.**
- "Blocked" was recorded as if it were a result (2.3.5.1, 2.4.3.1).
- There's no blocked outcome (4.1.2.2).

**Design, in RELEASING.md:**

- Every gate ends as one of `passed`, `failed`, `blocked` or `waived`.
- A version is bumped only when every applicable gate is `passed`, or is
  `blocked` and then `waived` by the maintainer with a written reason.
- `failed` can never be waived.
- Evidence bullets in CHANGELOG.md follow this format:

  ```
  - [passed] model-run @3f2a1b0: /five-whys --smoke --yes ... 39/39, 4 checks, 0 failed
  - [blocked] eval @ed42be1: refused, ~/.docker symlinks; [waived] by the maintainer: <reason>
  ```

  Gate names: `unit`, `validate`, `model-run`, `interactive`, `eval`,
  `measured-branch`, `full-run`, `ledger-audit`, `quality-sample`.

**Tests.** A docs test parses the dated section for the manifest version. Every
Evidence bullet must carry a status and a gate name, `[failed]` must be absent,
and every `[blocked]` must include `[waived]`.

### 4b. Stale evidence check (optional; can wait)

**Problem.** Fixes landed after gate evidence was recorded, as `ed42be1` did
after `b61eb75` (4.1.4.4).

**Design.** `tools/release_gates.py` reads the Unreleased Evidence bullets. It
maps each gate name to the paths it covers:

| Gate | Paths |
|------|-------|
| `model-run` | `skills/`, `agents/`, `scripts/` |
| `eval` | `evals/`, `RELEASING.md` |
| `measured-branch` | `agents/`, `scripts/fivewhys.py` |

A gate is **stale** when `git log <commit>..HEAD -- <paths>` shows commits. The
tool prints a table and exits 1 if any gate is stale.

**Tests.** A temporary git repository with two commits confirms stale detection.

### 4c. Verification records for improvements

**Problem.** Catalog items counted as done once they were implemented
(3.4.3.1, 1.3.4.3).

**Design.** `round-N/verification.json` records each IMP code as
`{"status": "observed|blocked|not-run", "evidence": "...", "commit": "..."}`.
`ledger.py <round> verify` lists IMP codes that aren't `observed`, and the
round README reports the observed count. Round 2 gets filled in honestly, for
example:
- IMP-50 (eval case): `blocked`.
- IMP-49 (non-software guidance): `not-run`.
- IMP-37 (parse): `observed` by the model-invoked and interactive runs.

### 4d. Deferrals carry a trigger

**Problem.** R-18 lumped one-off runs in with multi-run studies, and deferrals
never came back (3.4.5.2, 4.4.5.2, 2.3.5.5).

**Design:**
- A catalog field `"schema": 3` makes `ledger.py` require a `deferral` object,
  `{"kind": "one-off-run|study", "trigger": "...", "cost": "..."}`, on every
  disposition titled "Deferred".
- The next catalog splits R-18 into one-off runs and studies.

---

## Fix 5: Small concrete fixes

### 5a. Per-wave timing

**Problem.** No wave timestamps exist, so per-wave time can't be measured (1.4).

**Design:**

- **`plan --record`** appends to `run.json`:
  `"waves": [{"wave": 1, "at": "<iso>", "ids": ["root"], "max_parallel": 5}]`.
  Retries appear as new waves, and `plan` without `--record` writes nothing.
- **`status`** adds `waves[].finished`: the latest `at` among ok checks for
  that wave's ids in `check-log.jsonl`, or null while any are missing. It also
  adds `waves[].seconds`.
- **`assemble`:**
  - The header gains `timing`, holding waves (count of ids and seconds) and
    `total_seconds`.
  - The index.md settings line adds "N waves, M min".
- **Compatibility.** Runs without `waves` report an empty list.

**Tests.** The replay test asserts the waves are `[root]` then `[1, 2, 3]`,
with ISO timestamps; status reports seconds as a non-negative integer or null.

### 5b. Check log records error kinds

**Problem.** The check log keeps only totals (3.5.4.3).

**Design:**
- `log_check` writes `kinds` for errors (`count`, `missing_reason`,
  `leaf_whys`, `json`, `top_level`, `assumptions`) and `warning_kinds`
  (`exact`, `near`, `restates`, `over_length`).
- A regex-based `error_kind(message)` sorts messages into kinds, with no
  refactor of `validate`.
- `status` sums kinds per fragment.

**Tests.** A miscounted fragment logs `count: 1`; a duplicate logs `exact: 1`.

### 5c. Usage report kept with evidence; README cost correction

**Problem.**
- Measurements printed to the terminal only (5.2.5.5).
- The README attributes cost to where the run happens, which the evidence above
  contradicts.

**Design:**
- `usage.py --out FILE` writes the JSON.
- Each agent entry gains `first_turn_context`, and the summary gains its
  min, mean and max.
- The README cost table gains a third column for the v0.3.0 headless run
  inside the repository:
  - first-turn context 4.9k
  - root 14.8k
  - branches 28.4k-61.7k (mean 38.1k)
  - total 0.97M
  - 1,731 s
  - output 607 KB
- The explanation changes to: cost depends mainly on the dispatching session's
  inherited context and on evidence reading.
- The estimate basis string is updated the same way.
- The constants stay; the 0.60M-1.62M range still contains all three runs.

**Tests.** `first_turn_context` is parsed from a synthetic log file.

### 5d. Ledger sample filters

Covered by Fix 3b.

### 5e. Agents stay off the network

**Problem.** Subagent logs show branch agents 4.3, 5.1 and 5.2 ran `gh`
commands through Bash, 8 in all:
- `gh api` for traffic and marketplace contents
- `gh repo view`
- `gh pr list`

The README says the plugin is local-only; nothing in the tree covers this.

**Design:**
- why-expander.md's first output step becomes: read local files only; do not
  run network commands such as `gh`, `curl` or `git fetch`.
- A new README Known limitations line: the rule is an instruction, not
  enforced, because agents have Bash.

**Gate.** Covered by the final gates. The model-invoked run's agent logs must
show no network commands.

### 5f. One script path everywhere

**Problem.** The orchestrator shortened `$S` to the relative
`scripts/fivewhys.py`. That works only when running inside the repository.

**Design:**
- `parse` output adds `"script": "<absolute path>"`.
- SKILL.md Steps 2-5 say to use `python3 "<script>"` from the parse output.
- Step 1 keeps `${CLAUDE_PLUGIN_ROOT}`.

**Tests:**
- A parse test checks that `script` is an existing absolute path.
- A docs test checks that SKILL.md never invokes `scripts/fivewhys.py` without
  a variable prefix.

### 5g. Correct the documentation behind false premises

- **Replay test.** Several reasons assumed it replays recorded v0.2.0
  fragments (1.1.2.1.3, 1.1.2.3.2, 1.3.5.2.4). The README and CHANGELOG will
  say it uses synthetic fragments written by the test.
- **Note length.** Round 2's README will state that ledger notes allow 30 words
  (5.1.1.4.4).

---

## Explicitly out of scope

- No new `/five-whys` options; the option count stays 10.
- These remain declined:
  - a mid-size preset
  - an HTML viewer
  - settings files (R-16)
  - telemetry (R-17)
  - vendor API calls (R-02)
- Cross-family review stays a known limitation. Fix 3 uses a human or a
  fresh-context reviewer instead.
- No round-3 per-reason ledger in this pass.

## Work order

All work happens on `improve/v0.3.0`, one commit per step, with tests passing
before each commit. Code and text changes come first, so the studies and gates
run once, against the final code.

| # | Change | Depends on |
|---|--------|-----------|
| 1 | 5g documentation corrections | none |
| 2 | Fix 2 boundary zones and docs test | none |
| 3 | 4a gate statuses and docs test; rewrite the existing Unreleased evidence in the new format | none |
| 4 | 3a rubric, rating format and tests | 2 |
| 5 | 3b ledger filters, `audit` with two-file agreement, reviewer prompt and tests | 4 |
| 6 | 3c `quality.py`, quality rubric and tests | 2 |
| 7 | 4c verification records (round 2 filled in), 4d deferral schema | 3 |
| 8 | 5c `usage.py --out` and first-turn context | none |
| 9 | 5a wave timing, 5b check-log kinds | none |
| 10 | 5e agent network rule, 5f script path | none |
| 11 | README cost section; CHANGELOG Unreleased entries for steps 1-10 | 8-10 |
| 12 | Studies, both reviewers: independent audit of the round-2 ledger; scored baseline sample of this round's tree | 5, 6 |
| 13 | Gates on the final commit: every-release, model-invoked run, interactive run, measured branch, scored sample of the new run's tree against the step-12 baseline by level, eval per Fix 1 | 11, 12 |
| 14 | Release 0.3.0: bump, dated entry, merge, marketplace entry | 13 all passed, or blocked items waived by the maintainer |
| After 0.3.0 | 4b `tools/release_gates.py` | 3 |

## Decisions (2026-09-13)

1. **Eval:** no Docker workarounds. The eval runs where Docker Desktop isn't
   installed. Otherwise it's recorded as blocked, for the maintainer to decide
   (Fix 1).
2. **Release:** all fixes bundle into 0.3.0.
3. **Reviewers:** both a fresh-context Claude agent and the maintainer.
4. **Stale-evidence tool (4b):** after 0.3.0.
