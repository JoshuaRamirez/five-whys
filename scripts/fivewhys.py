#!/usr/bin/env python3
"""Five Whys run manager.

Every reason is asked "why?" and answered with `breadth` further reasons, `depth`
levels deep. Generation is split into agent-sized fragments: one root agent
writes levels 1..split, and one branch agent per level-`split` reason writes the
levels beneath it. This script owns everything deterministic:

  parse     split raw /five-whys arguments (stdin) into options and the problem
  init      create a run (problem statement on stdin) and print its size estimate
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

SCHEMA = "five-whys/2"
AGENT = "five-whys:why-expander"
PRESETS = {"full": (5, 5), "smoke": (3, 3)}
MODELS = ("inherit", "sonnet", "opus", "haiku")
MAX_PARALLEL = 5  # default wave size, well under Claude Code's cap
PLATFORM_PARALLEL_CAP = 20  # Claude Code runs at most 20 subagents at once by default
MAX_ATTEMPTS = 3
CONFIRM_AGENTS = 5  # runs needing more agents than this ask the user before dispatching
READ_WINDOW_BYTES = 48_000  # Read accepted about 64 KB of five-whys.json and rejected about 89 KB

# Agent tokens are estimated as a range from two runs measured with
# docs/self-improvement/usage.py (2026-09-13, claude-opus-5):
# - High: the v0.2.0 full run on its own rating, inside this repository. Agents
#   started with about 21k tokens of session context and read local files as
#   evidence. Root 44.1k for 30 reasons; branches mean 63.1k for 155 reasons.
# - Low: a root and one branch on a problem naming no files, in a clean
#   directory. Agents started with about 4.6k tokens and read only their prompt.
#   Root 11.3k; branch 23.6k.
# The assembled v0.2.0 file held 38 tokens per reason.
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


def default_split(depth: int) -> int:
    return max(1, depth // 2)


def shape_of(meta: dict) -> tuple[int, int, int]:
    shape = meta["shape"]
    return shape["breadth"], shape["depth"], shape["split"]


def agent_count(breadth: int, depth: int, split: int) -> int:
    return 1 + (breadth**split if split < depth else 0)


def estimate(breadth: int, depth: int, split: int) -> dict:
    agents, total = agent_count(breadth, depth, split), reasons(breadth, depth)
    return {
        "agents": agents,
        "reasons": total,
        "agent_tokens_low": agents * AGENT_OVERHEAD_TOKENS_LOW + total * TOKENS_PER_REASON_LOW,
        "agent_tokens": agents * AGENT_OVERHEAD_TOKENS + total * TOKENS_PER_REASON,
        "output_tokens": total * OUTPUT_TOKENS_PER_REASON,
        "basis": f"range from two {MEASURED['model']} runs measured on {MEASURED['date']}: the low end is a "
                 "problem naming no local files in a clean directory; the high end (agent_tokens) is the "
                 f"v{MEASURED['version']} self-run inside a large repository, where agents started with more "
                 "session context and read files as evidence. Each figure sums agents' reported totals; "
                 "context re-read on every turn is billed on top, mostly as cache reads.",
    }


# ---------------------------------------------------------------- invocation


def parse_invocation(text: str) -> dict:
    """Split leading options from the problem statement, exactly as SKILL.md documents."""
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

    for flag in ("--breadth", "--depth", "--split", "--max-parallel"):
        if flag in given and not (str(given[flag]).isdigit() and int(given[flag]) >= 1):
            errors.append(f"{flag} must be a whole number of at least 1")
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
            errors.append("--resume takes no problem statement")
        if not (Path(given["--resume"]) / "run.json").is_file():
            errors.append(f"--resume {given['--resume']} is not a five-whys run directory")
    elif not problem:
        errors.append("no problem statement after the options")

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
    """Return (whys or None, assumptions, errors)."""
    if not path.exists():
        return None, [], [f"{path.name}: missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [], [f"{path.name}: invalid JSON ({exc})"]
    if not isinstance(data, dict) or "whys" not in data:
        return None, [], [f'{path.name}: top level must be {{"whys": [...]}}']
    errors = validate(data["whys"], breadth, depth)
    assumptions = data.get("assumptions", [])
    if not (isinstance(assumptions, list) and all(isinstance(a, str) for a in assumptions)):
        errors.append("assumptions: must be a list of strings")
    if errors:
        return None, [], [f"{path.name}: {e}" for e in errors]
    return data["whys"], [a.strip() for a in assumptions if a.strip()], []


# ---------------------------------------------------------------- run layout


def read_run(run: Path) -> dict:
    path = run / "run.json"
    if not path.exists():
        sys.exit(f"not a five-whys run directory: {run}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.setdefault("shape", {"breadth": 5, "depth": 5, "split": 2})  # v0.1 runs
    meta.setdefault("model", "inherit")
    meta.setdefault("root_model", meta["model"])  # v0.2 runs could split tiers
    meta.setdefault("branch_model", meta["model"])
    meta.setdefault("max_parallel", 20)  # the v0.1 and v0.2 default
    meta.setdefault("attempts", {})
    return meta


def write_run(run: Path, meta: dict) -> None:
    (run / "run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def root_path(run: Path) -> Path:
    return run / "fragments" / "root.json"


def branch_path(run: Path, node_id: str) -> Path:
    return run / "fragments" / f"branch-{node_id}.json"


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


def node_at(nodes, node_id: str) -> dict:
    node = {}
    for step in node_id.split("."):
        node = nodes[int(step) - 1]
        nodes = node.get("whys") or []
    return node


def flatten(nodes, prefix: str = "", depth: int = 1, parent: str | None = None) -> list[dict]:
    return [{"id": i, "depth": d, "parent": p, "reason": n["reason"].strip()}
            for i, d, p, n in walk(nodes, prefix, depth, parent)]


# ---------------------------------------------------------------- prompts


def shape_example(breadth: int, levels: int) -> str:
    inner = '{"reason": "..."}'
    for _ in range(levels - 1):
        inner = '{"reason": "...", "whys": [' + inner + f", ... x{breadth}]}}"
    return '{"assumptions": ["..."], "whys": [' + inner + f", ... x{breadth}]}}"


def check_command(fragment: Path, breadth: int, levels: int) -> str:
    return f"python3 {SCRIPT} check {fragment} --breadth {breadth} --depth {levels}"


def output_section(fragment: Path, breadth: int, levels: int, top_note: str = "") -> list[str]:
    return [
        "",
        f"That is {reasons(breadth, levels)} reasons, roughly {reasons(breadth, levels) * OUTPUT_TOKENS_PER_REASON:,} "
        "output tokens with the JSON. That size is expected: keep every reason a full, specific sentence.",
        "Write them as JSON to:",
        str(fragment),
        "",
        f"Shape (every whys list has exactly {breadth} items{top_note}; assumptions is optional):",
        shape_example(breadth, levels),
        "",
        "Then run:",
        check_command(fragment, breadth, levels),
        f"Repair and re-check until it prints OK, at most {MAX_ATTEMPTS} fix cycles.",
    ]


def header_lines(meta: dict, title: str) -> list[str]:
    lines = [title, "", f"Problem: {meta['problem']}"]
    if meta.get("context"):
        lines += ["", "Context from the user:", meta["context"]]
    return lines


def root_prompt(meta: dict, fragment: Path) -> str:
    breadth, depth, split = shape_of(meta)
    lines = header_lines(meta, f"Five Whys — ROOT expansion (levels 1-{split} of {depth}).")
    lines += ["", "Build these levels:",
              f'- Level 1: {breadth} distinct reasons answering "Why does this problem occur?"']
    if split > 1:
        lines.append(f'- Levels 2-{split}: for EACH reason above, {breadth} distinct reasons '
                     'answering "Why <that reason>?"')
    lines.append(f"- Stop after level {split}; level-{split} reasons have no whys in this file.")
    return "\n".join(lines + output_section(fragment, breadth, split))


def branch_prompt(meta: dict, chain: tuple, fragment: Path, written: list) -> str:
    breadth, depth, split = shape_of(meta)
    node_id, reason = chain[-1]
    first = split + 1
    lines = header_lines(meta, f"Five Whys — BRANCH expansion of node {node_id} (levels {first}-{depth} of {depth}).")
    lines += [""] + [f"Why level {level} (id {cid}): {text}" for level, (cid, text) in enumerate(chain, 1)]
    own = {cid for cid, _ in chain}
    others = [(cid, text) for cid, text in written if cid not in own]
    if others:
        lines += ["", "Reasons already written for other parts of the tree. Do not reproduce these causes; "
                      "go deeper on your own node instead:"]
        lines += [f"- {cid}: {text}" for cid, text in others]
    lines += ["", f"Expand node {node_id} into levels {first}-{depth}:",
              f'- Level {first}: {breadth} distinct reasons answering "Why: {reason}"']
    if depth > first:
        lines.append(f"- Each further level: for EACH reason above it, {breadth} distinct reasons "
                     'answering "Why <that reason>?"')
    lines.append(f"- Stop after level {depth}; level-{depth} reasons have no whys.")
    top_note = f"; the top-level whys are the level-{first} reasons"
    return "\n".join(lines + output_section(fragment, breadth, depth - split, top_note))


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
    problem = sys.stdin.read().strip()
    if not problem:
        sys.exit("init: provide the problem statement on stdin")
    breadth, depth = PRESETS[args.preset]
    breadth, depth = args.breadth or breadth, args.depth or depth
    if breadth < 1 or depth < 1:
        sys.exit("init: breadth and depth must be at least 1")
    split = args.split or default_split(depth)
    if not 1 <= split <= depth:
        sys.exit(f"init: split must be between 1 and {depth}")
    if not 1 <= args.max_parallel <= PLATFORM_PARALLEL_CAP:
        sys.exit(f"init: max-parallel must be between 1 and {PLATFORM_PARALLEL_CAP}")
    context = Path(args.context_file).read_text(encoding="utf-8").strip() if args.context_file else ""

    slug = re.sub(r"[^a-z0-9]+", "-", problem.lower()).strip("-")[:40].strip("-") or "problem"
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

    size = estimate(breadth, depth, split)
    meta = {
        "schema": SCHEMA,
        "problem": problem,
        "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
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
    print(json.dumps({"run": str(run), "shape": meta["shape"], "model": args.model,
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

    root, _, root_errors = load_fragment(root_path(run), breadth, split)
    pending = []
    if root is None:
        pending.append({"id": "root", "fragment": str(root_path(run)), "errors": root_errors,
                        "prompt": root_prompt(meta, root_path(run))})
    elif split < depth:
        branches = []
        for node_id, chain in frontier(root, split):
            path = branch_path(run, node_id)
            branch, _, errors = load_fragment(path, breadth, depth - split)
            branches.append((node_id, chain, path, branch, errors))
        # Later waves also see the first-level reasons of branches that are already done.
        written = [(node_id, node["reason"].strip()) for node_id, _, _, node in walk(root)]
        for node_id, _, _, branch, _ in branches:
            if branch is not None:
                written += [(f"{node_id}.{i}", node["reason"].strip()) for i, node in enumerate(branch, 1)]
        for node_id, chain, path, branch, errors in branches:
            if branch is None and (not only or node_id in only):
                pending.append({"id": node_id, "fragment": str(path), "errors": errors,
                                "prompt": branch_prompt(meta, chain, path, written)})

    ready = [t for t in pending if attempts.get(t["id"], 0) < MAX_ATTEMPTS]
    stuck = [t for t in pending if attempts.get(t["id"], 0) >= MAX_ATTEMPTS]
    wave = ready[: meta["max_parallel"]]
    for task in wave:
        task["attempt"] = attempts.get(task["id"], 0) + 1
        tier = meta["root_model"] if task["id"] == "root" else meta["branch_model"]
        task["model"] = None if tier == "inherit" else tier
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

    state = ("root" if root is None else "branches") if wave else ("stuck" if stuck else "ready")
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
    total = agent_count(breadth, depth, split)
    root, _, _ = load_fragment(root_path(run), breadth, split)
    if root is None:
        missing, done = ["root"], 0
    else:
        missing = [node_id for node_id, _ in frontier(root, split)
                   if load_fragment(branch_path(run, node_id), breadth, depth - split)[0] is None] if split < depth else []
        done = total - len(missing)
    print(json.dumps({
        "run": str(run),
        "shape": meta["shape"],
        "model": meta["model"],
        "max_parallel": meta["max_parallel"],
        "plugin_version": meta.get("plugin_version", "before 0.3.0"),
        "installed_plugin_version": plugin_version(),
        "done": done,
        "total": total,
        "missing": missing,
        "stuck": [m for m in missing if meta["attempts"].get(m, 0) >= MAX_ATTEMPTS],
        "checks": read_checks(run),
        "waves": wave_timing(run, meta),
        "assembled": (run / "five-whys.json").exists(),
        "estimate": estimate(breadth, depth, split),
    }, indent=2))


def run_folder(fragment: Path) -> Path | None:
    folder = fragment.resolve().parent
    return folder.parent if folder.name == "fragments" and (folder.parent / "run.json").exists() else None


# Which rule a check error broke, so the log shows what agents get wrong, not just how often.
ERROR_KINDS = (
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


def fragment_name(node_id: str) -> str:
    return "root.json" if node_id == "root" else f"branch-{node_id}.json"


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
    """For a branch fragment inside a run: (node id, the root's reasons as flat entries)."""
    run, match = run_folder(fragment), re.fullmatch(r"branch-(\d+(?:\.\d+)*)\.json", fragment.name)
    if run is None or not match:
        return None
    meta = read_run(run)
    breadth, _, split = shape_of(meta)
    root, _, _ = load_fragment(root_path(run), breadth, split)
    return (match.group(1), flatten(root)) if root is not None else None


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

    context = root_context(fragment)
    if context:  # compare against the real ancestors and the root's reasons
        node_id, root_flat = context
        mine = flatten(whys, node_id, node_id.count(".") + 2, node_id)
        flags = hygiene(root_flat + mine, report={r["id"] for r in mine})
        prefix = node_id + "."

        def label(i):
            return i[len(prefix):] if i.startswith(prefix) else f"{i} (written by the root)"
    else:
        flags = hygiene(flatten(whys))

        def label(i):
            return i
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
    root, root_assumptions, errors = load_fragment(root_path(run), breadth, split)
    if root is None:
        sys.exit("\n".join(errors))
    assumptions = {"root": root_assumptions} if root_assumptions else {}
    missing, problems = [], []
    if split < depth:
        for node_id, _ in list(frontier(root, split)):
            branch, branch_assumptions, errs = load_fragment(branch_path(run, node_id), breadth, depth - split)
            if branch is None:
                if args.partial:
                    missing.append(node_id)
                    node_at(root, node_id)["missing"] = True
                else:
                    problems.extend(errs)
                continue
            node_at(root, node_id)["whys"] = branch
            if branch_assumptions:
                assumptions[node_id] = branch_assumptions
    if problems:
        sys.exit("cannot assemble; run plan and re-dispatch, or assemble --partial:\n" + "\n".join(problems))

    flat = flatten(root)
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
    tiers = {} if meta["root_model"] == meta["branch_model"] == meta["model"] else \
        {"root_model": meta["root_model"], "branch_model": meta["branch_model"]}
    header = {
        "schema": SCHEMA,
        "problem": meta["problem"],
        **({"context": meta["context"]} if meta.get("context") else {}),
        "created": meta.get("created"),
        "assembled": now.isoformat(timespec="seconds"),
        "duration_seconds": duration,
        "waves": [{"wave": w["wave"], "fragments": len(w["ids"]), "seconds": w["seconds"]} for w in timing],
        "plugin_version": meta.get("plugin_version", "before 0.3.0"),
        "breadth": breadth,
        "depth": depth,
        "split": split,
        "model": meta["model"],
        **tiers,
        "total_reasons": reasons(breadth, depth),
        "present_reasons": len(flat),
        "complete": not missing,
        "missing_branches": missing,
        "levels": levels,
        **({"assumptions": assumptions} if assumptions else {}),
        "reading": "Top-level whys answer 'Why does the problem occur?'. Each node's whys answer "
                   "'Why <that node's reason>?'. An id is the dotted path from the top, so 2.4.1 is the "
                   "1st reason under 2.4, which is the 4th reason under 2. index.md lists the top "
                   f"{split} level(s) and the Read windows for this file; hygiene.json holds mechanical flags only.",
    }
    head = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    lines = [f'{head[:-1]},"whys":[']
    emit(root, "", 1, depth, lines)
    lines.append("]}")
    text = "\n".join(lines) + "\n"
    json.loads(text)  # guard: the hand-rolled layout must still be valid JSON
    out = run / "five-whys.json"
    out.write_text(text, encoding="utf-8")

    windows = read_plan(lines)
    index = ["# Five Whys index", "", f"Problem: {meta['problem']}", "",
             f"Settings: {breadth} wide x {depth} deep, root writes {split} level(s), model {meta['model']}"
             + (f" (root {meta['root_model']}, branches {meta['branch_model']})" if tiers else "")
             + f", waves of {meta['max_parallel']}"
             + (f" ({len(timing)} dispatched, {round(duration / 60)} min)" if timing and duration is not None else "")
             + f", plugin {header['plugin_version']}.", ""]
    span = "Level 1" if split == 1 else f"Levels 1-{split}"
    if split < depth:
        index += [f"{span} of {depth}. Each level-{split} reason heads a branch of "
                  f"{reasons(breadth, depth - split)} deeper reasons. Print one branch with:", "",
                  "```", f"python3 {SCRIPT} show {run} --id <id>", "```", ""]
    index += [f"{'  ' * (r['depth'] - 1)}- {r['id']} {r['reason']}" + (" (branch missing)" if r["id"] in missing else "")
              for r in flat if r["depth"] <= split]
    index += ["", "## Reading five-whys.json whole", "",
              f"Read these {len(windows)} windows in order; each stays under the Read tool's size limit:", ""]
    index += [f"- offset {offset}, limit {limit}" for offset, limit in windows]
    (run / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    flags = hygiene(flat)
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
        "present_reasons": len(flat),
        "total_reasons": reasons(breadth, depth),
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
    nodes = json.loads(path.read_text(encoding="utf-8"))["whys"]
    if args.sample:
        chains = []

        def collect(level_nodes, chain):
            for node in level_nodes:
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
            print(f"{'  ' * (node['depth'] - 1)}{node['id']}  {node['reason']}{marker}")
            if remaining != 1:
                print_level(node.get("whys", []), remaining - 1)

    print_level(nodes, args.levels or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="split raw /five-whys arguments (stdin) into options and the problem")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("init", help="create a run; problem statement on stdin")
    p.add_argument("--base", default=".five-whys", help="parent directory for runs")
    p.add_argument("--preset", choices=sorted(PRESETS), default="full", help="full = 5x5, smoke = 3x3")
    p.add_argument("--breadth", type=int, help="reasons per why (overrides the preset)")
    p.add_argument("--depth", type=int, help="levels of why (overrides the preset)")
    p.add_argument("--split", type=int, help="levels written by the root agent (default: depth // 2)")
    p.add_argument("--model", choices=MODELS, default="inherit", help="model for the expander agents")
    p.add_argument("--max-parallel", type=int, default=MAX_PARALLEL, help="largest dispatch wave")
    p.add_argument("--context-file", help="file of user-supplied context included in every prompt")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="next wave of missing fragments with dispatch prompts")
    p.add_argument("run")
    p.add_argument("--record", action="store_true", help="count this wave as a dispatch attempt")
    p.add_argument("--only", help="comma-separated branch ids to plan (root is always planned first)")
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
    p.add_argument("--partial", action="store_true", help="assemble even with missing branches, marking them")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("show", help="print a subtree or the top levels of an assembled tree")
    p.add_argument("tree", help="five-whys.json, or the run directory holding it")
    p.add_argument("--id", help="dotted node id to show, preceded by its ancestor chain")
    p.add_argument("--levels", type=int, help="levels to print, counting the shown node (default: all)")
    p.add_argument("--sample", type=int, help="print N randomly chosen reasons, each with its ancestor chain")
    p.add_argument("--seed", type=int, help="random seed for --sample, for repeatable spot checks")
    p.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
