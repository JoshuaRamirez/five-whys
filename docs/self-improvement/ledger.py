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
  ledger.py <round> sample N [--seed S] [--code C] [--via own|inherited] [--level L]
                             [--stratify] [--json]
                                                  print random entries with their ancestor
                                                  chain and code detail; --stratify draws
                                                  equally per (level, own or inherited);
                                                  --json prints a reviewer packet
  ledger.py <round> audit VERDICTS [VERDICTS]     validate reviewer verdict files and report
                                                  wrong-code rates; two files add agreement
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

MAX_NOTE_WORDS = 25
CITED = re.compile(r"\b(?:IMP|R)-\d+\b")
VERDICTS = ("fit", "adjacent", "wrong")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk(nodes, parent=None):
    for node in nodes:
        yield node, parent
        yield from walk(node.get("whys", []), node["id"])


def level_of(node_id: str) -> int:
    return node_id.count(".") + 1


def group_of(entry: dict) -> tuple[int, str]:
    return level_of(entry["id"]), "inherited" if entry.get("via") else "own"


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """95% Wilson score interval for k of n."""
    if n == 0:
        return [0.0, 1.0]
    p, denom = k / n, 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


class Round:
    def __init__(self, folder: Path):
        self.folder = folder
        self.nodes, self.parent = {}, {}
        for node, parent in walk(load(folder / "tree.json")["whys"]):
            self.nodes[node["id"]] = node
            self.parent[node["id"]] = parent
        catalog = load(folder / "catalog.json")
        self.rules = catalog.get("rules", [])
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

    def ledger(self) -> list[dict]:
        path = self.folder / "ledger.json"
        if not path.exists():
            sys.exit(f"{path} does not exist; run merge first")
        return load(path)["entries"]


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


def draw(pool: list[dict], n: int, seed, stratify: bool) -> list[dict]:
    """Uniform draw, or an equal share per (level, own or inherited); a small group gives all it has."""
    rng = random.Random(seed)
    if not stratify:
        return rng.sample(pool, min(n, len(pool)))
    groups: dict[tuple, list] = {}
    for entry in pool:
        groups.setdefault(group_of(entry), []).append(entry)
    share, extra = divmod(n, len(groups)) if groups else (0, 0)
    picked = []
    for k, key in enumerate(sorted(groups)):
        want = share + (1 if k < extra else 0)
        picked += rng.sample(groups[key], min(want, len(groups[key])))
    return picked


def cmd_sample(ledger: Round, args) -> None:
    pool = [e for e in ledger.ledger()
            if (not args.code or e["d"] == args.code)
            and (not args.via or group_of(e)[1] == args.via)
            and (not args.level or level_of(e["id"]) == args.level)]
    picked = draw(pool, args.n, args.seed, args.stratify)
    if args.json:  # what an independent reviewer gets: no ledger files, no session history
        print(json.dumps({
            "round": ledger.folder.name,
            "seed": args.seed,
            "stratified": args.stratify,
            "filters": {"code": args.code, "via": args.via, "level": args.level},
            "groups": dict(Counter(f"level {lvl} {kind}" for lvl, kind in map(group_of, picked))),
            "rules": ledger.rules,
            "codes": {code: {"title": item["title"], "detail": item.get("detail", "")}
                      for code, item in ledger.catalog.items()},
            "entries": [{"id": e["id"], "level": level_of(e["id"]), "inherited_from": e.get("via"),
                         "chain": [{"id": a, "reason": ledger.nodes[a]["reason"]} for a in ledger.chain(e["id"])[:-1]],
                         "reason": e["reason"], "code": e["d"], "note": e["note"]} for e in picked],
        }, indent=1, ensure_ascii=False))
        return
    for k, entry in enumerate(picked):
        if k:
            print()
        for ancestor in ledger.chain(entry["id"])[:-1]:
            print(f"^ {ancestor}  {ledger.nodes[ancestor]['reason']}")
        print(f"{entry['id']}  {entry['reason']}")
        item = ledger.catalog[entry["d"]]
        print(f"=> {entry['d']} ({item['title']}){' via ' + entry['via'] if entry.get('via') else ''}")
        print(f"   note: {entry['note']}")


def read_verdicts(path: Path, known: set) -> tuple[dict | None, list[str]]:
    try:
        data = load(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{path.name}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{path.name}: expected a JSON object"]
    errors = []
    if not isinstance(data.get("reviewer"), str) or not data["reviewer"].strip():
        errors.append("reviewer: required, naming who reviewed and what they could see")
    for field in ("independent", "stratified"):
        if not isinstance(data.get(field), bool):
            errors.append(f"{field}: must be true or false")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("entries: must be a non-empty list")
        entries = []
    seen = Counter()
    for k, entry in enumerate(entries):
        where = f"entries[{k}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected an object")
            continue
        seen[entry.get("id")] += 1
        if entry.get("id") not in known:
            errors.append(f"{where}: no ledger entry {entry.get('id')!r}")
        verdict = entry.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{where}: verdict must be one of {', '.join(VERDICTS)}")
        elif verdict != "fit" and not str(entry.get("note") or "").strip():
            errors.append(f"{where}: a {verdict} verdict needs a note naming the better code")
    errors += [f"{i}: listed {c} times" for i, c in seen.items() if c > 1]
    return (None if errors else data), [f"{path.name}: {e}" for e in errors]


def summarize(entries: list[dict], by_id: dict) -> dict:
    groups: dict[str, Counter] = {}
    for entry in entries:
        level, kind = group_of(by_id[entry["id"]])
        groups.setdefault(f"level {level} {kind}", Counter())[entry["verdict"]] += 1
    counts = Counter(e["verdict"] for e in entries)
    return {"n": len(entries), **{v: counts[v] for v in VERDICTS},
            "wrong_rate": round(counts["wrong"] / len(entries), 4), "wrong_rate_95": wilson(counts["wrong"], len(entries)),
            "groups": {key: {"n": sum(c.values()), **{v: c[v] for v in VERDICTS}} for key, c in sorted(groups.items())}}


def cmd_audit(ledger: Round, args) -> None:
    by_id = {e["id"]: e for e in ledger.ledger()}
    files, errors = [], []
    for name in args.verdicts:
        data, errs = read_verdicts(Path(name), set(by_id))
        errors += errs
        if data:
            files.append((name, data))
    if errors:
        print("\n".join(errors[:40]))
        sys.exit(1)
    result = {"files": [{"file": name, "reviewer": data["reviewer"], "independent": data["independent"],
                         "stratified": data["stratified"], **summarize(data["entries"], by_id)} for name, data in files]}
    if len(files) == 2:
        a, b = ({e["id"]: e["verdict"] for e in data["entries"]} for _, data in files)
        common = sorted(set(a) & set(b), key=lambda i: [int(x) for x in i.split(".")])
        if common:
            result["agreement"] = {
                "common": len(common),
                "exact": round(sum(a[i] == b[i] for i in common) / len(common), 4),
                "disagreements": [{"id": i, "a": a[i], "b": b[i]} for i in common if a[i] != b[i]],
            }
    print(json.dumps(result, indent=2))


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
    p.add_argument("--via", choices=("own", "inherited"))
    p.add_argument("--level", type=int)
    p.add_argument("--stratify", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sample)
    p = sub.add_parser("audit")
    p.add_argument("verdicts", nargs="+")
    p.set_defaults(func=cmd_audit)
    args = parser.parse_args()
    if args.command == "audit" and len(args.verdicts) > 2:
        parser.error("audit takes one or two verdict files")
    args.func(Round(Path(args.round)), args)


if __name__ == "__main__":
    main()
