#!/usr/bin/env python3
"""Five Whys run manager.

Every reason is asked "why?" and answered with `breadth` further reasons, `depth`
levels deep. Generation is split into agent-sized fragments: one root agent
writes levels 1..split, and one branch agent per level-`split` reason writes the
levels beneath it. This script owns everything deterministic:

  init      create a run (problem statement on stdin) and print its size estimate
  plan      list the next wave of missing fragments, each with a dispatch prompt
  status    report done, missing and stuck fragments
  check     validate one fragment against its expected shape
  assemble  merge fragments into five-whys.json plus index.md and hygiene.json
  show      print a subtree, the top levels, or a random sample, with ancestor chains

Run metadata lives in <run>/run.json and fragments in <run>/fragments/.
Nothing here ranks, prunes or summarizes reasons; hygiene flags are mechanical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA = "five-whys/2"
SCRIPT = Path(__file__).resolve()
AGENT = "five-whys:why-expander"
PRESETS = {"full": (5, 5), "smoke": (3, 3)}
MODELS = ("inherit", "sonnet", "opus", "haiku")
MAX_PARALLEL = 20  # Claude Code's default cap on concurrent subagents
MAX_ATTEMPTS = 3
LONG_REASON_WORDS = 25
SIMILARITY = 0.6

# Measured on the 2026-09-13 self-run (26 agents, 3,905 reasons): about 36.6k
# tokens of per-agent overhead, 67 generation tokens per reason, and 33 tokens
# per reason in the assembled file.
AGENT_OVERHEAD_TOKENS = 36_600
TOKENS_PER_REASON = 67
OUTPUT_TOKENS_PER_REASON = 33

STOPWORDS = frozenset(
    "a an and are as at be because been but by can for from has have how in into is it its "
    "not no of on or so than that the their them then there they this to was were what when "
    "which while who why will with without".split()
)


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
        "agent_tokens": agents * AGENT_OVERHEAD_TOKENS + total * TOKENS_PER_REASON,
        "output_tokens": total * OUTPUT_TOKENS_PER_REASON,
        "basis": "scaled from the measured 2026-09-13 self-run; actual use varies by model and problem",
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
    meta.setdefault("root_model", meta["model"])
    meta.setdefault("branch_model", meta["model"])
    meta.setdefault("max_parallel", MAX_PARALLEL)
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


# ---------------------------------------------------------------- hygiene


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", text.lower()) if w not in STOPWORDS}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def hygiene(flat: list[dict]) -> dict:
    """Mechanical flags over every reason. Annotates only; removes nothing."""
    by_id = {r["id"]: r for r in flat}
    toks = {r["id"]: tokens(r["reason"]) for r in flat}

    groups = defaultdict(list)
    for r in flat:
        groups[" ".join(re.findall(r"[a-z0-9]+", r["reason"].lower()))].append(r["id"])
    exact = [ids for ids in groups.values() if len(ids) > 1]
    exact_pairs = {frozenset((a, b)) for ids in exact for a in ids for b in ids if a != b}

    # Candidate pairs share at least two informative tokens; very common tokens
    # (over 5% of reasons) are skipped so the index stays near-linear.
    df = Counter(t for s in toks.values() for t in s)
    common = max(5, len(flat) // 20)
    index = defaultdict(list)
    for r in flat:
        for t in toks[r["id"]]:
            if df[t] <= common:
                index[t].append(r["id"])
    shared = Counter()
    for ids in index.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                shared[(ids[i], ids[j])] += 1
    near = []
    for (a, b), count in shared.items():
        if count < 2 or frozenset((a, b)) in exact_pairs:
            continue
        ta, tb = toks[a], toks[b]
        parent = by_id[a]["parent"]
        if parent and parent == by_id[b]["parent"]:  # siblings share their parent's topic words
            ta, tb = ta - toks[parent], tb - toks[parent]
        similarity = jaccard(ta, tb)
        if similarity >= SIMILARITY:
            near.append({"a": a, "b": b, "similarity": round(similarity, 2)})
    near.sort(key=lambda p: -p["similarity"])

    restates_parent, restates_ancestor = [], []
    for r in flat:
        ancestor, k = r["parent"], 0
        while ancestor:
            similarity = jaccard(toks[r["id"]], toks[ancestor])
            if similarity >= SIMILARITY:
                flag = {"id": r["id"], "of": ancestor, "similarity": round(similarity, 2)}
                (restates_parent if k == 0 else restates_ancestor).append(flag)
                break
            ancestor, k = by_id[ancestor]["parent"], k + 1

    over_length = [{"id": r["id"], "words": len(r["reason"].split())}
                   for r in flat if len(r["reason"].split()) > LONG_REASON_WORDS]
    flags = {"exact_duplicates": exact, "near_duplicates": near, "restates_parent": restates_parent,
             "restates_ancestor": restates_ancestor, "over_length": over_length}
    return {
        "note": "Mechanical flags only. Nothing was removed, rewritten, ranked or summarized; "
                "whether a flag matters is the reader's call.",
        "method": "word-overlap (Jaccard) on lowercased words minus stopwords; sibling pairs ignore their "
                  "parent's words. Catches copies and close rewordings, misses paraphrases.",
        "thresholds": {"similarity": SIMILARITY, "long_reason_words": LONG_REASON_WORDS},
        "counts": {name: len(items) for name, items in flags.items()},
        **flags,
    }


# ---------------------------------------------------------------- commands


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
    if args.max_parallel < 1:
        sys.exit("init: max-parallel must be at least 1")
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

    meta = {
        "schema": SCHEMA,
        "problem": problem,
        "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "shape": {"breadth": breadth, "depth": depth, "split": split},
        "model": args.model,
        "root_model": args.root_model or args.model,
        "branch_model": args.branch_model or args.model,
        "max_parallel": args.max_parallel,
        "attempts": {},
    }
    if context:
        meta["context"] = context
    write_run(run, meta)
    print(json.dumps({"run": str(run), "shape": meta["shape"], "model": args.model,
                      "root_model": meta["root_model"], "branch_model": meta["branch_model"],
                      "estimate": estimate(breadth, depth, split)}, indent=2))


def cmd_plan(args) -> None:
    run = Path(args.run).resolve()
    meta = read_run(run)
    breadth, depth, split = shape_of(meta)
    only = {i.strip() for i in args.only.split(",")} if args.only else None
    attempts = meta["attempts"]

    root, _, root_errors = load_fragment(root_path(run), breadth, split)
    pending = []
    if root is None:
        pending.append({"id": "root", "fragment": str(root_path(run)), "errors": root_errors,
                        "prompt": root_prompt(meta, root_path(run))})
    elif split < depth:
        written = [(node_id, node["reason"].strip()) for node_id, _, _, node in walk(root)]
        for node_id, chain in frontier(root, split):
            if only and node_id not in only:
                continue
            path = branch_path(run, node_id)
            branch, _, errors = load_fragment(path, breadth, depth - split)
            if branch is None:
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
        "done": done,
        "total": total,
        "missing": missing,
        "stuck": [m for m in missing if meta["attempts"].get(m, 0) >= MAX_ATTEMPTS],
        "checks": read_checks(run),
        "assembled": (run / "five-whys.json").exists(),
        "estimate": estimate(breadth, depth, split),
    }, indent=2))


def log_check(fragment: Path, errors: int, warnings: int) -> None:
    # Only fragments inside a run directory are logged, so repair cycles are countable.
    folder = fragment.resolve().parent
    if folder.name != "fragments" or not (folder.parent / "run.json").exists():
        return
    entry = {"fragment": fragment.name, "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
             "ok": errors == 0, "errors": errors, "warnings": warnings}
    with open(folder.parent / "check-log.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")


def read_checks(run: Path) -> dict:
    checks = {}
    log = run / "check-log.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            item = checks.setdefault(entry["fragment"], {"checks": 0, "failed": 0})
            item["checks"] += 1
            item["failed"] += 0 if entry["ok"] else 1
    return checks


def cmd_check(args) -> None:
    fragment = Path(args.fragment)
    whys, _, errors = load_fragment(fragment, args.breadth, args.depth)
    if errors:
        log_check(fragment, len(errors), 0)
        print("\n".join(errors[:25]))
        if len(errors) > 25:
            print(f"... and {len(errors) - 25} more errors")
        sys.exit(1)
    print("OK")
    flags = hygiene([{"id": i, "depth": d, "parent": p, "reason": n["reason"].strip()} for i, d, p, n in walk(whys)])
    warnings = [f"warning: items {', '.join(ids)} repeat the same text" for ids in flags["exact_duplicates"]]
    warnings += [f"warning: items {f['a']} and {f['b']} are near-duplicates (similarity {f['similarity']})"
                 for f in flags["near_duplicates"]]
    warnings += [f"warning: item {f['id']} restates item {f['of']}"
                 for f in flags["restates_parent"] + flags["restates_ancestor"]]
    warnings += [f"warning: item {f['id']} has {f['words']} words; aim for about 20" for f in flags["over_length"]]
    log_check(fragment, 0, len(warnings))
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

    flat = [{"id": i, "depth": d, "parent": p, "reason": n["reason"].strip()} for i, d, p, n in walk(root)]
    levels = []
    for level in range(1, depth + 1):
        at = [len(r["reason"].split()) for r in flat if r["depth"] == level]
        levels.append({"level": level, "reasons": len(at), "avg_words": round(sum(at) / len(at), 1) if at else 0})

    now = dt.datetime.now().astimezone()
    try:
        duration = int((now - dt.datetime.fromisoformat(meta["created"])).total_seconds())
    except (KeyError, ValueError, TypeError):
        duration = None
    header = {
        "schema": SCHEMA,
        "problem": meta["problem"],
        **({"context": meta["context"]} if meta.get("context") else {}),
        "created": meta.get("created"),
        "assembled": now.isoformat(timespec="seconds"),
        "duration_seconds": duration,
        "breadth": breadth,
        "depth": depth,
        "split": split,
        "model": meta["model"],
        "root_model": meta["root_model"],
        "branch_model": meta["branch_model"],
        "total_reasons": reasons(breadth, depth),
        "present_reasons": len(flat),
        "complete": not missing,
        "missing_branches": missing,
        "levels": levels,
        **({"assumptions": assumptions} if assumptions else {}),
        "reading": "Top-level whys answer 'Why does the problem occur?'. Each node's whys answer "
                   "'Why <that node's reason>?'. An id is the dotted path from the top, so 2.4.1 is the "
                   "1st reason under 2.4, which is the 4th reason under 2. index.md lists the top "
                   f"{split} level(s); hygiene.json holds mechanical flags only.",
    }
    head = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    lines = [f'{head[:-1]},"whys":[']
    emit(root, "", 1, depth, lines)
    lines.append("]}")
    text = "\n".join(lines) + "\n"
    json.loads(text)  # guard: the hand-rolled layout must still be valid JSON
    out = run / "five-whys.json"
    out.write_text(text, encoding="utf-8")

    index = ["# Five Whys index", "", f"Problem: {meta['problem']}", ""]
    if split < depth:
        index += [f"Levels 1-{split} of {depth}. Each level-{split} reason heads a branch of "
                  f"{reasons(breadth, depth - split)} deeper reasons. Print one branch with:", "",
                  "```", f"python3 {SCRIPT} show {run} --id <id>", "```", ""]
    index += [f"{'  ' * (r['depth'] - 1)}- {r['id']} {r['reason']}" + (" (branch missing)" if r["id"] in missing else "")
              for r in flat if r["depth"] <= split]
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

    p = sub.add_parser("init", help="create a run; problem statement on stdin")
    p.add_argument("--base", default=".five-whys", help="parent directory for runs")
    p.add_argument("--preset", choices=sorted(PRESETS), default="full", help="full = 5x5, smoke = 3x3")
    p.add_argument("--breadth", type=int, help="reasons per why (overrides the preset)")
    p.add_argument("--depth", type=int, help="levels of why (overrides the preset)")
    p.add_argument("--split", type=int, help="levels written by the root agent (default: depth // 2)")
    p.add_argument("--model", choices=MODELS, default="inherit", help="model for the expander agents")
    p.add_argument("--root-model", choices=MODELS, help="model for the root task (default: --model)")
    p.add_argument("--branch-model", choices=MODELS, help="model for branch tasks (default: --model)")
    p.add_argument("--max-parallel", type=int, default=MAX_PARALLEL, help="largest dispatch wave")
    p.add_argument("--context-file", help="file of user-supplied context included in every prompt")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="next wave of missing fragments with dispatch prompts")
    p.add_argument("run")
    p.add_argument("--record", action="store_true", help="count this wave as a dispatch attempt")
    p.add_argument("--only", help="comma-separated branch ids to plan (root is always planned first)")
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
