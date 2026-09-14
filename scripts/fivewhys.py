#!/usr/bin/env python3
"""Five Whys run manager.

A run takes one or more inputs. Each input is asked "why?" and answered with
`breadth` reasons, and every reason is asked again, `depth` levels deep (1 to 5).
Generation is split into agent-sized fragments: root agents write levels
1..split for a group of inputs, and one branch agent per level-`split` reason
writes the levels beneath it. This script owns everything deterministic:

  parse     split raw /five-whys arguments (stdin) into options and inputs
  init      create a run (inputs on stdin, one per line) and print its size estimate
  plan      list the next wave of missing fragments, each with a dispatch prompt
  status    report done, missing and stuck fragments
  check     validate one fragment against its expected shape
  assemble  merge fragments into five-whys.json plus index.md and hygiene.json
  show      print a subtree, the top levels, or a random sample, with ancestor chains

Run metadata lives in <run>/run.json and fragments in <run>/fragments/.
Nothing here ranks, prunes or summarizes reasons; hygiene flags (hygiene.py) are mechanical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
from hygiene import hygiene  # noqa: E402

SCHEMA = "five-whys/3"
AGENT = "five-whys:why-expander"
PRESETS = {"full": (5, 5), "smoke": (3, 3)}
SMOKE_SPLIT = 1  # the smoke preset keeps a root and branches, so it rehearses both kinds of dispatch
MAX_DEPTH = 5
FRAGMENT_REASONS = 155  # the most reasons one agent writes: a 5-wide, 3-deep branch, as measured
MODELS = ("inherit", "sonnet", "opus", "haiku")
MAX_PARALLEL = 5  # default wave size, well under Claude Code's cap
PLATFORM_PARALLEL_CAP = 20  # Claude Code runs at most 20 subagents at once by default
MAX_ATTEMPTS = 3
CONFIRM_AGENTS = 5  # runs needing more agents than this ask the user before dispatching
READ_WINDOW_BYTES = 48_000  # Read accepted about 64 KB of five-whys.json and rejected about 89 KB

# Agent tokens are estimated as a range from two runs measured with
# docs/self-improvement/usage.py (2026-09-13, claude-opus-5):
# - High: the v0.2.0 full run on its own rating, dispatched from an interactive
#   session in this repository. Agents inherited about 21k tokens of session
#   context and read local files as evidence. Root 44.1k for 30 reasons;
#   branches mean 63.1k for 155 reasons.
# - Low: a root and one branch dispatched from headless claude -p, on a problem
#   naming no files, in a clean directory. Agents inherited about 4.6k tokens
#   and read only their prompt. Root 11.3k; branch 23.6k.
# A later v0.3.0 full run, headless in this repository (4.9k inherited, files
# read), totalled 0.97M, inside the range. The assembled v0.2.0 file held 38
# tokens per reason.
MEASURED = {"version": "0.2.0", "date": "2026-09-13", "model": "claude-opus-5"}
AGENT_OVERHEAD_TOKENS = 39_600
TOKENS_PER_REASON = 152
AGENT_OVERHEAD_TOKENS_LOW = 8_400
TOKENS_PER_REASON_LOW = 98
OUTPUT_TOKENS_PER_REASON = 38

# Options /five-whys accepts. "init" is the init flag an option becomes; None means
# the skill consumes it. The README and SKILL.md document exactly these.
OPTIONS = [
    {"flag": "--smoke", "value": None, "init": "--preset"},
    {"flag": "--model", "value": "NAME", "init": "--model"},
    {"flag": "--breadth", "value": "N", "init": "--breadth"},
    {"flag": "--depth", "value": "N", "init": "--depth"},
    {"flag": "--split", "value": "N", "init": "--split"},
    {"flag": "--max-parallel", "value": "N", "init": "--max-parallel"},
    {"flag": "--context-file", "value": "PATH", "init": "--context-file"},
    {"flag": "--base", "value": "DIR", "init": "--base"},
    {"flag": "--yes", "value": None, "init": None},
    {"flag": "--resume", "value": "RUN_DIR", "init": None},
]


def plugin_version() -> str:
    try:
        manifest = SCRIPT.parents[1] / ".claude-plugin" / "plugin.json"
        return json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- shape


def reasons(breadth: int, levels: int) -> int:
    return sum(breadth**level for level in range(1, levels + 1))


def default_split(breadth: int, depth: int) -> int:
    """Levels a root agent writes: all of them when one agent holds an input's whole tree,
    otherwise the fewest that keep every branch within FRAGMENT_REASONS."""
    if reasons(breadth, depth) <= FRAGMENT_REASONS:
        return depth
    for split in range(1, depth):
        if reasons(breadth, depth - split) <= FRAGMENT_REASONS and reasons(breadth, split) <= FRAGMENT_REASONS:
            return split
    return max(1, depth // 2)


def shape_of(meta: dict) -> tuple[int, int, int]:
    shape = meta["shape"]
    return shape["breadth"], shape["depth"], shape["split"]


def root_groups(inputs: int, breadth: int, split: int) -> list[tuple[int, int]]:
    """(first, last) input numbers per root agent, packing inputs up to FRAGMENT_REASONS reasons."""
    size = max(1, FRAGMENT_REASONS // reasons(breadth, split))
    return [(first, min(first + size - 1, inputs)) for first in range(1, inputs + 1, size)]


def group_id(first: int, last: int) -> str:
    return f"roots-{first}" if first == last else f"roots-{first}-{last}"


def group_range(name: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"roots-(\d+)(?:-(\d+))?(?:\.json)?", name)
    return (int(match.group(1)), int(match.group(2) or match.group(1))) if match else None


def agent_count(breadth: int, depth: int, split: int, inputs: int = 1) -> int:
    return len(root_groups(inputs, breadth, split)) + (inputs * breadth**split if split < depth else 0)


def estimate(breadth: int, depth: int, split: int, inputs: int = 1) -> dict:
    agents, total = agent_count(breadth, depth, split, inputs), inputs * reasons(breadth, depth)
    return {
        "inputs": inputs,
        "agents": agents,
        "reasons": total,
        "agent_tokens_low": agents * AGENT_OVERHEAD_TOKENS_LOW + total * TOKENS_PER_REASON_LOW,
        "agent_tokens": agents * AGENT_OVERHEAD_TOKENS + total * TOKENS_PER_REASON,
        "output_tokens": total * OUTPUT_TOKENS_PER_REASON,
        "basis": f"range from two {MEASURED['model']} runs measured on {MEASURED['date']}: the low end is a "
                 "headless session on a problem naming no local files; the high end (agent_tokens) is the "
                 f"v{MEASURED['version']} self-run dispatched from an interactive session with many tools loaded, "
                 "where agents inherited about 21k tokens of context and read files as evidence. The dispatching "
                 "session's context drives the base cost. Each figure sums agents' reported totals; context "
                 "re-read on every turn is billed on top, mostly as cache reads.",
    }


# ---------------------------------------------------------------- invocation

LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\(?\d{1,3}[.)])\s+")
INLINE_NUMBER = re.compile(r"(?:^|\s)\(?\d{1,3}[.)]\s")


def split_inputs(text: str) -> list[str]:
    """One input per non-empty line, with list markers such as '- ', '* ' or '2. ' removed."""
    stripped = (LIST_MARKER.sub("", line).strip() for line in text.splitlines())
    return [line for line in stripped if line]


def input_hints(text: str, inputs: list[str]) -> list[str]:
    """Signs that the lines may not be the inputs the user meant; the skill asks when any appear."""
    lines = [line for line in text.splitlines() if line.strip()]
    hints = []
    if len(inputs) == 1 and len(INLINE_NUMBER.findall(lines[0])) >= 2:
        hints.append("one line holds a numbered list, so it may be several inputs")
    for above, below in zip(lines, lines[1:]):
        if not (LIST_MARKER.match(above) or LIST_MARKER.match(below)) \
                and not re.search(r"[.!?:;)\]\"'`]\s*$", above) and re.match(r"\s*[a-z]", below):
            hints.append("a line runs on into the next, so these lines may be one input")
            break
    return hints


def parse_invocation(text: str) -> dict:
    """Split leading options from the inputs, exactly as SKILL.md documents."""
    by_flag = {option["flag"]: option for option in OPTIONS}
    rest, given, errors, notes = text.strip(), {}, [], []
    while rest.startswith("--"):
        match = re.match(r"(\S+)\s*", rest)
        token, rest = match.group(1), rest[match.end():]
        if token == "--":
            break
        flag, _, inline = token.partition("=")
        option = by_flag.get(flag)
        if option is None:
            errors.append(f"unknown option {flag}; options: {', '.join(by_flag)}")
            continue
        value = True
        if option["value"]:
            if inline:
                value = inline
            else:
                quoted = re.match(r"""(["'])(.*?)\1\s*""", rest, re.S) or re.match(r"(\S+)\s*", rest)
                if not quoted or rest.startswith("--"):
                    errors.append(f"{flag} needs a value ({option['value']})")
                    continue
                value, rest = quoted.group(quoted.lastindex), rest[quoted.end():]
        if flag in given:
            errors.append(f"{flag} given twice")
        given[flag] = value
    problem = rest.strip()
    inputs = [] if "--resume" in given else split_inputs(problem)

    for flag in ("--breadth", "--split", "--max-parallel"):
        if flag in given and not (str(given[flag]).isdigit() and int(given[flag]) >= 1):
            errors.append(f"{flag} must be a whole number of at least 1")
    if "--depth" in given and not (str(given["--depth"]).isdigit() and 1 <= int(given["--depth"]) <= MAX_DEPTH):
        errors.append(f"--depth must be a whole number from 1 to {MAX_DEPTH}")
    if "--model" in given and given["--model"] not in MODELS:
        errors.append(f"--model must be one of {', '.join(MODELS)}")
    if "--context-file" in given and not Path(given["--context-file"]).is_file():
        errors.append(f"--context-file {given['--context-file']} does not exist")
    if "--smoke" in given and ({"--breadth", "--depth"} & set(given)):
        notes.append("--breadth/--depth override the smoke preset's 3x3 shape")
    if "--resume" in given:
        others = set(given) - {"--resume", "--yes", "--max-parallel"}
        if others:
            errors.append(f"--resume continues an existing run and takes no {', '.join(sorted(others))}")
        if problem:
            errors.append("--resume takes no inputs")
        if not (Path(given["--resume"]) / "run.json").is_file():
            errors.append(f"--resume {given['--resume']} is not a five-whys run directory")
    elif not inputs:
        errors.append("no input after the options")

    plan_args = ["--max-parallel", str(given["--max-parallel"])] if "--resume" in given and "--max-parallel" in given else []
    init_args = []
    for flag, value in given.items():
        target = by_flag[flag]["init"]
        if flag == "--smoke":
            init_args += ["--preset", "smoke"]
        elif target:
            init_args += [target, str(value)]
    return {
        "script": str(SCRIPT),  # later skill steps use this absolute path, never a relative one
        "problem": problem,
        "inputs": inputs,
        "input_hints": input_hints(problem, inputs) if inputs else [],
        "options": given,
        "init_flags": "" if "--resume" in given else shlex.join(init_args),
        "plan_flags": shlex.join(plan_args),
        "yes": "--yes" in given,
        "resume": given.get("--resume"),
        "errors": errors,
        "notes": notes,
    }


# ---------------------------------------------------------------- validation


def validate(nodes, breadth: int, depth: int, label: str = "") -> list[str]:
    """Return shape errors for `depth` nested levels of `breadth` reasons each."""
    where = f"item {label}'s whys" if label else "top-level whys"
    if not isinstance(nodes, list):
        return [f"{where}: must be a list, got {type(nodes).__name__}"]
    errors = []
    if len(nodes) != breadth:
        errors.append(f"{where}: expected {breadth} reasons, got {len(nodes)}")
    for i, node in enumerate(nodes, 1):
        here = f"{label}.{i}" if label else str(i)
        if not isinstance(node, dict):
            errors.append(f"item {here}: expected an object")
            continue
        reason = node.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"item {here}: reason missing or empty")
        children = node.get("whys")
        if depth > 1:
            errors.extend(validate(children, breadth, depth - 1, here))
        elif children:
            errors.append(f"item {here}: deepest reasons must not have whys")
    return errors


