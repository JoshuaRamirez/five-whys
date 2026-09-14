#!/usr/bin/env python3
"""Ledger tooling for the five-whys self-improvement rounds.

Each round directory holds the tree the plugin produced about itself
(tree.json), a catalog of dispositions derived from reading it (catalog.json)
and ledger fragments (ledger/). Every reason in the tree gets exactly one
disposition code from the catalog.

Fragments come in two forms:
  *.json  {"entries": [{"id", "d", "note"}]}, one entry per reason (round 1)
  *.txt   rule lines "<id> <CODE> <note>"; a rule covers its node and every
          descendant that has no rule of its own (round 2)

  ledger.py <round> check <fragment> [--scope S]  validate one fragment
  ledger.py <round> merge [--allow-new]           prove every reason is covered
                                                  once; write ledger.json and summary.md
  ledger.py <round> sample N [--seed S] [--code C]  print random entries with their
                                                  ancestor chain and code detail
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

MAX_NOTE_WORDS = 25
CITED = re.compile(r"\b(?:IMP|R)-\d+\b")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk(nodes, parent=None):
    for node in nodes:
        yield node, parent
        yield from walk(node.get("whys", []), node["id"])


class Round:
    def __init__(self, folder: Path):
        self.folder = folder
        self.nodes, self.parent = {}, {}
        for node, parent in walk(load(folder / "tree.json")["whys"]):
            self.nodes[node["id"]] = node
            self.parent[node["id"]] = parent
        catalog = load(folder / "catalog.json")
        self.catalog = {item["code"]: item for item in catalog["improvements"] + catalog["dispositions"]}
        self.max_words = catalog.get("max_note_words", MAX_NOTE_WORDS)

    def chain(self, node_id: str) -> list[str]:
        ids = []
        while node_id:
            ids.append(node_id)
            node_id = self.parent[node_id]
        return ids[::-1]

    def scope_ids(self, scope: str) -> list[str]:
        if scope == "root":
            return [i for i, n in self.nodes.items() if n["depth"] <= 2]
        return [i for i in self.nodes if i == scope or i.startswith(scope + ".")]

    def read_fragment(self, path: Path) -> tuple[list[dict], list[str]]:
        """Return (entries with a "rule" flag, errors)."""
        if path.suffix == ".json":
            try:
                entries = load(path)["entries"]
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                return [], [f'cannot read {path.name}: {exc} (expected {{"entries": [...]}})']
            return [dict(e, rule=False) for e in entries], []
        entries, errors = [], []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 3:
                errors.append(f"{path.name}:{n}: expected '<id> <CODE> <note>'")
                continue
            entries.append({"id": parts[0], "d": parts[1], "note": parts[2], "rule": True})
        return entries, errors

    def validate(self, entries: list[dict]) -> list[str]:
        errors, seen = [], Counter()
        for entry in entries:
            node_id, code, note = entry.get("id"), entry.get("d"), entry.get("note")
            seen[node_id] += 1
            if node_id not in self.nodes:
                errors.append(f"{node_id!r}: no such reason in tree.json")
            if code not in self.catalog:
                errors.append(f"{node_id}: unknown code {code!r}")
            if not isinstance(note, str) or not note.strip():
                errors.append(f"{node_id}: note is required")
            elif len(note.split()) > self.max_words:
                errors.append(f"{node_id}: note exceeds {self.max_words} words")
        errors += [f"{i}: listed {c} times" for i, c in seen.items() if c > 1]
        return errors

    def resolve(self, entries: list[dict]) -> tuple[dict, list[str]]:
        """Map every reason id to (entry, via) where via is the rule id it inherited from."""
        direct = {e["id"]: e for e in entries}
        resolved, missing = {}, []
        for node_id in self.nodes:
            owner = next((i for i in reversed(self.chain(node_id))
                          if i in direct and (i == node_id or direct[i]["rule"])), None)
            if owner is None:
                missing.append(f"{node_id}: missing")
            else:
                resolved[node_id] = (direct[owner], None if owner == node_id else owner)
        return resolved, missing


def cmd_check(ledger: Round, args) -> None:
    path = Path(args.fragment)
    entries, errors = ledger.read_fragment(path)
    errors += ledger.validate(entries)
    if args.scope:
        expected = set(ledger.scope_ids(args.scope))
        if not expected:
            sys.exit(f"unknown scope {args.scope!r}")
        errors += [f"{e['id']}: outside scope {args.scope}" for e in entries if e["id"] not in expected]
        if not any(e["rule"] for e in entries):  # per-reason fragments must list every id
            listed = {e["id"] for e in entries}
            errors += [f"{i}: missing" for i in sorted(expected - listed)]
    if errors:
        print("\n".join(errors[:30]) + (f"\n... and {len(errors) - 30} more errors" if len(errors) > 30 else ""))
        sys.exit(1)
    print(f"OK {len(entries)} entries")


def cmd_merge(ledger: Round, args) -> None:
    entries, errors = [], []
    for fragment in sorted((ledger.folder / "ledger").glob("*.*")):
        found, errs = ledger.read_fragment(fragment)
        entries += found
        errors += errs
    errors += ledger.validate(entries)
    resolved, missing = ledger.resolve(entries)
    errors += missing
    new = [i for i, (e, _) in resolved.items() if e["d"] == "NEW"]
    if new and not args.allow_new:
        errors.append(f"{len(new)} reasons still resolve to NEW and need reconciliation")
    if errors:
        print("\n".join(errors[:40]))
        sys.exit(1)

    lines, counts, x_total, x_cited = [], Counter(), 0, 0
    for node_id, node in ledger.nodes.items():
        entry, via = resolved[node_id]
        counts[entry["d"]] += 1
        if entry["d"].startswith("X-"):
            x_total += 1
            x_cited += bool(CITED.search(entry["note"]))
        record = {"id": node_id, "d": entry["d"], "note": entry["note"].strip(),
                  **({"via": via} if via else {}), "reason": node["reason"]}
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    (ledger.folder / "ledger.json").write_text('{"entries":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")

    rules = sum(1 for e in entries if e["rule"])
    inherited = sum(1 for _, via in resolved.values() if via)
    out = ["# Self-improvement ledger summary", "",
           f"{len(resolved)} reasons, each with exactly one disposition."]
    if rules:
        out += ["", f"{len(entries)} written lines; {len(resolved) - inherited} reasons have their own line and "
                    f"{inherited} inherit the nearest ancestor's line (recorded as `via` in ledger.json)."]
    out += ["", f"X dispositions whose note cites an IMP or R code: {x_cited} of {x_total}.", "",
            "| Code | Title | Reasons |", "|------|-------|---------|"]
    out += [f"| {code} | {item['title']} | {counts[code]} |" for code, item in ledger.catalog.items()]
    (ledger.folder / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(json.dumps({"reasons": len(resolved), "lines": len(entries), "inherited": inherited,
                      "x_cited": f"{x_cited}/{x_total}", "counts": dict(counts)}, indent=2))


def cmd_sample(ledger: Round, args) -> None:
    data = load(ledger.folder / "ledger.json")["entries"]
    pool = [e for e in data if not args.code or e["d"] == args.code]
    for k, entry in enumerate(random.Random(args.seed).sample(pool, min(args.n, len(pool)))):
        if k:
            print()
        for ancestor in ledger.chain(entry["id"])[:-1]:
            print(f"^ {ancestor}  {ledger.nodes[ancestor]['reason']}")
        print(f"{entry['id']}  {entry['reason']}")
        item = ledger.catalog[entry["d"]]
        print(f"=> {entry['d']} ({item['title']}){' via ' + entry['via'] if entry.get('via') else ''}")
        print(f"   note: {entry['note']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("round", help="round directory, e.g. docs/self-improvement/round-2")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("fragment")
    p.add_argument("--scope")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("merge")
    p.add_argument("--allow-new", action="store_true")
    p.set_defaults(func=cmd_merge)
    p = sub.add_parser("sample")
    p.add_argument("n", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--code")
    p.set_defaults(func=cmd_sample)
    args = parser.parse_args()
    args.func(Round(Path(args.round)), args)


if __name__ == "__main__":
    main()
