#!/usr/bin/env python3
"""Five Whys run manager.

The tree is BRANCHING wide and DEPTH deep: every reason is asked "why?" and
answered with BRANCHING further reasons, DEPTH times over. Generation is split
into agent-sized fragments; this script owns everything deterministic:

  init      create a run directory (problem statement read from stdin)
  plan      list the fragments still missing, with a ready-to-dispatch prompt each
  check     validate one fragment file against its expected shape
  assemble  validate every fragment and write the final five-whys.json

Fragments:
  fragments/root.json         levels 1..ROOT_DEPTH
  fragments/branch-<id>.json  the levels below one level-ROOT_DEPTH node
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

BRANCHING = 5
DEPTH = 5
ROOT_DEPTH = 2
BRANCH_DEPTH = DEPTH - ROOT_DEPTH
SCHEMA = "five-whys/1"
SCRIPT = Path(__file__).resolve()
AGENT = "five-whys:why-expander"


def total_reasons(depth: int = DEPTH) -> int:
    return sum(BRANCHING**level for level in range(1, depth + 1))


# ---------------------------------------------------------------- validation


def validate(nodes, depth: int, where: str = "whys") -> list[str]:
    """Return shape errors for a list of `depth` nested levels of reasons."""
    if not isinstance(nodes, list):
        return [f"{where}: expected a list, got {type(nodes).__name__}"]
    errors = []
    if len(nodes) != BRANCHING:
        errors.append(f"{where}: expected {BRANCHING} reasons, got {len(nodes)}")
    for i, node in enumerate(nodes):
        here = f"{where}[{i}]"
        if not isinstance(node, dict):
            errors.append(f"{here}: expected an object")
            continue
        reason = node.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{here}.reason: missing or empty")
        children = node.get("whys")
        if depth > 1:
            errors.extend(validate(children, depth - 1, f"{here}.whys"))
        elif children:
            errors.append(f"{here}.whys: leaf reasons must not have whys")
    return errors


def load_fragment(path: Path, depth: int) -> tuple[list | None, list[str]]:
    if not path.exists():
        return None, [f"{path.name}: missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"{path.name}: invalid JSON ({exc})"]
    if not isinstance(data, dict) or "whys" not in data:
        return None, [f'{path.name}: top level must be {{"whys": [...]}}']
    errors = validate(data["whys"], depth)
    return (None if errors else data["whys"]), [f"{path.name}: {e}" for e in errors]


# ---------------------------------------------------------------- run layout


def read_run(run: Path) -> dict:
    meta = run / "run.json"
    if not meta.exists():
        sys.exit(f"not a five-whys run directory: {run}")
    return json.loads(meta.read_text(encoding="utf-8"))


def root_path(run: Path) -> Path:
    return run / "fragments" / "root.json"


def branch_path(run: Path, node_id: str) -> Path:
    return run / "fragments" / f"branch-{node_id}.json"


def frontier(nodes: list, prefix: str = "", chain: tuple = (), depth: int = 1):
    """Yield (id, chain-of-reasons) for every node at level ROOT_DEPTH."""
    for i, node in enumerate(nodes, 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        here = chain + ((node_id, node["reason"]),)
        if depth == ROOT_DEPTH:
            yield node_id, here
        else:
            yield from frontier(node["whys"], node_id, here, depth + 1)


def shape_example(depth: int) -> str:
    inner = '{"reason": "..."}'
    for _ in range(depth - 1):
        inner = '{"reason": "...", "whys": [' + inner + f", ... x{BRANCHING}]}}"
    return '{"whys": [' + inner + f", ... x{BRANCHING}]}}"


def root_prompt(problem: str, fragment: Path) -> str:
    return f"""Five Whys — ROOT expansion.

Problem: {problem}

Build levels 1-{ROOT_DEPTH} of the tree:
- Level 1: {BRANCHING} distinct reasons answering "Why does this problem occur?"
- Level 2: for EACH level-1 reason, {BRANCHING} distinct reasons answering "Why <that reason>?"

That is {total_reasons(ROOT_DEPTH)} reasons. Write them as JSON to:
{fragment}

Shape (every list has exactly {BRANCHING} items):
{shape_example(ROOT_DEPTH)}

Then run:
python3 {SCRIPT} check {fragment} --depth {ROOT_DEPTH}
Fix and rewrite the file until it prints OK."""


def branch_prompt(problem: str, chain: tuple, fragment: Path) -> str:
    node_id, reason = chain[-1]
    lines = "\n".join(
        f"Why level {level} (id {cid}): {text}" for level, (cid, text) in enumerate(chain, 1)
    )
    levels = f"{ROOT_DEPTH + 1}-{DEPTH}"
    return f"""Five Whys — BRANCH expansion of node {node_id}.

Problem: {problem}
{lines}

Expand node {node_id} into levels {levels}:
- Level {ROOT_DEPTH + 1}: {BRANCHING} distinct reasons answering "Why {reason}"
- Each further level: for EACH reason above it, {BRANCHING} distinct reasons answering "Why <that reason>?"
- Stop after level {DEPTH}; level-{DEPTH} reasons have no whys.

