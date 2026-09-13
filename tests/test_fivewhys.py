"""Tests for scripts/fivewhys.py. Run from the repo root: python3 -m unittest discover tests"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fivewhys.py"


def run(*args, stdin: str = "", ok: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          input=stdin, capture_output=True, text=True)
    if ok and proc.returncode != 0:
        raise AssertionError(f"{args} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}")
    return proc


def words(label: str) -> str:
    """Unique filler words, so synthetic reasons never look alike to hygiene."""
    return " ".join(hashlib.md5(f"{label}-{k}".encode()).hexdigest()[:8] for k in range(4))


def fragment(breadth: int, levels: int, tag: str) -> dict:
    def build(level: int, prefix: str) -> list:
        items = []
        for i in range(1, breadth + 1):
            label = f"{prefix}.{i}" if prefix else str(i)
            item = {"reason": f"{words(tag + label)}."}
            if level < levels:
                item["whys"] = build(level + 1, label)
            items.append(item)
        return items
    return {"whys": build(1, "")}


def tree_ids(nodes) -> list[str]:
    ids = []
    for node in nodes:
        ids.append(node["id"])
        ids.extend(tree_ids(node.get("whys", [])))
    return ids


class RunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, *flags, problem="Deploys fail on Friday afternoons"):
        out = json.loads(run("init", "--base", self.base, *flags, stdin=problem).stdout)
        return Path(out["run"]), out

    def plan(self, run_dir, *flags) -> dict:
        return json.loads(run("plan", run_dir, *flags).stdout)

    def write(self, path, data) -> None:
        Path(path).write_text(json.dumps(data))

    def read(self, path) -> dict:
        return json.loads(Path(path).read_text())

    def fill_root(self, run_dir, breadth, split) -> dict:
        data = fragment(breadth, split, "root")
        self.write(run_dir / "fragments" / "root.json", data)
        return data

    def fill_branches(self, run_dir, breadth, levels, skip=()) -> None:
        for node_id in json.loads(run("status", run_dir).stdout)["missing"]:
            if node_id not in skip:
                self.write(run_dir / "fragments" / f"branch-{node_id}.json", fragment(breadth, levels, f"b{node_id}"))


class InitTests(RunCase):
    def test_full_default_shape_and_estimate(self):
        run_dir, out = self.init()
        self.assertEqual(out["shape"], {"breadth": 5, "depth": 5, "split": 2})
        self.assertEqual((out["estimate"]["agents"], out["estimate"]["reasons"]), (26, 3905))
        meta = self.read(run_dir / "run.json")
        self.assertEqual((meta["model"], meta["problem"]), ("inherit", "Deploys fail on Friday afternoons"))

    def test_smoke_preset(self):
        _, out = self.init("--preset", "smoke")
        self.assertEqual(out["shape"], {"breadth": 3, "depth": 3, "split": 1})
        self.assertEqual((out["estimate"]["agents"], out["estimate"]["reasons"]), (4, 39))

    def test_rejects_empty_problem_and_bad_split(self):
        self.assertNotEqual(run("init", "--base", self.base, stdin="  ", ok=False).returncode, 0)
        bad = run("init", "--base", self.base, "--depth", "3", "--split", "4", stdin="x", ok=False)
        self.assertNotEqual(bad.returncode, 0)

    def test_same_problem_twice_gets_distinct_runs(self):
        first, _ = self.init("--preset", "smoke")
        second, _ = self.init("--preset", "smoke")
        self.assertNotEqual(first, second)

    def test_context_file_reaches_prompts(self):
        context = self.base / "context.md"
        context.write_text("Kubernetes cluster, deploys via Argo CD.")
        run_dir, _ = self.init("--context-file", context)
        self.assertIn("Argo CD", self.plan(run_dir)["tasks"][0]["prompt"])


class PlanTests(RunCase):
    def test_root_first_then_capped_waves(self):
        run_dir, _ = self.init("--preset", "smoke", "--max-parallel", "2")
        first = self.plan(run_dir)
        self.assertEqual((first["state"], [t["id"] for t in first["tasks"]]), ("root", ["root"]))
        self.fill_root(run_dir, 3, 1)
        second = self.plan(run_dir)
        self.assertEqual(second["state"], "branches")
        self.assertEqual([t["id"] for t in second["tasks"]], ["1", "2"])
        self.assertEqual(second["waiting"], ["3"])

    def test_full_run_waves_respect_default_cap(self):
        run_dir, _ = self.init()
        self.fill_root(run_dir, 5, 2)
        plan = self.plan(run_dir)
        self.assertEqual((len(plan["tasks"]), len(plan["waiting"])), (20, 5))

    def test_only_filters_branches(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_root(run_dir, 3, 1)
        self.assertEqual([t["id"] for t in self.plan(run_dir, "--only", "2")["tasks"]], ["2"])

    def test_branch_prompt_lists_other_reasons_but_not_its_own_chain(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = self.fill_root(run_dir, 3, 1)
        prompt = next(t["prompt"] for t in self.plan(run_dir)["tasks"] if t["id"] == "2")
        self.assertIn(f"- 1: {root['whys'][0]['reason']}", prompt)
        self.assertIn(f"- 3: {root['whys'][2]['reason']}", prompt)
        self.assertNotIn("- 2: ", prompt)
        self.assertIn(f"Why level 1 (id 2): {root['whys'][1]['reason']}", prompt)
        self.assertIn("--breadth 3 --depth 2", prompt)

    def test_model_override_is_emitted_only_when_chosen(self):
        chosen, _ = self.init("--preset", "smoke", "--model", "sonnet")
        self.assertEqual(self.plan(chosen)["tasks"][0]["model"], "sonnet")
        inherited, _ = self.init("--preset", "smoke")
        self.assertIsNone(self.plan(inherited)["tasks"][0]["model"])

    def test_recorded_attempts_mark_task_stuck(self):
        run_dir, _ = self.init("--preset", "smoke")
        for _ in range(3):
            self.plan(run_dir, "--record")
        stuck = self.plan(run_dir)
        self.assertEqual((stuck["state"], stuck["tasks"]), ("stuck", []))
        self.assertEqual((stuck["stuck"][0]["id"], stuck["stuck"][0]["attempts"]), ("root", 3))

    def test_v01_run_without_shape_still_plans(self):
        run_dir = self.base / "legacy"
        (run_dir / "fragments").mkdir(parents=True)
        self.write(run_dir / "run.json", {"schema": "five-whys/1", "problem": "p",
                                          "created": "2026-09-13T14:07:31-07:00", "branching": 5, "depth": 5})
        plan = self.plan(run_dir)
        self.assertEqual(plan["tasks"][0]["id"], "root")
        self.assertIn("--breadth 5 --depth 2", plan["tasks"][0]["prompt"])


class CheckTests(RunCase):
    def check(self, data, breadth, depth):
        path = self.base / "fragment.json"
        self.write(path, data)
        return run("check", path, "--breadth", breadth, "--depth", depth, ok=False)

    def test_valid_fragment_passes(self):
        proc = self.check(fragment(5, 3, "x"), 5, 3)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_miscount_reports_its_position(self):
        data = fragment(5, 2, "x")
        data["whys"][1]["whys"].pop()
        proc = self.check(data, 5, 2)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("item 2's whys: expected 5 reasons, got 4", proc.stdout)

    def test_leaf_with_whys_and_bad_assumptions_are_rejected(self):
        data = fragment(2, 1, "x")
        data["whys"][0]["whys"] = [{"reason": "extra"}]
        data["assumptions"] = [3]
        out = self.check(data, 2, 1).stdout
        self.assertIn("item 1: deepest reasons must not have whys", out)
        self.assertIn("assumptions: must be a list of strings", out)


class AssembleTests(RunCase):
    def smoke_run(self):
        run_dir, _ = self.init("--preset", "smoke")
        return run_dir, self.fill_root(run_dir, 3, 1)

    def test_full_5x5_assembles_every_reason_once(self):
        run_dir, _ = self.init()
        self.fill_root(run_dir, 5, 2)
        self.fill_branches(run_dir, 5, 3)
        self.assertEqual(self.plan(run_dir)["state"], "ready")
        summary = json.loads(run("assemble", run_dir).stdout)
        self.assertTrue(summary["complete"])
        tree = self.read(run_dir / "five-whys.json")
        ids = tree_ids(tree["whys"])
        self.assertEqual((len(ids), len(set(ids))), (3905, 3905))
        self.assertEqual([level["reasons"] for level in tree["levels"]], [5, 25, 125, 625, 3125])
        self.assertTrue((run_dir / "index.md").exists())
        self.assertEqual(self.read(run_dir / "run.json")["output"]["bytes"], summary["bytes"])

    def test_hygiene_flags_duplicates_and_restatements_without_removing_them(self):
        run_dir, root = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        fragments = run_dir / "fragments"
        b1, b2, b3 = (self.read(fragments / f"branch-{i}.json") for i in (1, 2, 3))
        b1["whys"][0]["reason"] = root["whys"][0]["reason"]
        b3["whys"][1]["reason"] = b2["whys"][1]["reason"]
        self.write(fragments / "branch-1.json", b1)
        self.write(fragments / "branch-3.json", b3)
        run("assemble", run_dir)
        flags = self.read(run_dir / "hygiene.json")
        self.assertIn(["2.2", "3.2"], flags["exact_duplicates"])
        self.assertIn({"id": "1.1", "of": "1", "similarity": 1.0}, flags["restates_parent"])
        self.assertEqual(self.read(run_dir / "five-whys.json")["present_reasons"], 39)

    def test_hygiene_catches_close_rewording_across_branches(self):
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        fragments = run_dir / "fragments"
        b1, b2 = self.read(fragments / "branch-1.json"), self.read(fragments / "branch-2.json")
        b1["whys"][0]["reason"] = "The validator only checks JSON shape, never reason content."
        b2["whys"][2]["reason"] = "Validator checks only the JSON shape and never the content of reasons."
        self.write(fragments / "branch-1.json", b1)
        self.write(fragments / "branch-2.json", b2)
        run("assemble", run_dir)
        pairs = {(p["a"], p["b"]) for p in self.read(run_dir / "hygiene.json")["near_duplicates"]}
        self.assertIn(("1.1", "2.3"), pairs)

    def test_partial_assembly_marks_missing_branch(self):
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2, skip=("2",))
        self.assertNotEqual(run("assemble", run_dir, ok=False).returncode, 0)
        summary = json.loads(run("assemble", run_dir, "--partial").stdout)
        self.assertEqual((summary["complete"], summary["missing_branches"]), (False, ["2"]))
        tree = self.read(run_dir / "five-whys.json")
        self.assertTrue(tree["whys"][1]["missing"])
        self.assertEqual(tree["present_reasons"], 3 + 2 * 12)
        self.assertIn("(branch missing)", (run_dir / "index.md").read_text())

    def test_assumptions_are_carried_into_output(self):
        run_dir, root = self.smoke_run()
        root["assumptions"] = ["Deploys run through a single CI pipeline."]
        self.write(run_dir / "fragments" / "root.json", root)
        self.fill_branches(run_dir, 3, 2)
        run("assemble", run_dir)
        tree = self.read(run_dir / "five-whys.json")
        self.assertEqual(tree["assumptions"], {"root": ["Deploys run through a single CI pipeline."]})

    def test_breadth_ten_uses_multi_digit_ids(self):
        run_dir, out = self.init("--breadth", "10", "--depth", "2")
        self.assertEqual(out["estimate"]["agents"], 11)
        self.fill_root(run_dir, 10, 1)
        self.fill_branches(run_dir, 10, 1)
        run("assemble", run_dir)
        shown = run("show", run_dir, "--id", "10.10").stdout.splitlines()
        self.assertTrue(shown[0].startswith("^ 10  "))
        self.assertTrue(shown[1].strip().startswith("10.10  "))


class StatusAndShowTests(RunCase):
    def test_status_counts_fragments(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_root(run_dir, 3, 1)
        status = json.loads(run("status", run_dir).stdout)
        self.assertEqual((status["done"], status["total"], status["missing"]), (1, 4, ["1", "2", "3"]))

    def test_show_prints_ancestors_and_limits_levels(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = self.fill_root(run_dir, 3, 1)
        self.fill_branches(run_dir, 3, 2)
        run("assemble", run_dir)
        lines = run("show", run_dir, "--id", "2.1", "--levels", "1").stdout.splitlines()
        self.assertEqual(lines[0], f"^ 2  {root['whys'][1]['reason']}")
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(run("show", run_dir, "--levels", "1").stdout.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
