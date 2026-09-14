# Ledger audit: reviewer instructions

You are auditing a sample of a self-improvement ledger for the five-whys
plugin. Someone else wrote the ledger. Judge it only from the packet you are
given. Don't open the round's `ledger.json`, `ledger/`, `audit.md` or earlier
verdict files, and don't look for the session that wrote them.

## The packet

`ledger.py <round> sample N --stratify --seed S --json` prints:

- `rules`: the precedence rules for choosing a code
- `codes`: every code with its title and detail
- `entries`: the sampled reasons. Each entry has:
  - `chain`: its ancestors
  - `code`: the code it was given
  - `inherited_from`: the ancestor whose line the code came from, or null
  - `note`: why the code was given

## Verdicts

For each entry, choose one:

- **fit:** the code is the best one in `codes` for this reason under `rules`,
  and the note describes this reason.
- **adjacent:** another code fits at least as well, or the note describes an
  ancestor rather than this reason. Say which code, or what the note misses.
- **wrong:** the code does not apply to this reason. Name the code that does.

Judge an inherited code exactly like one written for the reason itself. Nobody
was checking that inheriting it was reasonable; the question is whether the
code fits this reason.

## What to write

A JSON file, usually `round-N/audit/<reviewer>.json`:

```json
{"reviewer": "<who you are, which model, and that you saw only the packet>",
 "independent": true, "seed": 11, "stratified": true,
 "entries": [{"id": "2.4.1.3", "verdict": "adjacent", "note": "R-18 fits better: ..."}]}
```

Every sampled id appears exactly once. `adjacent` and `wrong` need a note.
Copy `seed` and `stratified` from the packet. Then run
`ledger.py <round> audit <file>`; it must print a report, not errors.