That is {total_reasons(BRANCH_DEPTH)} reasons. Write them as JSON to:
{fragment}

Shape (every list has exactly {BRANCHING} items; the top-level whys are the level-{ROOT_DEPTH + 1} reasons):
{shape_example(BRANCH_DEPTH)}

Then run:
python3 {SCRIPT} check {fragment} --depth {BRANCH_DEPTH}
Fix and rewrite the file until it prints OK."""


# ---------------------------------------------------------------- commands


def cmd_init(args) -> None:
    problem = sys.stdin.read().strip()
    if not problem:
        sys.exit("init: provide the problem statement on stdin")
    slug = re.sub(r"[^a-z0-9]+", "-", problem.lower()).strip("-")[:40].strip("-") or "problem"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run = (Path(args.base) / f"{stamp}-{slug}").resolve()
    (run / "fragments").mkdir(parents=True)
    meta = {
        "schema": SCHEMA,
        "problem": problem,
        "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "branching": BRANCHING,
        "depth": DEPTH,
    }
    (run / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(run)


def cmd_plan(args) -> None:
    run = Path(args.run).resolve()
    problem = read_run(run)["problem"]
    root, root_errors = load_fragment(root_path(run), ROOT_DEPTH)
    tasks = []
    if root is None:
        state = "root"
        tasks.append({
            "id": "root",
            "fragment": str(root_path(run)),
            "errors": root_errors,
            "prompt": root_prompt(problem, root_path(run)),
        })
    else:
        for node_id, chain in frontier(root):
            path = branch_path(run, node_id)
            branch, errors = load_fragment(path, BRANCH_DEPTH)
            if branch is None:
                tasks.append({
                    "id": node_id,
                    "fragment": str(path),
                    "errors": errors,
                    "prompt": branch_prompt(problem, chain, path),
                })
        state = "branches" if tasks else "ready"
    print(json.dumps({"run": str(run), "state": state, "agent": AGENT, "tasks": tasks},
                     indent=2, ensure_ascii=False))


def cmd_check(args) -> None:
    _, errors = load_fragment(Path(args.fragment), args.depth)
    if errors:
        print("\n".join(errors[:25]))
        if len(errors) > 25:
            print(f"... and {len(errors) - 25} more errors")
        sys.exit(1)
    print("OK")


def emit(nodes: list, prefix: str, depth: int, out: list[str]) -> None:
    """One reason per line, indented by depth, so the file pages cleanly."""
    for i, node in enumerate(nodes, 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        head = json.dumps({"id": node_id, "depth": depth, "reason": node["reason"].strip()},
                          ensure_ascii=False, separators=(",", ":"))
        comma = "" if i == len(nodes) else ","
        indent = " " * depth
        if depth < DEPTH:
            out.append(f'{indent}{head[:-1]},"whys":[')
            emit(node["whys"], node_id, depth + 1, out)
            out.append(f"{indent}]}}{comma}")
        else:
            out.append(f"{indent}{head}{comma}")


def cmd_assemble(args) -> None:
    run = Path(args.run).resolve()
    meta = read_run(run)
    root, errors = load_fragment(root_path(run), ROOT_DEPTH)
    if root is None:
        sys.exit("\n".join(errors))
    problems = []
    for node_id, _ in frontier(root):
        branch, errors = load_fragment(branch_path(run, node_id), BRANCH_DEPTH)
        if branch is None:
            problems.extend(errors)
            continue
        node = root
        for step in node_id.split("."):
            node = node[int(step) - 1] if isinstance(node, list) else node["whys"][int(step) - 1]
        node["whys"] = branch
    if problems:
        sys.exit("cannot assemble; run `plan` and re-dispatch:\n" + "\n".join(problems))

    header = {
        "schema": SCHEMA,
        "problem": meta["problem"],
        "created": meta["created"],
        "assembled": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "branching": BRANCHING,
        "depth": DEPTH,
        "total_reasons": total_reasons(),
        "reading": "Top-level whys answer 'Why does the problem occur?'. Each node's whys answer "
                   "'Why <that node's reason>?'. An id is the dotted path from the top, so "
                   "2.4.1 is the 1st reason for 2.4, which is the 4th reason for 2.",
    }
    head = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    lines = [f'{head[:-1]},"whys":[']
    emit(root, "", 1, lines)
    lines.append("]}")
    text = "\n".join(lines) + "\n"
    json.loads(text)  # guard: the hand-rolled layout must still be valid JSON

    out = run / "five-whys.json"
    out.write_text(text, encoding="utf-8")
    size = out.stat().st_size
    print(json.dumps({
        "file": str(out),
        "total_reasons": total_reasons(),
        "lines": len(lines),
        "bytes": size,
        "approx_tokens": size // 4,
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a run; problem statement on stdin")
    p.add_argument("--base", default=".five-whys", help="parent directory for runs")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="list missing fragments with dispatch prompts")
    p.add_argument("run")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("check", help="validate one fragment")
    p.add_argument("fragment")
    p.add_argument("--depth", type=int, required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("assemble", help="write the final five-whys.json")
    p.add_argument("run")
    p.set_defaults(func=cmd_assemble)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
