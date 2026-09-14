"""Tests for docs/self-improvement/ledger.py on a small synthetic round."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "self-improvement" / "ledger.py"
spec = importlib.util.spec_from_file_location("ledger", LEDGER)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def tree(breadth: int, depth: int, prefix: str = "", level: int = 1) -> list[dict]:
    nodes = []
    for i in range(1, breadth + 1):
        node_id = f"{prefix}.{i}" if prefix else str(i)
        node = {"id": node_id, "depth": level, "reason": f"Reason {node_id}."}
        if level < depth:
            node["whys"] = tree(breadth, depth, node_id, level + 1)
        nodes.append(node)
    return nodes


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.round = Path(self.tmp.name) / "round-9"
        (self.round / "ledger").mkdir(parents=True)
        (self.round / "tree.json").write_text(json.dumps({"whys": tree(2, 3)}))
        (self.round / "catalog.json").write_text(json.dumps({
            "rules": ["IMP beats X."],
            "improvements": [{"code": "IMP-1", "title": "Fix it", "detail": "d"}],
            "dispositions": [{"code": "X-HIST", "title": "History", "detail": "d"}]}))
        # 1 and 1.1 and 2 have their own lines; everything else inherits.
        (self.round / "ledger" / "a.txt").write_text("1 IMP-1 note one\n1.1 X-HIST own line\n2 X-HIST note two\n")
        self.cli("merge")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, ok=True) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, str(LEDGER), str(self.round), *map(str, args)],
                              capture_output=True, text=True)
        if ok and proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)
        return proc

    def packet(self, *args) -> dict:
        return json.loads(self.cli("sample", *args, "--json").stdout)

    def verdicts(self, name, entries, **fields) -> Path:
        path = self.round / name
        path.write_text(json.dumps({"reviewer": "test reviewer", "independent": True, "stratified": True,
                                    **fields, "entries": entries}))
        return path


class SampleTests(LedgerCase):
    def test_stratified_draw_is_equal_per_group_and_repeatable(self):
        first = self.packet(6, "--seed", 3, "--stratify")
        self.assertEqual(first, self.packet(6, "--seed", 3, "--stratify"))
        # groups: level 1 own (2), level 2 inherited (3), level 2 own (1), level 3 inherited (8)
        self.assertEqual(first["groups"], {"level 1 own": 2, "level 2 inherited": 2, "level 2 own": 1,
                                           "level 3 inherited": 1})
        entry = next(e for e in first["entries"] if e["level"] == 3)
        self.assertEqual([a["id"] for a in entry["chain"]], [entry["id"].rsplit(".", 1)[0].split(".")[0],
                                                             entry["id"].rsplit(".", 1)[0]])
        self.assertIsNotNone(entry["inherited_from"])
        self.assertIn("IMP-1", first["codes"])

    def test_via_and_level_filters(self):
        picked = self.packet(20, "--seed", 1, "--via", "inherited", "--level", 3)["entries"]
        self.assertEqual(len(picked), 8)
        self.assertTrue(all(e["level"] == 3 and e["inherited_from"] for e in picked))
        own = self.packet(20, "--seed", 1, "--via", "own")["entries"]
        self.assertEqual(sorted(e["id"] for e in own), ["1", "1.1", "2"])


class AuditTests(LedgerCase):
    def test_wilson_interval_matches_known_values(self):
        self.assertEqual(ledger.wilson(5, 10), [0.2366, 0.7634])
        self.assertEqual(ledger.wilson(0, 10), [0.0, 0.2775])

    def test_report_rates_groups_and_agreement(self):
        a = self.verdicts("a.json", [{"id": "1", "verdict": "fit"}, {"id": "1.2", "verdict": "wrong", "note": "IMP-1"},
                                     {"id": "2.1.1", "verdict": "fit"}, {"id": "2", "verdict": "adjacent", "note": "x"}])
        b = self.verdicts("b.json", [{"id": "1", "verdict": "fit"}, {"id": "1.2", "verdict": "fit"},
                                     {"id": "2", "verdict": "adjacent", "note": "x"}], independent=False)
        report = json.loads(self.cli("audit", a, b).stdout)
        first = report["files"][0]
        self.assertEqual((first["n"], first["wrong"], first["adjacent"], first["wrong_rate"]), (4, 1, 1, 0.25))
        self.assertEqual(first["groups"]["level 2 inherited"], {"n": 1, "fit": 0, "adjacent": 0, "wrong": 1})
        self.assertEqual(report["agreement"]["common"], 3)
        self.assertEqual(report["agreement"]["disagreements"], [{"id": "1.2", "a": "wrong", "b": "fit"}])

    def test_malformed_verdict_files_are_rejected(self):
        bad = self.verdicts("bad.json", [{"id": "9.9", "verdict": "fit"}, {"id": "1", "verdict": "maybe"},
                                         {"id": "2", "verdict": "wrong"}])
        proc = self.cli("audit", bad, ok=False)
        self.assertEqual(proc.returncode, 1)
        for text in ("no ledger entry '9.9'", "verdict must be one of", "needs a note"):
            self.assertIn(text, proc.stdout)
        missing_fields = self.round / "empty.json"
        missing_fields.write_text(json.dumps({"entries": [{"id": "1", "verdict": "fit"}]}))
        out = self.cli("audit", missing_fields, ok=False).stdout
        self.assertIn("reviewer: required", out)
        self.assertIn("independent: must be true or false", out)


if __name__ == "__main__":
    unittest.main()
