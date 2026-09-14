#!/usr/bin/env python3
"""Scored quality samples of a five-whys tree, for development measurement.

Scores stay in docs/self-improvement and never go into a run directory or
anything a run shows its user (see the README's design decisions). Criteria and
anchors are in quality-rubric.md.

  quality.py draw <tree> --n N --seed S [--stratify level] --out PACKET
      write a scoring packet (shuffled, no ids) and PACKET.key.json beside it
  quality.py score <packet> <scores>
      validate one scorer's file against the packet
  quality.py report <packet> <scores> [<scores>]
      means per criterion and per level; with two scorers, agreement

<tree> is five-whys.json, a run directory or a round's tree.json.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

CRITERIA = ("causal", "specific", "distinct")
SCORES = (0, 1, 2)


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def key_path(packet: Path) -> Path:
    return packet.with_name(packet.stem + ".key.json")


def reasons_in_context(nodes, chain=()) -> list[dict]:
    """Every reason with its ancestors' texts and its siblings' texts."""
    out = []
    for node in nodes:
        if node.get("missing"):
            continue
        out.append({"id": node["id"], "level": len(chain) + 1, "chain": [c["reason"] for c in chain],
                    "reason": node["reason"], "siblings": [n["reason"] for n in nodes if n is not node]})
        out += reasons_in_context(node.get("whys") or [], chain + (node,))
    return out


def tree_reasons(tree: dict) -> list[dict]:
    """Reasons in context from a tree assembled with inputs (0.3.0 on) or without them (earlier)."""
    if "inputs" not in tree:
        return reasons_in_context(tree["whys"])
    return [dict(item, input=entry["input"]) for entry in tree["inputs"] if not entry.get("missing")
            for item in reasons_in_context(entry.get("whys") or [])]


def cmd_draw(args) -> None:
    source = Path(args.tree)
    if source.is_dir():
        source = source / "five-whys.json"
    tree = load(source)
    pool = tree_reasons(tree)
    rng = random.Random(args.seed)
    if args.stratify == "level":
        levels: dict[int, list] = {}
        for item in pool:
            levels.setdefault(item["level"], []).append(item)
        share, extra = divmod(args.n, len(levels))
        picked = []
        for k, level in enumerate(sorted(levels)):
            picked += rng.sample(levels[level], min(share + (1 if k < extra else 0), len(levels[level])))
    else:
        picked = rng.sample(pool, min(args.n, len(pool)))
    rng.shuffle(picked)  # packet order says nothing about position in the tree
    out = Path(args.out)
    packet = {
        **({"problem": tree["problem"]} if tree.get("problem") else {}),
        **({"context": tree["context"]} if tree.get("context") else {}),
        "instructions": "Score each item with quality-rubric.md. input, when present, is the problem the item's "
                        "tree answers; chain lists the reasons above it, from the top; siblings are the other "
                        "reasons answering the same why.",
        "items": [{"n": k, **({"input": item["input"]} if "input" in item else {}), "chain": item["chain"],
                   "reason": item["reason"], "siblings": item["siblings"]} for k, item in enumerate(picked, 1)],
    }
    key = {"tree": str(source), "seed": args.seed, "stratify": args.stratify,
           "items": [{"n": k, "id": item["id"], "level": item["level"]} for k, item in enumerate(picked, 1)]}
    out.write_text(json.dumps(packet, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    key_path(out).write_text(json.dumps(key, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"packet": str(out), "key": str(key_path(out)), "items": len(picked)}, indent=2))


def read_scores(packet: dict, path: Path) -> tuple[dict | None, list[str]]:
    try:
        data = load(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{path.name}: {exc}"]
    errors = []
    if not isinstance(data, dict):
        return None, [f"{path.name}: expected a JSON object"]
    if not isinstance(data.get("scorer"), str) or not data["scorer"].strip():
        errors.append("scorer: required, naming who scored and what they could see")
    if not isinstance(data.get("independent"), bool):
        errors.append("independent: must be true or false")
    wanted = {item["n"] for item in packet["items"]}
    seen = set()
    for k, score in enumerate(data.get("scores") if isinstance(data.get("scores"), list) else []):
        where = f"scores[{k}]"
        n = score.get("n") if isinstance(score, dict) else None
        if n not in wanted:
            errors.append(f"{where}: n must be an item number from the packet")
            continue
        if n in seen:
            errors.append(f"{where}: item {n} scored twice")
        seen.add(n)
        for criterion in CRITERIA:
            value = score.get(criterion)
            if isinstance(value, bool) or value not in SCORES:
                errors.append(f"{where}: {criterion} must be 0, 1 or 2")
    if not isinstance(data.get("scores"), list):
        errors.append("scores: must be a list")
    elif wanted - seen:
        errors.append(f"items not scored: {', '.join(map(str, sorted(wanted - seen)))}")
    return (None if errors else data), [f"{path.name}: {e}" for e in errors]


def cmd_score(args) -> None:
    packet = load(Path(args.packet))
    data, errors = read_scores(packet, Path(args.scores))
    if errors:
        print("\n".join(errors[:40]))
        sys.exit(1)
    print(f"OK {len(data['scores'])} items scored by {data['scorer']}")


def means(scores: list[dict]) -> dict:
    return {c: round(statistics.mean(s[c] for s in scores), 3) for c in CRITERIA}


def cmd_report(args) -> None:
    packet_path = Path(args.packet)
    packet, key = load(packet_path), load(key_path(packet_path))
    level = {item["n"]: item["level"] for item in key["items"]}
    scorers, errors = [], []
    for name in args.scores:
        data, errs = read_scores(packet, Path(name))
        errors += errs
        if data:
            scorers.append(data)
    if errors:
        print("\n".join(errors[:40]))
        sys.exit(1)
    result = {"packet": str(packet_path), "tree": key["tree"], "items": len(packet["items"]), "scorers": []}
    for data in scorers:
        by_level: dict[int, list] = {}
        for score in data["scores"]:
            by_level.setdefault(level[score["n"]], []).append(score)
        result["scorers"].append({"scorer": data["scorer"], "independent": data["independent"],
                                  "means": means(data["scores"]),
                                  "by_level": {str(lvl): {"items": len(s), **means(s)} for lvl, s in sorted(by_level.items())}})
    if len(scorers) == 2:
        a, b = ({s["n"]: s for s in data["scores"]} for data in scorers)
        ns = sorted(a)
        result["agreement"] = {
            "exact": {c: round(sum(a[n][c] == b[n][c] for n in ns) / len(ns), 3) for c in CRITERIA},
            "mean_abs_difference": {c: round(statistics.mean(abs(a[n][c] - b[n][c]) for n in ns), 3) for c in CRITERIA},
        }
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("draw")
    p.add_argument("tree")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--stratify", choices=("level",))
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_draw)
    p = sub.add_parser("score")
    p.add_argument("packet")
    p.add_argument("scores")
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("report")
    p.add_argument("packet")
    p.add_argument("scores", nargs="+")
    p.set_defaults(func=cmd_report)
    args = parser.parse_args()
    if args.command == "report" and len(args.scores) > 2:
        parser.error("report takes one or two score files")
    args.func(args)


if __name__ == "__main__":
    main()