def load_fragment(path: Path, breadth: int, depth: int):
    """Return (whys or None, assumptions, errors).

    A branch fragment is {"whys": [...]}. A root group, named roots-A-B.json, is
    {"inputs": [{"whys": [...]}, ...]} with one entry per input from A to B, and its
    whys come back as one list per input.
    """
    if not path.exists():
        return None, [], [f"{path.name}: missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [], [f"{path.name}: invalid JSON ({exc})"]
    span = group_range(path.name)
    if span:
        first, last = span
        items = data.get("inputs") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return None, [], [f'{path.name}: top level must be {{"inputs": [{{"whys": [...]}}, ...]}}']
        errors, whys = [], []
        if len(items) != last - first + 1:
            errors.append(f"inputs: expected {last - first + 1} inputs, got {len(items)}")
        for k, item in enumerate(items):
            if not isinstance(item, dict) or "whys" not in item:
                errors.append(f'input {first + k}: expected an object with "whys"')
                continue
            errors += [f"input {first + k}: {e}" for e in validate(item["whys"], breadth, depth)]
            whys.append(item["whys"])
    else:
        if not isinstance(data, dict) or "whys" not in data:
            return None, [], [f'{path.name}: top level must be {{"whys": [...]}}']
        errors, whys = validate(data["whys"], breadth, depth), data["whys"]
    assumptions = data.get("assumptions", [])
    if not (isinstance(assumptions, list) and all(isinstance(a, str) for a in assumptions)):
        errors.append("assumptions: must be a list of strings")
    if errors:
        return None, [], [f"{path.name}: {e}" for e in errors]
    return whys, [a.strip() for a in assumptions if a.strip()], []


# ---------------------------------------------------------------- run layout


def read_run(run: Path) -> dict:
    path = run / "run.json"
    if not path.exists():
        sys.exit(f"not a five-whys run directory: {run}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("schema") != SCHEMA:
        sys.exit(f"{run} was created by an older five-whys ({meta.get('plugin_version', 'before 0.3.0')}), "
                 "whose fragments are laid out differently. Finish it with that version, or start a new run.")
    meta.setdefault("attempts", {})
    return meta


def write_run(run: Path, meta: dict) -> None:
    (run / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def root_path(run: Path, gid: str) -> Path:
    return run / "fragments" / f"{gid}.json"


def branch_path(run: Path, node_id: str) -> Path:
    return run / "fragments" / f"branch-{node_id}.json"


def fragment_name(task_id: str) -> str:
    return f"{task_id}.json" if task_id.startswith("roots-") else f"branch-{task_id}.json"


def groups_of(meta: dict) -> list[tuple[int, int]]:
    breadth, _, split = shape_of(meta)
    return root_groups(len(meta["inputs"]), breadth, split)


def load_roots(run: Path, meta: dict):
    """Return ({input number: its levels 1..split}, {group id: errors} for invalid groups, assumptions)."""
    breadth, _, split = shape_of(meta)
    roots, problems, assumptions = {}, {}, {}
    for first, last in groups_of(meta):
        gid = group_id(first, last)
        whys, notes, errors = load_fragment(root_path(run, gid), breadth, split)
        if whys is None:
            problems[gid] = errors
            continue
        for k, nodes in enumerate(whys):
            roots[first + k] = nodes
        if notes:
            assumptions[gid] = notes
    return roots, problems, assumptions


def walk(nodes, prefix: str = "", depth: int = 1, parent: str | None = None):
    """Yield (id, depth, parent_id, node) in document order."""
    for i, node in enumerate(nodes, 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        yield node_id, depth, parent, node
        yield from walk(node.get("whys") or [], node_id, depth + 1, node_id)


def frontier(nodes, split: int, prefix: str = "", chain: tuple = (), depth: int = 1):
    """Yield (id, chain of (id, reason)) for every level-`split` node."""
    for i, node in enumerate(nodes, 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        here = chain + ((node_id, node["reason"].strip()),)
        if depth == split:
            yield node_id, here
        else:
            yield from frontier(node["whys"], split, node_id, here, depth + 1)


def node_at(nodes, path: str) -> dict:
    node = {}
    for step in path.split("."):
        node = nodes[int(step) - 1]
        nodes = node.get("whys") or []
    return node


def flatten(nodes, prefix: str = "", depth: int = 1, parent: str | None = None) -> list[dict]:
    return [{"id": i, "depth": d, "parent": p, "reason": n["reason"].strip()}
            for i, d, p, n in walk(nodes, prefix, depth, parent)]


# ---------------------------------------------------------------- prompts


def whys_example(breadth: int, levels: int) -> str:
    inner = '{"reason": "..."}'
    for _ in range(levels - 1):
        inner = '{"reason": "...", "whys": [' + inner + f", ... x{breadth}]}}"
    return "[" + inner + f", ... x{breadth}]"


def shape_example(breadth: int, levels: int, inputs: int | None = None) -> str:
    whys = whys_example(breadth, levels)
    if inputs is None:
        return '{"assumptions": ["..."], "whys": ' + whys + "}"
    return '{"assumptions": ["..."], "inputs": [{"whys": ' + whys + "}" + f", ... x{inputs}]}}"


def check_command(fragment: Path, breadth: int, levels: int) -> str:
    return f"python3 {SCRIPT} check {fragment} --breadth {breadth} --depth {levels}"


def output_section(fragment: Path, breadth: int, levels: int, total: int, example: str, top_note: str = "") -> list[str]:
    return [
        "",
        f"That is {total} reasons, roughly {total * OUTPUT_TOKENS_PER_REASON:,} "
        "output tokens with the JSON. That size is expected: keep every reason a full, specific sentence.",
        "Write them as JSON to:",
        str(fragment),
        "",
        f"Shape (every whys list has exactly {breadth} items{top_note}; assumptions is optional):",
        example,
        "",
        "Then run:",
        check_command(fragment, breadth, levels),
        f"Repair and re-check until it prints OK, at most {MAX_ATTEMPTS} fix cycles.",
    ]


def context_lines(meta: dict) -> list[str]:
    return ["", "Context from the user:", meta["context"]] if meta.get("context") else []


def root_prompt(meta: dict, first: int, last: int, fragment: Path) -> str:
    breadth, depth, split = shape_of(meta)
    count, inputs = last - first + 1, meta["inputs"]
    which = f"input {first}" if count == 1 else f"inputs {first}-{last}"
    lines = [f"Five Whys — ROOT expansion of {which} of {len(inputs)} (levels 1-{split} of {depth}).", ""]
    lines += [f"Input {k}: {inputs[k - 1]}" for k in range(first, last + 1)]
    lines += context_lines(meta)
    lines += ["", "Build these levels" + (" for EACH input separately:" if count > 1 else ":"),
              f'- Level 1: {breadth} distinct reasons answering "Why does this happen?" about the input']
    if split > 1:
        lines.append(f'- Levels 2-{split}: for EACH reason above, {breadth} distinct reasons '
                     'answering "Why <that reason>?"')
    lines.append(f"- Stop after level {split}; level-{split} reasons have no whys in this file.")
    top_note = f"; inputs has one entry per input above, {count} in all, in the order listed"
    return "\n".join(lines + output_section(fragment, breadth, split, count * reasons(breadth, split),
                                            shape_example(breadth, split, count), top_note))


def branch_prompt(meta: dict, k: int, chain: tuple, fragment: Path, written: list) -> str:
    breadth, depth, split = shape_of(meta)
    node_id, reason = chain[-1]
    first = split + 1
    lines = [f"Five Whys — BRANCH expansion of node {node_id} (levels {first}-{depth} of {depth}).", "",
             f"Input {k}: {meta['inputs'][k - 1]}"]
    lines += context_lines(meta)
    lines += [""] + [f"Why level {level} (id {cid}): {text}" for level, (cid, text) in enumerate(chain, 1)]
    own = {cid for cid, _ in chain}
    others = [(cid, text) for cid, text in written if cid not in own]
    if others:
        lines += ["", "Reasons already written for other parts of this input's tree. Do not reproduce these causes; "
                      "go deeper on your own node instead:"]
        lines += [f"- {cid}: {text}" for cid, text in others]
    lines += ["", f"Expand node {node_id} into levels {first}-{depth}:",
              f'- Level {first}: {breadth} distinct reasons answering "Why: {reason}"']
    if depth > first:
        lines.append(f"- Each further level: for EACH reason above it, {breadth} distinct reasons "
                     'answering "Why <that reason>?"')
    lines.append(f"- Stop after level {depth}; level-{depth} reasons have no whys.")
    top_note = f"; the top-level whys are the level-{first} reasons"
    levels = depth - split
    return "\n".join(lines + output_section(fragment, breadth, levels, reasons(breadth, levels),
                                            shape_example(breadth, levels), top_note))


def read_plan(lines: list[str], budget: int = READ_WINDOW_BYTES) -> list[tuple[int, int]]:
    """(offset, limit) windows covering every line, each under `budget` bytes."""
    windows, start, size = [], 1, 0
    for n, line in enumerate(lines, 1):
        cost = len(line.encode("utf-8")) + 1
        if size and size + cost > budget:
            windows.append((start, n - start))
            start, size = n, 0
        size += cost
    windows.append((start, len(lines) - start + 1))
    return windows


# ---------------------------------------------------------------- commands


def cmd_parse(args) -> None:
    result = parse_invocation(sys.stdin.read())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["errors"]:
        sys.exit(1)


def cmd_init(args) -> None:
    inputs = split_inputs(sys.stdin.read())
    if not inputs:
        sys.exit("init: provide at least one input on stdin, one per line")
    breadth, depth = PRESETS[args.preset]
    smoke_shape = args.preset == "smoke" and args.breadth is None and args.depth is None
    breadth = args.breadth if args.breadth is not None else breadth
    depth = args.depth if args.depth is not None else depth
    if breadth < 1:
        sys.exit("init: breadth must be at least 1")
    if not 1 <= depth <= MAX_DEPTH:
        sys.exit(f"init: depth must be between 1 and {MAX_DEPTH}")
    split = args.split or (SMOKE_SPLIT if smoke_shape else default_split(breadth, depth))
    if not 1 <= split <= depth:
        sys.exit(f"init: split must be between 1 and {depth}")
    if not 1 <= args.max_parallel <= PLATFORM_PARALLEL_CAP:
        sys.exit(f"init: max-parallel must be between 1 and {PLATFORM_PARALLEL_CAP}")
    context = Path(args.context_file).read_text(encoding="utf-8").strip() if args.context_file else ""

    slug = re.sub(r"[^a-z0-9]+", "-", inputs[0].lower()).strip("-") or "problem"
    if len(inputs) > 1:
        slug = f"{len(inputs)}-inputs-{slug}"
    slug = slug[:40].strip("-")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run = (Path(args.base) / f"{stamp}-{slug}").resolve()
    suffix = 2
    while run.exists():
        run = run.with_name(f"{stamp}-{slug}-{suffix}")
        suffix += 1
    (run / "fragments").mkdir(parents=True)
    ignore = Path(args.base) / ".gitignore"
    if not ignore.exists():  # problem statements and reasons can be sensitive
        ignore.write_text("# Five Whys runs can hold sensitive details; keep them out of git.\n*\n", encoding="utf-8")

    size = estimate(breadth, depth, split, len(inputs))
    meta = {
        "schema": SCHEMA,
        "inputs": inputs,
        "created": now_iso(),
        "plugin_version": plugin_version(),
        "options": sys.argv[2:],
        "shape": {"breadth": breadth, "depth": depth, "split": split},
        "model": args.model,
        "max_parallel": args.max_parallel,
        "estimate": size,
        "attempts": {},
    }
    if context:
        meta["context"] = context
    write_run(run, meta)
    print(json.dumps({"run": str(run), "inputs": len(inputs), "shape": meta["shape"], "model": args.model,
                      "max_parallel": args.max_parallel, "plugin_version": meta["plugin_version"],
                      "estimate": size, "confirm": size["agents"] > CONFIRM_AGENTS}, indent=2))


def cmd_plan(args) -> None:
    run = Path(args.run).resolve()
    meta = read_run(run)
    breadth, depth, split = shape_of(meta)
    only = {i.strip() for i in args.only.split(",")} if args.only else None
    attempts = meta["attempts"]
    if args.max_parallel:  # a resumed run can change its wave size
        if not 1 <= args.max_parallel <= PLATFORM_PARALLEL_CAP:
            sys.exit(f"plan: max-parallel must be between 1 and {PLATFORM_PARALLEL_CAP}")
        meta["max_parallel"] = args.max_parallel
        write_run(run, meta)

    roots, root_errors, _ = load_roots(run, meta)
    pending = []
    for first, last in groups_of(meta):
        gid = group_id(first, last)
        if gid in root_errors:
            path = root_path(run, gid)
            pending.append({"id": gid, "fragment": str(path), "errors": root_errors[gid],
                            "prompt": root_prompt(meta, first, last, path)})
    if not root_errors and split < depth:
        for k in range(1, len(meta["inputs"]) + 1):
            branches = []
            for node_id, chain in frontier(roots[k], split, str(k)):
                path = branch_path(run, node_id)
                branch, _, errors = load_fragment(path, breadth, depth - split)
                branches.append((node_id, chain, path, branch, errors))
            # Later waves also see the first-level reasons of this input's branches that are already done.
            written = [(node_id, node["reason"].strip()) for node_id, _, _, node in walk(roots[k], str(k))]
            for node_id, _, _, branch, _ in branches:
                if branch is not None:
                    written += [(f"{node_id}.{i}", node["reason"].strip()) for i, node in enumerate(branch, 1)]
            for node_id, chain, path, branch, errors in branches:
                if branch is None and (not only or node_id in only):
                    pending.append({"id": node_id, "fragment": str(path), "errors": errors,
                                    "prompt": branch_prompt(meta, k, chain, path, written)})

    ready = [t for t in pending if attempts.get(t["id"], 0) < MAX_ATTEMPTS]
    stuck = [t for t in pending if attempts.get(t["id"], 0) >= MAX_ATTEMPTS]
    wave = ready[: meta["max_parallel"]]
    for task in wave:
        task["attempt"] = attempts.get(task["id"], 0) + 1
        task["model"] = None if meta["model"] == "inherit" else meta["model"]
        # Full prompts go to files so the orchestrating session only carries short pointers.
        prompt_file = run / "prompts" / f"{task['id']}.md"
        prompt_file.parent.mkdir(exist_ok=True)
        prompt_file.write_text(task["prompt"] + "\n", encoding="utf-8")
        task["prompt_file"] = str(prompt_file)
        task["prompt"] = f"Read {prompt_file} and carry out the Five Whys task it describes, exactly as written."
    if args.record and wave:
        for task in wave:
            attempts[task["id"]] = task["attempt"]
        waves = meta.setdefault("waves", [])  # start times, so each wave's wall clock can be measured
        waves.append({"wave": len(waves) + 1, "at": now_iso(), "ids": [t["id"] for t in wave],
                      "max_parallel": meta["max_parallel"]})
        write_run(run, meta)

    state = ("root" if root_errors else "branches") if wave else ("stuck" if stuck else "ready")
    print(json.dumps({
        "run": str(run),
        "state": state,
        "agent": AGENT,
        "tasks": wave,
        "waiting": [t["id"] for t in ready[len(wave):]],
        "stuck": [{"id": t["id"], "attempts": attempts.get(t["id"], 0), "errors": t["errors"]} for t in stuck],
    }, indent=2, ensure_ascii=False))


def cmd_status(args) -> None:
    run = Path(args.run).resolve()
    meta = read_run(run)
    breadth, depth, split = shape_of(meta)
    inputs = len(meta["inputs"])
    roots, root_errors, _ = load_roots(run, meta)
    missing = list(root_errors)
    done = len(groups_of(meta)) - len(root_errors)
    if split < depth:
        for k in sorted(roots):
            for node_id, _ in frontier(roots[k], split, str(k)):
                if load_fragment(branch_path(run, node_id), breadth, depth - split)[0] is None:
                    missing.append(node_id)
                else:
                    done += 1
    print(json.dumps({
        "run": str(run),
        "inputs": inputs,
        "shape": meta["shape"],
        "model": meta["model"],
        "max_parallel": meta["max_parallel"],
        "plugin_version": meta.get("plugin_version", "unknown"),
        "installed_plugin_version": plugin_version(),
        "done": done,
        "total": agent_count(breadth, depth, split, inputs),
        "missing": missing,
        "stuck": [m for m in missing if meta["attempts"].get(m, 0) >= MAX_ATTEMPTS],
        "checks": read_checks(run),
        "waves": wave_timing(run, meta),
        "assembled": (run / "five-whys.json").exists(),
        "estimate": estimate(breadth, depth, split, inputs),
    }, indent=2))


def run_folder(fragment: Path) -> Path | None:
    folder = fragment.resolve().parent
    return folder.parent if folder.name == "fragments" and (folder.parent / "run.json").exists() else None


# Which rule a check error broke, so the log shows what agents get wrong, not just how often.
ERROR_KINDS = (
    ("input_count", r"expected \d+ inputs, got \d+"),
    ("count", r"expected \d+ reasons, got \d+"),
    ("missing_reason", r"reason missing or empty"),
    ("leaf_whys", r"deepest reasons must not have whys"),
    ("json", r"invalid JSON"),
    ("assumptions", r"assumptions: must be"),
    ("structure", r"top level must be|must be a list|expected an object"),
    ("missing_file", r": missing$"),
)


def error_kind(message: str) -> str:
    return next((kind for kind, pattern in ERROR_KINDS if re.search(pattern, message)), "other")


def log_check(fragment: Path, errors: list[str], warning_kinds: dict) -> None:
    # Only fragments inside a run directory are logged, so repair cycles are countable.
    run = run_folder(fragment)
    if run is None:
        return
    entry = {"fragment": fragment.name, "at": now_iso(), "ok": not errors,
             "errors": len(errors), "warnings": sum(warning_kinds.values())}
    if errors:
        entry["kinds"] = dict(Counter(map(error_kind, errors)))
    if warning_kinds:
        entry["warning_kinds"] = warning_kinds
    with open(run / "check-log.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")


def read_log(run: Path) -> list[dict]:
    log = run / "check-log.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_checks(run: Path) -> dict:
    checks = {}
    for entry in read_log(run):
        item = checks.setdefault(entry["fragment"], {"checks": 0, "failed": 0})
        item["checks"] += 1
        item["failed"] += 0 if entry["ok"] else 1
        for field in ("kinds", "warning_kinds"):  # summed across the fragment's checks
            for kind, count in entry.get(field, {}).items():
                bucket = item.setdefault(field, {})
                bucket[kind] = bucket.get(kind, 0) + count
    return checks


def wave_timing(run: Path, meta: dict) -> list[dict]:
    """Recorded waves; a wave finishes when its last fragment first checks OK after the wave began."""
    passes: dict[str, list] = {}
    for entry in read_log(run):
        if entry["ok"]:
            passes.setdefault(entry["fragment"], []).append(dt.datetime.fromisoformat(entry["at"]))
    timing = []
    for wave in meta.get("waves", []):
        start = dt.datetime.fromisoformat(wave["at"])
        firsts = [min((t for t in passes.get(fragment_name(i), []) if t >= start), default=None) for i in wave["ids"]]
        finished = None if any(t is None for t in firsts) else max(firsts)
        timing.append({**wave, "finished": finished.isoformat() if finished else None,
                       "seconds": int((finished - start).total_seconds()) if finished else None})
    return timing


def root_context(fragment: Path):
    """For a branch fragment inside a run: (node id, its input's root reasons as flat entries)."""
    run, match = run_folder(fragment), re.fullmatch(r"branch-(\d+(?:\.\d+)*)\.json", fragment.name)
    if run is None or not match:
        return None
    meta = read_run(run)
    roots, _, _ = load_roots(run, meta)
    node_id = match.group(1)
    k = int(node_id.split(".")[0])
    return (node_id, flatten(roots[k], str(k))) if k in roots else None


def cmd_check(args) -> None:
    fragment = Path(args.fragment)
    whys, _, errors = load_fragment(fragment, args.breadth, args.depth)
    if errors:
        log_check(fragment, errors, {})
        print("\n".join(errors[:25]))
        if len(errors) > 25:
            print(f"... and {len(errors) - 25} more errors")
        sys.exit(1)
    print("OK")

    span = group_range(fragment.name)
    context = None if span else root_context(fragment)

    def label(i):
        return i
    if span:  # a root group: ids start with the input number
        flat = [r for k, nodes in enumerate(whys, span[0]) for r in flatten(nodes, str(k))]
        flags = hygiene(flat, branch_level=2)
    elif context:  # compare against the real ancestors and the input's root reasons
        node_id, root_flat = context
        mine = flatten(whys, node_id, node_id.count(".") + 1, node_id)
        flags = hygiene(root_flat + mine, report={r["id"] for r in mine}, branch_level=2)
        prefix = node_id + "."

        def label(i):
            return i[len(prefix):] if i.startswith(prefix) else f"{i} (written by the root)"
    else:
        flags = hygiene(flatten(whys))
    warnings = [f"warning: items {', '.join(map(label, g['ids']))} repeat the same text" for g in flags["exact_duplicates"]]
    warnings += [f"warning: items {label(f['a'])} and {label(f['b'])} are near-duplicates (similarity {f['similarity']})"
                 for f in flags["near_duplicates"]]
    warnings += [f"warning: item {label(f['id'])} restates item {label(f['of'])}"
                 for f in flags["restates_parent"] + flags["restates_ancestor"]]
    warnings += [f"warning: item {label(f['id'])} has {f['words']} words; aim for about 20" for f in flags["over_length"]]
    kinds = {"exact": len(flags["exact_duplicates"]), "near": len(flags["near_duplicates"]),
             "restates": len(flags["restates_parent"]) + len(flags["restates_ancestor"]),
             "over_length": len(flags["over_length"])}
    log_check(fragment, [], {kind: count for kind, count in kinds.items() if count})
    if warnings:
        print("\n".join(warnings[:25]))
        print("Warnings never block. Fix them with Edit when that doesn't mean rewriting the fragment.")


def emit(nodes, prefix: str, depth: int, max_depth: int, out: list[str]) -> None:
    """One reason per line, indented by depth, so the file pages cleanly."""
    for i, node in enumerate(nodes, 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        record = {"id": node_id, "depth": depth, "reason": node["reason"].strip()}
        if node.get("missing"):
            record["missing"] = True
        head = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        comma = "" if i == len(nodes) else ","
        indent = " " * depth
        if depth < max_depth and node.get("whys"):
            out.append(f'{indent}{head[:-1]},"whys":[')
            emit(node["whys"], node_id, depth + 1, max_depth, out)
            out.append(f"{indent}]}}{comma}")
        else:
            out.append(f"{indent}{head}{comma}")


def cmd_assemble(args) -> None:
    run = Path(args.run).resolve()
    meta = read_run(run)
    breadth, depth, split = shape_of(meta)
    inputs = meta["inputs"]
    roots, root_errors, assumptions = load_roots(run, meta)
    if root_errors and not args.partial:
        sys.exit("cannot assemble; run plan and re-dispatch, or assemble --partial:\n"
                 + "\n".join(e for errs in root_errors.values() for e in errs))
    missing, problems = list(root_errors), []
    if split < depth:
        for k in sorted(roots):
            for node_id, _ in list(frontier(roots[k], split, str(k))):
                branch, notes, errs = load_fragment(branch_path(run, node_id), breadth, depth - split)
                target = node_at(roots[k], node_id.split(".", 1)[1])
                if branch is None:
                    if args.partial:
                        missing.append(node_id)
                        target["missing"] = True
                    else:
                        problems.extend(errs)
                    continue
                target["whys"] = branch
                if notes:
                    assumptions[node_id] = notes
    if problems:
        sys.exit("cannot assemble; run plan and re-dispatch, or assemble --partial:\n" + "\n".join(problems))

    flats = {k: flatten(roots[k], str(k)) for k in sorted(roots)}
    flat = [r for k in sorted(flats) for r in flats[k]]
    total = len(inputs) * reasons(breadth, depth)
    levels = []
    for level in range(1, depth + 1):
        at = [len(r["reason"].split()) for r in flat if r["depth"] == level]
        levels.append({"level": level, "reasons": len(at), "avg_words": round(sum(at) / len(at), 1) if at else 0})

    now = dt.datetime.now().astimezone()
    # From creation to the newest fragment, so assembling again later doesn't stretch it.
    finished = max((p.stat().st_mtime for p in (run / "fragments").glob("*.json")), default=None)
    try:
        duration = int(finished - dt.datetime.fromisoformat(meta["created"]).timestamp()) if finished else None
    except (KeyError, ValueError, TypeError):
        duration = None
    timing = wave_timing(run, meta)
    header = {
        "schema": SCHEMA,
        **({"context": meta["context"]} if meta.get("context") else {}),
        "created": meta.get("created"),
        "assembled": now.isoformat(timespec="seconds"),
        "duration_seconds": duration,
        "waves": [{"wave": w["wave"], "fragments": len(w["ids"]), "seconds": w["seconds"]} for w in timing],
        "plugin_version": meta.get("plugin_version", "unknown"),
        "input_count": len(inputs),
        "breadth": breadth,
        "depth": depth,
        "split": split,
        "model": meta["model"],
        "total_reasons": total,
        "present_reasons": len(flat),
        "complete": not missing,
        "missing_branches": missing,
        "levels": levels,
        **({"assumptions": assumptions} if assumptions else {}),
        "reading": "Each input's whys answer 'Why does this happen?' about that input; each reason's whys answer "
                   "'Why <that reason>?'. An id is the dotted path from the top and starts with the input number, "
                   "so 2.4.1 is the 1st reason under 2.4, which is the 4th reason about input 2. index.md lists "
                   "the inputs, their top levels and the Read windows for this file; hygiene.json holds "
                   "mechanical flags only.",
    }
    head = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    lines = [f'{head[:-1]},"inputs":[']
    for k, text in enumerate(inputs, 1):
        record = {"id": str(k), "depth": 0, "input": text, **({} if k in roots else {"missing": True})}
        top = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        comma = "" if k == len(inputs) else ","
        if k in roots:
            lines.append(f'{top[:-1]},"whys":[')
            emit(roots[k], str(k), 1, depth, lines)
            lines.append(f"]}}{comma}")
        else:
            lines.append(f"{top}{comma}")
    lines.append("]}")
    text = "\n".join(lines) + "\n"
    json.loads(text)  # guard: the hand-rolled layout must still be valid JSON
    out = run / "five-whys.json"
    out.write_text(text, encoding="utf-8")

    windows = read_plan(lines)
    listed = min(split, 2)
    count = f"{len(inputs)} input{'s' if len(inputs) != 1 else ''}"
    index = ["# Five Whys index", "",
             f"{count}, each asked why {depth} level(s) deep with {breadth} reasons per why: {total:,} reasons.", "",
             f"Settings: {breadth} wide x {depth} deep, root writes {split} level(s), model {meta['model']}"
             + f", waves of {meta['max_parallel']}"
             + (f" ({len(timing)} dispatched, {round(duration / 60)} min)" if timing and duration is not None else "")
             + f", plugin {header['plugin_version']}.", ""]
    if depth > listed:
        index += [f"Levels 1-{listed} of {depth} are listed. Print an input or a reason with everything beneath it:",
                  "", "```", f"python3 {SCRIPT} show {run} --id <id>", "```", ""]
    for k, text in enumerate(inputs, 1):
        index.append(f"- {k} [input] {text}" + ("" if k in roots else " (missing)"))
        index += [f"{'  ' * r['depth']}- {r['id']} {r['reason']}" + (" (branch missing)" if r["id"] in missing else "")
                  for r in flats.get(k, []) if r["depth"] <= listed]
    index += ["", "## Reading five-whys.json whole", "",
              f"Read these {len(windows)} windows in order; each stays under the Read tool's size limit:", ""]
    index += [f"- offset {offset}, limit {limit}" for offset, limit in windows]
    (run / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    flags = hygiene(flat, branch_level=2)
    (run / "hygiene.json").write_text(json.dumps(flags, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    checks = read_checks(run)
    totals = {"runs": sum(c["checks"] for c in checks.values()), "failed": sum(c["failed"] for c in checks.values())}
    size = out.stat().st_size
    meta.update({"assembled": header["assembled"], "duration_seconds": duration,
                 "output": {"bytes": size, "approx_tokens": size // 4, "lines": len(lines), "complete": not missing}, "checks": totals})
    write_run(run, meta)
    print(json.dumps({
        "file": str(out),
        "index": str(run / "index.md"),
        "hygiene": str(run / "hygiene.json"),
        "complete": not missing,
        "missing_branches": missing,
        "inputs": len(inputs),
        "present_reasons": len(flat),
        "total_reasons": total,
        "bytes": size,
        "approx_tokens": size // 4,
        "read_windows": len(windows),
        "duration_seconds": duration,
        "hygiene_counts": flags["counts"],
        "checks": totals,
    }, indent=2))


def cmd_show(args) -> None:
    path = Path(args.tree)
    if path.is_dir():
        path = path / "five-whys.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if "inputs" in data:  # inputs sit above the reasons at depth 0
        nodes = [{"id": i["id"], "depth": 0, "reason": f"[input] {i['input']}", "whys": i.get("whys", []),
                  "missing": i.get("missing")} for i in data["inputs"]]
        base = 0
    else:  # trees assembled before 0.3.0 start at the reasons
        nodes, base = data["whys"], 1
    if args.sample:
        chains = []

        def collect(level_nodes, chain):
            for node in level_nodes:
                if node["depth"] > 0:
                    chains.append(chain + [node])
                collect(node.get("whys", []), chain + [node])

        collect(nodes, [])
        for k, chain in enumerate(random.Random(args.seed).sample(chains, min(args.sample, len(chains)))):
            if k:
                print()
            for ancestor in chain[:-1]:
                print(f"^ {ancestor['id']}  {ancestor['reason']}")
            print(f"{chain[-1]['id']}  {chain[-1]['reason']}")
        return
    if args.id:
        chain = []
        try:
            for step in args.id.split("."):
                node = nodes[int(step) - 1]
                chain.append(node)
                nodes = node.get("whys", [])
        except (ValueError, IndexError):
            sys.exit(f"show: no node with id {args.id}")
        for ancestor in chain[:-1]:
            print(f"^ {ancestor['id']}  {ancestor['reason']}")
        nodes = [chain[-1]]

    def print_level(level_nodes, remaining):
        for node in level_nodes:
            marker = " (branch missing)" if node.get("missing") else ""
            print(f"{'  ' * (node['depth'] - base)}{node['id']}  {node['reason']}{marker}")
            if remaining != 1:
                print_level(node.get("whys", []), remaining - 1)

    print_level(nodes, args.levels or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="split raw /five-whys arguments (stdin) into options and inputs")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("init", help="create a run; inputs on stdin, one per line")
    p.add_argument("--base", default=".five-whys", help="parent directory for runs")
    p.add_argument("--preset", choices=sorted(PRESETS), default="full", help="full = 5x5, smoke = 3x3")
    p.add_argument("--breadth", type=int, help="reasons per why (overrides the preset)")
    p.add_argument("--depth", type=int, help=f"levels of why, 1 to {MAX_DEPTH} (overrides the preset)")
    p.add_argument("--split", type=int, help="levels written by root agents (default: sized to fit one agent)")
    p.add_argument("--model", choices=MODELS, default="inherit", help="model for the expander agents")
    p.add_argument("--max-parallel", type=int, default=MAX_PARALLEL, help="largest dispatch wave")
    p.add_argument("--context-file", help="file of user-supplied context included in every prompt")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="next wave of missing fragments with dispatch prompts")
    p.add_argument("run")
    p.add_argument("--record", action="store_true", help="count this wave as a dispatch attempt")
    p.add_argument("--only", help="comma-separated branch ids to plan (root groups are always planned first)")
    p.add_argument("--max-parallel", type=int, help="change the run's wave size, for example when resuming")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("status", help="done, missing and stuck fragments")
    p.add_argument("run")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check", help="validate one fragment")
    p.add_argument("fragment")
    p.add_argument("--depth", type=int, required=True)
    p.add_argument("--breadth", type=int, default=5)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("assemble", help="write five-whys.json, index.md and hygiene.json")
    p.add_argument("run")
    p.add_argument("--partial", action="store_true", help="assemble even with missing fragments, marking them")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("show", help="print a subtree or the top levels of an assembled tree")
    p.add_argument("tree", help="five-whys.json, or the run directory holding it")
    p.add_argument("--id", help="dotted id to show, starting with the input number, preceded by its ancestors")
    p.add_argument("--levels", type=int, help="levels to print, counting the shown node (default: all)")
    p.add_argument("--sample", type=int, help="print N randomly chosen reasons, each with its ancestor chain")
    p.add_argument("--seed", type=int, help="random seed for --sample, for repeatable spot checks")
    p.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
