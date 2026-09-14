"""Tests for docs/self-improvement/usage.py against synthetic subagent logs."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "docs" / "self-improvement" / "usage.py"


def log_lines(run: Path, node: str, contexts: list[int], output: int = 100) -> list[dict]:
    lines = [{"type": "user", "timestamp": f"2026-09-13T10:00:0{len(node)}Z",
              "message": {"role": "user", "content": f"Read {run}/prompts/{node}.md and carry out the task."}}]
    for k, context in enumerate(contexts):
        lines.append({"type": "assistant", "message": {"role": "assistant", "content": [],
                      "usage": {"input_tokens": 10, "cache_creation_input_tokens": context - 10,
                                "cache_read_input_tokens": 0, "output_tokens": output}}})
        if k == len(contexts) - 1:
            lines.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "OK"}]}})
    return lines


class UsageTests(unittest.TestCase):
    def test_first_turn_context_and_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = tmp / "20260913-100000-deploys-fail"
            run.mkdir()
            (run / "run.json").write_text(json.dumps({"shape": {"breadth": 3, "depth": 3, "split": 1}}))
            logs = tmp / "logs"
            logs.mkdir()
            for node, contexts in {"root": [4000, 6000], "1": [5000, 9000], "2": [6000, 7000]}.items():
                (logs / f"agent-{node}.jsonl").write_text(
                    "\n".join(json.dumps(line) for line in log_lines(run, node, contexts)) + "\n")
            out = tmp / "usage.json"
            proc = subprocess.run([sys.executable, str(USAGE), str(run), "--logs", str(logs / "*.jsonl"),
                                   "--out", str(out)], capture_output=True, text=True, check=True)
            result = json.loads(proc.stdout)
            self.assertEqual(json.loads(out.read_text()), result)
            self.assertEqual(result["first_turn_context"], {"min": 4000, "mean": 5000, "max": 6000})
            self.assertEqual({a["id"]: a["first_turn_context"] for a in result["agents"]},
                             {"root": 4000, "1": 5000, "2": 6000})
            self.assertEqual(result["root_reported_total"], 6100)


    def test_root_groups_count_every_input_they_wrote(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = tmp / "20260914-100000-2-inputs-deploys-fail"
            run.mkdir()
            (run / "run.json").write_text(json.dumps({"shape": {"breadth": 5, "depth": 5, "split": 2}}))
            logs = tmp / "logs"
            logs.mkdir()
            for node, contexts in {"roots-1-2": [5000, 20000], "1.1": [5000, 40000]}.items():
                (logs / f"agent-{node}.jsonl").write_text(
                    "\n".join(json.dumps(line) for line in log_lines(run, node, contexts)) + "\n")
            result = json.loads(subprocess.run([sys.executable, str(USAGE), str(run), "--logs", str(logs / "*.jsonl")],
                                               capture_output=True, text=True, check=True).stdout)
            # The root group wrote 2 x 30 reasons, the branch 155: (40100 - 20100) / (155 - 60) per reason.
            self.assertEqual(result["root_reported_total"], 20100)
            self.assertEqual(result["fit"], {"AGENT_OVERHEAD_TOKENS": 7500.0, "TOKENS_PER_REASON": 211})


if __name__ == "__main__":
    unittest.main()
