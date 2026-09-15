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


class InputTreeTests(unittest.TestCase):
    def test_levels_ignore_the_input_number_at_the_start_of_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "round-9"
            (folder / "ledger").mkdir(parents=True)
            (folder / "tree.json").write_text(json.dumps({"schema": "five-whys/3", "inputs": [
                {"id": str(k), "depth": 0, "input": f"Input {k}", "whys": tree(2, 2, str(k))} for k in (1, 2)]}))
            (folder / "catalog.json").write_text(json.dumps({
                "improvements": [], "dispositions": [{"code": "X-HIST", "title": "History", "detail": "d"}]}))
            (folder / "ledger" / "a.txt").write_text("".join(f"{k}.{i} X-HIST note\n" for k in (1, 2) for i in (1, 2)))

            def cli(*args):
                return subprocess.run([sys.executable, str(LEDGER), str(folder), *map(str, args)],
                                      capture_output=True, text=True, check=True).stdout
            self.assertEqual(json.loads(cli("merge"))["reasons"], 12)
            packet = json.loads(cli("sample", 20, "--seed", 1, "--level", 2, "--json"))
            self.assertEqual(len(packet["entries"]), 8)
            self.assertTrue(all(e["level"] == 2 and e["id"].count(".") == 2 for e in packet["entries"]))
            self.assertEqual(set(json.loads(cli("sample", 20, "--seed", 1, "--stratify", "--json"))["groups"]),
                             {"level 1 own", "level 2 inherited"})


class QuestionTreeTests(unittest.TestCase):
    def test_levels_ignore_the_input_and_question_at_the_start_of_ids(self):
        def answers(prefix, level=1):
            return [{"id": f"{prefix}.{i}", "depth": level, "answer": f"Answer {prefix}.{i}.",
                     **({"answers": answers(f"{prefix}.{i}", level + 1)} if level < 2 else {})} for i in (1, 2)]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "round-9"
            (folder / "ledger").mkdir(parents=True)
            (folder / "tree.json").write_text(json.dumps({"schema": "five-whys/4", "inputs": [
                {"id": "1", "depth": 0, "input": "Input 1", "trees": [
                    {"id": "1.why", "question": "why", "answers": answers("1.why")},
                    {"id": "1.how", "question": "how", "answers": answers("1.how")}]}]}))
            (folder / "catalog.json").write_text(json.dumps({
                "improvements": [], "dispositions": [{"code": "X-HIST", "title": "History", "detail": "d"}]}))
            (folder / "ledger" / "a.txt").write_text(
                "".join(f"1.{q}.{i} X-HIST note\n" for q in ("why", "how") for i in (1, 2)))

            def cli(*args):
                return subprocess.run([sys.executable, str(LEDGER), str(folder), *map(str, args)],
                                      capture_output=True, text=True, check=True).stdout
            self.assertEqual(json.loads(cli("merge"))["reasons"], 12)
            packet = json.loads(cli("sample", 20, "--seed", 1, "--level", 2, "--json"))
            self.assertEqual(len(packet["entries"]), 8)
            self.assertTrue(all(e["level"] == 2 for e in packet["entries"]))
            self.assertIn("Answer 1.how.1.", [c["reason"] for e in packet["entries"] for c in e["chain"]])


class VerifyAndDeferralTests(LedgerCase):
    def write_verification(self, records):
        (self.round / "verification.json").write_text(json.dumps({"improvements": records}))

    def test_verify_counts_statuses_and_requires_every_improvement(self):
        self.write_verification({})
        self.assertIn("IMP-1: no verification record", self.cli("verify", ok=False).stdout)
        self.write_verification({"IMP-1": {"status": "observed", "evidence": "seen in a run"}})
        self.assertIn("needs the commit", self.cli("verify", ok=False).stdout)
        self.write_verification({"IMP-1": {"status": "blocked", "evidence": "eval refused"}})
        self.assertEqual(json.loads(self.cli("verify").stdout),
                         {"improvements": 1, "observed": 0, "blocked": ["IMP-1"], "not_run": []})

    def test_schema_3_catalog_needs_deferral_triggers(self):
        catalog = json.loads((self.round / "catalog.json").read_text())
        catalog["schema"] = 3
        catalog["dispositions"].append({"code": "R-1", "title": "Deferred: a study", "detail": "d"})
        (self.round / "catalog.json").write_text(json.dumps(catalog))
        out = self.cli("check", self.round / "ledger" / "a.txt", ok=False).stdout
        self.assertIn("R-1: a deferred disposition needs a deferral object", out)
        catalog["dispositions"][-1]["deferral"] = {"kind": "study", "trigger": "two outside users", "cost": "10 runs"}
        (self.round / "catalog.json").write_text(json.dumps(catalog))
        self.assertIn("OK", self.cli("check", self.round / "ledger" / "a.txt").stdout)


if __name__ == "__main__":
    unittest.main()
