#!/usr/bin/env python3
"""Ledger tooling for the five-whys self-improvement pass.

Every reason in tree.json gets exactly one disposition code from catalog.json.
Agents write one ledger fragment per scope ("root" = levels 1-2, or a level-2
id such as "2.4" = everything beneath it).

  check <fragment> --scope S   validate one fragment against its scope
  merge                        prove all reasons are covered exactly once and
                               write ledger.json plus summary.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE / "tree.json"
CATALOG = HERE / "catalog.json"
FRAGMENTS = HERE / "ledger"
MAX_NOTE_WORDS = 25


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("whys", []))


def tree_nodes() -> dict:
    return {node["id"]: node for node in walk(load(TREE)["whys"])}


def catalog_codes() -> dict:
    catalog = load(CATALOG)
    return {item["code"]: item["title"] for item in catalog["improvements"] + catalog["dispositions"]}


def scope_ids(nodes: dict, scope: str) -> list[str]:
    if scope == "root":
        return [i for i, n in nodes.items() if n["depth"] <= 2]
    return [i for i in nodes if i.startswith(scope + ".")]


def validate(entries, expected: list[str], codes: dict) -> list[str]:
    if not isinstance(entries, list):
        return ["entries: expected a list"]
    errors, seen = [], Counter()
    expected_set = set(expected)
    for k, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{k}]: expected an object")
            continue
        node_id, code, note = entry.get("id"), entry.get("d"), entry.get("note")
        seen[node_id] += 1
        if node_id not in expected_set:
            errors.append(f"entries[{k}]: id {node_id!r} is not in this scope")
        if code not in codes:
            errors.append(f"{node_id}: unknown code {code!r}")
        if not isinstance(note, str) or not note.strip():
            errors.append(f"{node_id}: note is required")
        elif len(note.split()) > MAX_NOTE_WORDS:
            errors.append(f"{node_id}: note exceeds {MAX_NOTE_WORDS} words")
    errors += [f"{i}: listed {c} times" for i, c in seen.items() if c > 1]
    errors += [f"{i}: missing" for i in expected if seen[i] == 0]
    return errors


def cmd_check(args) -> None:
    nodes = tree_nodes()
    expected = scope_ids(nodes, args.scope)
    if not expected:
        sys.exit(f"unknown scope {args.scope!r}")
    try:
        entries = load(Path(args.fragment))["entries"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        sys.exit(f'cannot read {args.fragment}: {exc} (expected {{"entries": [...]}})')
    errors = validate(entries, expected, catalog_codes())
    if errors:
        print("\n".join(errors[:30]))
        if len(errors) > 30:
            print(f"... and {len(errors) - 30} more errors")
        sys.exit(1)
    print(f"OK {len(entries)} entries")


def cmd_merge(args) -> None:
    nodes, codes = tree_nodes(), catalog_codes()
    entries = []
    for fragment in sorted(FRAGMENTS.glob("*.json")):
        entries.extend(load(fragment)["entries"])
    errors = validate(entries, list(nodes), codes)
    new = [e for e in entries if e.get("d") == "NEW"]
    if new and not args.allow_new:
        errors.append(f"{len(new)} NEW entries still need reconciliation")
    if errors:
        print("\n".join(errors[:40]))
        sys.exit(1)

    by_id = {e["id"]: e for e in entries}
    lines = []
    for node_id, node in nodes.items():
        e = by_id[node_id]
        record = {"id": node_id, "d": e["d"], "note": e["note"].strip(), "reason": node["reason"]}
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    (HERE / "ledger.json").write_text('{"entries":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")

    counts = Counter(e["d"] for e in entries)
    out = ["# Self-improvement ledger summary", "",
           f"{len(entries)} reasons, each with exactly one disposition.", "",
           "| Code | Title | Reasons |", "|------|-------|---------|"]
    out += [f"| {code} | {title} | {counts[code]} |" for code, title in codes.items()]
    (HERE / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(entries), "counts": dict(counts)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("fragment")
    p.add_argument("--scope", required=True)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("merge")
    p.add_argument("--allow-new", action="store_true")
    p.set_defaults(func=cmd_merge)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
