"""Tests for docs/self-improvement/quality.py."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "docs" / "self-improvement" / "quality.py"


def nodes(breadth: int, depth: int, prefix: str = "", level: int = 1) -> list[dict]:
    out = []
    for i in range(1, breadth + 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        text = hashlib.md5(node_id.encode()).hexdigest()[:12]
        node = {"id": node_id, "depth": level, "reason": f"Reason {text}."}
        if level < depth:
            node["whys"] = nodes(breadth, depth, node_id, level + 1)
        out.append(node)
    return out


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.tree = self.dir / "five-whys.json"
        self.tree.write_text(json.dumps({"problem": "Deploys fail.", "whys": nodes(2, 3)}))
        self.packet = self.dir / "packet.json"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, ok=True):
        proc = subprocess.run([sys.executable, str(QUALITY), *map(str, args)], capture_output=True, text=True)
        if ok and proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)
        return proc

    def draw(self, *extra):
        self.cli("draw", self.tree, "--n", 6, "--seed", 4, "--out", self.packet, *extra)
        return json.loads(self.packet.read_text()), json.loads((self.dir / "packet.key.json").read_text())

    def scores(self, name, values, **fields):
        path = self.dir / name
        path.write_text(json.dumps({"scorer": "test", "independent": True, **fields,
                                    "scores": [{"n": n, "causal": c, "specific": s, "distinct": d}
                                               for n, (c, s, d) in values.items()]}))
        return path

    def test_draw_is_repeatable_stratified_and_hides_ids(self):
        packet, key = self.draw("--stratify", "level")
        self.assertEqual((packet, key), self.draw("--stratify", "level"))
        self.assertEqual(sorted(item["level"] for item in key["items"]), [1, 1, 2, 2, 3, 3])
        self.assertNotIn('"id"', self.packet.read_text())
        item = next(i for i in packet["items"] if i["n"] == next(k["n"] for k in key["items"] if k["level"] == 3))
        self.assertEqual((len(item["chain"]), len(item["siblings"])), (2, 1))

    def test_score_rejects_bad_values_and_missing_items(self):
        self.draw()
        bad = self.scores("bad.json", {1: (3, 1, 1), 2: (True, 1, 1)})
        out = self.cli("score", self.packet, bad, ok=False)
        self.assertEqual(out.returncode, 1)
        self.assertIn("causal must be 0, 1 or 2", out.stdout)
        self.assertIn("items not scored: 3, 4, 5, 6", out.stdout)
        good = self.scores("good.json", {n: (2, 1, 2) for n in range(1, 7)})
        self.assertIn("OK 6 items", self.cli("score", self.packet, good).stdout)

    def test_report_means_and_agreement(self):
        self.draw("--stratify", "level")
        a = self.scores("a.json", {n: (2, 2, 1) for n in range(1, 7)})
        b = self.scores("b.json", {n: (2, 1 if n <= 3 else 2, 1) for n in range(1, 7)}, independent=False)
        report = json.loads(self.cli("report", self.packet, a, b).stdout)
        self.assertEqual(report["scorers"][0]["means"], {"causal": 2, "specific": 2, "distinct": 1})
        self.assertEqual(report["scorers"][1]["means"]["specific"], 1.5)
        self.assertEqual(sorted(report["scorers"][0]["by_level"]), ["1", "2", "3"])
        self.assertEqual(report["agreement"]["exact"], {"causal": 1.0, "specific": 0.5, "distinct": 1.0})
        self.assertEqual(report["agreement"]["mean_abs_difference"]["specific"], 0.5)


if __name__ == "__main__":
    unittest.main()
