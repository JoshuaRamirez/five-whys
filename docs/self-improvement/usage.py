#!/usr/bin/env python3
"""Measure a five-whys run's per-agent token use from Claude Code subagent logs.

The script that manages runs never sees token usage; Claude Code records it in
each subagent's log. This reads those logs, keeps the latest completed agent per
fragment of one run, and fits the estimate constants used by fivewhys.py.

  usage.py <run-dir> [--logs GLOB]

Default GLOB: ~/.claude/projects/*/*/subagents/*.jsonl
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
from pathlib import Path


def reasons(breadth: int, levels: int) -> int:
    return sum(breadth**level for level in range(1, levels + 1))


def read_agent(path: str, run_name: str):
    lines = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    opening = json.dumps(lines[:3])
    match = re.search(r"prompts/(root|\d+(?:\.\d+)*)\.md", opening)
    if run_name not in opening or not match:
        return None
    turns = output = cumulative = 0
    final = None
    completed = False
    for entry in lines:
        message = entry.get("message") or {}
        if entry.get("type") == "user":  # a check that printed OK means the fragment validated
            for part in message.get("content") if isinstance(message.get("content"), list) else []:
                body = part.get("content") if isinstance(part, dict) and part.get("type") == "tool_result" else None
                texts = [body] if isinstance(body, str) else [b.get("text", "") for b in body or [] if isinstance(b, dict)]
                completed = completed or any(t.startswith("OK") for t in texts)
        usage = message.get("usage")
        if entry.get("type") != "assistant" or not usage:
            continue
        turns += 1
        context = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) \
            + usage.get("cache_read_input_tokens", 0)
        output += usage.get("output_tokens", 0)
        cumulative += context
        final = context + usage.get("output_tokens", 0)
        for part in message.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text", "").startswith("OK "):
                completed = True
    return {"id": match.group(1), "log": os.path.basename(path), "started": lines[0].get("timestamp"),
            "completed": completed, "turns": turns, "output_tokens": output,
            "reported_total": final, "cumulative_context": cumulative}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--logs", default=os.path.expanduser("~/.claude/projects/*/*/subagents/*.jsonl"))
    args = parser.parse_args()
    run = Path(args.run).resolve()
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    breadth, depth, split = (meta["shape"][k] for k in ("breadth", "depth", "split"))

    agents = [a for a in (read_agent(p, run.name) for p in glob.glob(args.logs)) if a]
    latest = {}
    for agent in sorted(agents, key=lambda a: a["started"] or ""):
        if agent["completed"]:
            latest[agent["id"]] = agent
    root = latest.get("root")
    branches = [a for i, a in latest.items() if i != "root"]
    # Agents stopped before their check returned (for example by a restart) may still have
    # written a valid fragment; their totals are incomplete, so they are listed, not fitted.
    interrupted = sorted({a["id"] for a in agents if a["id"] not in latest})
    result = {"run": str(run), "agent_logs": len(agents), "completed_fragments": len(latest),
              "interrupted_without_completed_retry": interrupted}
    if root and branches:
        root_reasons, branch_reasons = reasons(breadth, split), reasons(breadth, depth - split)
        branch_mean = statistics.mean(a["reported_total"] for a in branches)
        per_reason = (branch_mean - root["reported_total"]) / (branch_reasons - root_reasons)
        result.update({
            "root_reported_total": root["reported_total"],
            "branch_reported_total": {"min": min(a["reported_total"] for a in branches),
                                      "mean": round(branch_mean), "max": max(a["reported_total"] for a in branches)},
            "branch_output_tokens_mean": round(statistics.mean(a["output_tokens"] for a in branches)),
            "branch_cumulative_context": {"min": min(a["cumulative_context"] for a in branches),
                                          "max": max(a["cumulative_context"] for a in branches)},
            "fit": {"AGENT_OVERHEAD_TOKENS": round(root["reported_total"] - root_reasons * per_reason, -2),
                    "TOKENS_PER_REASON": round(per_reason)},
        })
    output = run / "five-whys.json"
    if output.exists():
        result["fit_output"] = {"OUTPUT_TOKENS_PER_REASON": round(output.stat().st_size / 4 / reasons(breadth, depth))}
    result["agents"] = sorted(latest.values(), key=lambda a: [int(x) if x.isdigit() else -1 for x in a["id"].split(".")])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
