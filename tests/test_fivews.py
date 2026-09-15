"""Tests for scripts/fivews.py. Run from the repo root: python3 -m unittest discover tests"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fivews.py"
READ_WINDOW_BYTES = int(re.search(r"READ_WINDOW_BYTES = ([\d_]+)", SCRIPT.read_text()).group(1).replace("_", ""))
PROBLEM = "Deploys fail on Friday afternoons"


def run(*args, stdin: str = "", ok: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          input=stdin, capture_output=True, text=True)
    if ok and proc.returncode != 0:
        raise AssertionError(f"{args} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}")
    return proc


def words(label: str) -> str:
    """Unique filler words, so synthetic answers never look alike to hygiene."""
    return " ".join(hashlib.md5(f"{label}-{k}".encode()).hexdigest()[:8] for k in range(4))


def fragment(breadth: int, levels: int, tag: str) -> dict:
    def build(level: int, prefix: str) -> list:
        items = []
        for i in range(1, breadth + 1):
            label = f"{prefix}.{i}" if prefix else str(i)
            item = {"answer": f"{words(tag + label)}."}
            if level < levels:
                item["answers"] = build(level + 1, label)
            items.append(item)
        return items
    return {"answers": build(1, "")}


def group(breadth: int, levels: int, first: int, last: int) -> dict:
    return {"trees": [fragment(breadth, levels, f"tree{k}") for k in range(first, last + 1)]}


def span(name: str) -> tuple[int, int]:
    match = re.fullmatch(r"roots-(\d+)(?:-(\d+))?(?:\.json)?", name)
    return int(match.group(1)), int(match.group(2) or match.group(1))


def answer_ids(nodes) -> list[str]:
    ids = []
    for node in nodes:
        ids.append(node["id"])
        ids.extend(answer_ids(node.get("answers", [])))
    return ids


def fake_agent(task: dict, tag: str, broken: bool = False) -> subprocess.CompletedProcess:
    """Do what the expander agent does: read the prompt file, write the fragment, run the check it names."""
    lines = Path(task["prompt_file"]).read_text().splitlines()
    path = Path(lines[lines.index("Write them as JSON to:") + 1])
    command = shlex.split(lines[lines.index("Then run:") + 1])
    breadth, levels = (int(command[command.index(flag) + 1]) for flag in ("--breadth", "--depth"))
    if path.name.startswith("roots-"):
        data = group(breadth, levels, *span(path.name))
        if broken:
            data["trees"].pop()
    else:
        data = fragment(breadth, levels, tag)
        if broken:
            data["answers"].pop()
    path.write_text(json.dumps(data))
    return subprocess.run([sys.executable, *command[1:]], capture_output=True, text=True)


class RunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, *flags, problem=PROBLEM):
        out = json.loads(run("init", "--base", self.base, *flags, stdin=problem).stdout)
        return Path(out["run"]), out

    def plan(self, run_dir, *flags) -> dict:
        return json.loads(run("plan", run_dir, *flags).stdout)

    def status(self, run_dir) -> dict:
        return json.loads(run("status", run_dir).stdout)

    def parse(self, text: str) -> dict:
        return json.loads(run("parse", stdin=text, ok=False).stdout)

    def write(self, path, data) -> None:
        Path(path).write_text(json.dumps(data))

    def read(self, path) -> dict:
        return json.loads(Path(path).read_text())

    def prompt(self, task) -> str:
        return Path(task["prompt_file"]).read_text()

    def fill_roots(self, run_dir, breadth, split) -> dict:
        """Write every missing root group; return {tree id: its answers}."""
        meta = self.read(run_dir / "run.json")
        trees = [f"{k}.{q}" for k in range(1, len(meta["inputs"]) + 1) for q in meta["questions"]]
        roots = {}
        for gid in [m for m in self.status(run_dir)["missing"] if m.startswith("roots-")]:
            first, last = span(gid)
            data = group(breadth, split, first, last)
            self.write(run_dir / "fragments" / f"{gid}.json", data)
            roots.update({trees[first - 1 + k]: item["answers"] for k, item in enumerate(data["trees"])})
        return roots

    def fill_branches(self, run_dir, breadth, levels, skip=()) -> None:
        for node_id in self.status(run_dir)["missing"]:
            if node_id not in skip:
                self.write(run_dir / "fragments" / f"branch-{node_id}.json", fragment(breadth, levels, f"b{node_id}"))


class ParseTests(RunCase):
    def test_leading_options_become_init_flags(self):
        out = self.parse("--smoke --model-level 2 Our deploys fail on Fridays")
        self.assertEqual((out["inputs"], out["questions"], out["init_flags"], out["yes"], out["errors"]),
                         (["Our deploys fail on Fridays"], ["why"], "--preset smoke --model-level 2 --ask why", False, []))

    def test_separator_equals_and_quoted_values(self):
        context = self.base / "my context.md"
        context.write_text("Kubernetes")
        out = self.parse(f"--depth=3 --context-file '{context}' -- --verbose logs aren't kept")
        self.assertEqual(out["inputs"], ["--verbose logs aren't kept"])
        self.assertEqual(shlex.split(out["init_flags"]), ["--depth", "3", "--context-file", str(context), "--ask", "why"])

    def test_input_text_is_kept_verbatim_after_the_options(self):
        out = self.parse("--yes The team's `make deploy` fails with $HOME unset")
        self.assertEqual((out["inputs"], out["yes"]), (["The team's `make deploy` fails with $HOME unset"], True))

    def test_each_line_is_an_input_and_list_markers_are_removed(self):
        out = self.parse("--depth 2\n1. Deploys fail on Fridays\n2) Login is slow after 9am\n\n- Nightly backups skip runs\n")
        self.assertEqual(out["inputs"], ["Deploys fail on Fridays", "Login is slow after 9am", "Nightly backups skip runs"])
        self.assertEqual((out["input_hints"], out["errors"]), ([], []))

    def test_unclear_splits_produce_hints_for_the_skill_to_ask_about(self):
        self.assertTrue(self.parse("1) deploys fail 2) login is slow 3) backups skip")["input_hints"])
        self.assertTrue(self.parse("Deploys fail whenever the\nrunner restarts mid-job")["input_hints"])
        self.assertEqual(self.parse("Deploys fail.\nLogin is slow.")["input_hints"], [])

    def test_ask_takes_any_combination_of_the_five_questions(self):
        self.assertEqual(self.parse("--ask what,how Deploys fail")["questions"], ["what", "how"])
        self.assertEqual(self.parse("--ask 'how and where' Deploys fail")["questions"], ["how", "where"])
        self.assertEqual(self.parse("--ask why,what,when,where,how x")["questions"], ["why", "what", "when", "where", "how"])
        self.assertIn("--ask takes any of why, what, when, where, how, comma-separated",
                      self.parse("--ask who Deploys fail")["errors"])

    def test_questions_can_be_chosen_in_plain_words(self):
        out = self.parse("ask how and where for: Deploys fail on Fridays")
        self.assertEqual((out["questions"], out["questions_from_words"], out["inputs"]),
                         (["how", "where"], True, ["Deploys fail on Fridays"]))
        self.assertTrue(out["notes"])
        listed = self.parse("Answer what, when questions about:\n- Deploys fail\n- Login is slow")
        self.assertEqual((listed["questions"], listed["inputs"]), (["what", "when"], ["Deploys fail", "Login is slow"]))
        self.assertEqual(self.parse("Deploys fail")["questions"], ["why"])
        flag_wins = self.parse("--ask why ask how for: x")
        self.assertEqual((flag_wins["questions"], flag_wins["inputs"]), (["why"], ["ask how for: x"]))

    def test_depth_and_model_level_must_be_one_to_five(self):
        for flag in ("--depth", "--model-level"):
            for value in ("0", "6", "two"):
                self.assertIn(f"{flag} must be a whole number from 1 to 5", self.parse(f"{flag} {value} x")["errors"])
            self.assertEqual(self.parse(f"{flag} 5 x")["errors"], [])

    def test_bad_options_are_errors_not_input_text(self):
        self.assertIn("unknown option --smok", self.parse("--smok Deploys fail")["errors"][0])
        self.assertIn("unknown option --model", self.parse("--model opus Deploys fail")["errors"][0])
        self.assertIn("no input after the options", self.parse("--yes")["errors"][0])
        self.assertNotEqual(run("parse", stdin="--yes", ok=False).returncode, 0)

    def test_resume_rules(self):
        run_dir, _ = self.init("--preset", "smoke")
        ok = self.parse(f"--resume {run_dir} --max-parallel 2")
        self.assertEqual((ok["errors"], ok["resume"], ok["plan_flags"], ok["init_flags"], ok["inputs"]),
                         ([], str(run_dir), "--max-parallel 2", "", []))
        self.assertTrue(self.parse(f"--resume {run_dir} --depth 3")["errors"])
        self.assertTrue(self.parse(f"--resume {run_dir} --ask how")["errors"])
        self.assertTrue(self.parse(f"--resume {run_dir} extra words")["errors"])
        self.assertTrue(self.parse(f"--resume {self.base}")["errors"])

    def test_script_path_is_absolute_for_later_steps(self):
        script = Path(self.parse("--smoke Deploys fail")["script"])
        self.assertTrue(script.is_absolute())
        self.assertEqual(script, SCRIPT.resolve())

    def test_smoke_with_shape_overrides_is_noted(self):
        self.assertTrue(self.parse("--smoke --depth 4 Deploys fail")["notes"])


class InitTests(RunCase):
    def test_full_default_shape_estimate_and_confirmation(self):
        run_dir, out = self.init()
        self.assertEqual((out["shape"], out["inputs"], out["questions"], out["trees"]),
                         ({"breadth": 5, "depth": 5, "split": 2}, 1, ["why"], 1))
        self.assertEqual((out["estimate"]["agents"], out["estimate"]["answers"], out["confirm"]), (26, 3905, True))
        meta = self.read(run_dir / "run.json")
        self.assertEqual((meta["inputs"], meta["questions"], meta["model_level"], meta["models"], meta["max_parallel"]),
                         ([PROBLEM], ["why"], None, None, 5))

    def test_smoke_preset_needs_no_confirmation(self):
        _, out = self.init("--preset", "smoke")
        self.assertEqual(out["shape"], {"breadth": 3, "depth": 3, "split": 1})
        self.assertEqual((out["estimate"]["agents"], out["estimate"]["answers"], out["confirm"]), (4, 39, False))

    def test_size_scales_with_inputs_questions_and_depth(self):
        ten = "\n".join(f"Problem number {k} keeps happening" for k in range(1, 11))
        cases = {  # (depth, inputs, questions): (split, agents, answers)
            (1, 10, "why"): (1, 1, 50),
            (2, 10, "why"): (2, 2, 300),
            (3, 1, "why,how"): (3, 2, 310),
            (4, 1, "why"): (1, 6, 780),
            (4, 10, "why"): (1, 51, 7800),
            (5, 10, "why"): (2, 252, 39050),
            (5, 1, "why,what,when,where,how"): (2, 126, 19525),
        }
        for (depth, count, ask), expected in cases.items():
            _, out = self.init("--depth", depth, "--ask", ask, problem=ten if count == 10 else PROBLEM)
            self.assertEqual((out["shape"]["split"], out["estimate"]["agents"], out["estimate"]["answers"]), expected,
                             (depth, count, ask))
            self.assertEqual(out["trees"], count * len(ask.split(",")))

    def test_model_level_records_the_mix_for_roots_and_branches(self):
        levels = {1: ("haiku", "haiku"), 2: ("sonnet", "haiku"), 3: ("sonnet", "sonnet"), 4: ("opus", "sonnet"),
                  5: ("opus", "opus")}
        for level, (roots, branches) in levels.items():
            run_dir, out = self.init("--model-level", level)
            self.assertEqual(out["models"], {"roots": roots, "branches": branches})
            self.assertEqual(self.read(run_dir / "run.json")["model_level"], level)

    def test_run_records_version_options_and_estimate(self):
        run_dir, out = self.init("--preset", "smoke", "--model-level", "3")
        meta = self.read(run_dir / "run.json")
        version = self.read(ROOT / ".claude-plugin" / "plugin.json")["version"]
        self.assertEqual((meta["plugin_version"], out["plugin_version"]), (version, version))
        self.assertEqual(meta["options"][-4:], ["--preset", "smoke", "--model-level", "3"])
        self.assertEqual(meta["estimate"], out["estimate"])

    def test_rejects_empty_input_bad_shapes_questions_and_oversized_waves(self):
        self.assertNotEqual(run("init", "--base", self.base, stdin="  \n ", ok=False).returncode, 0)
        for flags in (("--depth", "3", "--split", "4"), ("--depth", "6"), ("--depth", "0"), ("--ask", "who"),
                      ("--model-level", "6"), ("--max-parallel", "21"), ("--model", "opus")):
            self.assertNotEqual(run("init", "--base", self.base, *flags, stdin="x", ok=False).returncode, 0, flags)

    def test_same_problem_twice_gets_distinct_runs(self):
        first, _ = self.init("--preset", "smoke")
        second, _ = self.init("--preset", "smoke")
        self.assertNotEqual(first, second)

    def test_context_file_reaches_prompts(self):
        context = self.base / "context.md"
        context.write_text("Kubernetes cluster, deploys via Argo CD.")
        run_dir, _ = self.init("--context-file", context)
        self.assertIn("Argo CD", self.prompt(self.plan(run_dir)["tasks"][0]))

    def test_run_base_is_gitignored(self):
        self.init("--preset", "smoke")
        self.assertIn("*", (self.base / ".gitignore").read_text().splitlines())


class PlanTests(RunCase):
    def test_dispatch_prompt_points_at_full_prompt_file(self):
        run_dir, _ = self.init("--preset", "smoke")
        task = self.plan(run_dir)["tasks"][0]
        self.assertLess(len(task["prompt"]), 300)
        self.assertIn(task["prompt_file"], task["prompt"])
        text = self.prompt(task)
        self.assertIn("Write them as JSON to:", text)
        self.assertIn("output tokens with the JSON", text)
        self.assertIn(f"Input: {PROBLEM}", text)
        self.assertIn("Level 1 asks: Why does this happen?", text)

    def test_root_first_then_capped_waves(self):
        run_dir, _ = self.init("--preset", "smoke", "--max-parallel", "2")
        first = self.plan(run_dir)
        self.assertEqual((first["state"], [t["id"] for t in first["tasks"]]), ("root", ["roots-1"]))
        self.fill_roots(run_dir, 3, 1)
        second = self.plan(run_dir)
        self.assertEqual(second["state"], "branches")
        self.assertEqual([t["id"] for t in second["tasks"]], ["1.why.1", "1.why.2"])
        self.assertEqual(second["waiting"], ["1.why.3"])

    def test_full_run_waves_default_to_five(self):
        run_dir, _ = self.init()
        self.fill_roots(run_dir, 5, 2)
        plan = self.plan(run_dir)
        self.assertEqual((len(plan["tasks"]), len(plan["waiting"])), (5, 20))

    def test_root_group_holds_several_trees_and_branches_stay_within_their_tree(self):
        twelve = "\n".join(f"Service {k} times out under load" for k in range(1, 13))
        run_dir, _ = self.init("--depth", "4", problem=twelve)
        root = self.plan(run_dir)["tasks"]
        self.assertEqual([t["id"] for t in root], ["roots-1-12"])
        text = self.prompt(root[0])
        self.assertIn("Tree 12: input 12, question WHY", text)
        self.assertIn("12 in all, in the order listed", text)
        roots = self.fill_roots(run_dir, 5, 1)
        plan = self.plan(run_dir)
        self.assertEqual((len(plan["tasks"]), len(plan["waiting"])), (5, 55))
        prompt = self.prompt(next(t for t in plan["tasks"] if t["id"] == "1.why.3"))
        self.assertIn(f"- 1.why.1: {roots['1.why'][0]['answer']}", prompt)
        self.assertNotIn(roots["2.why"][0]["answer"], prompt)

    def test_each_question_gets_its_own_tree_and_wording(self):
        run_dir, _ = self.init("--ask", "why,how", "--depth", "4")
        self.assertIn("Tree 2: input 1, question HOW", self.prompt(self.plan(run_dir)["tasks"][0]))
        roots = self.fill_roots(run_dir, 5, 1)
        waiting = self.plan(run_dir, "--only", "1.how.2")
        prompt = self.prompt(waiting["tasks"][0])
        self.assertIn("Question: HOW. Answers are mechanisms", prompt)
        self.assertIn(f'answers to "How does this come about: {roots["1.how"][1]["answer"]}"', prompt)
        self.assertIn(f"- 1.how.1: {roots['1.how'][0]['answer']}", prompt)
        self.assertNotIn(roots["1.why"][0]["answer"], prompt)

    def test_model_level_sets_root_and_branch_models(self):
        mixed, _ = self.init("--preset", "smoke", "--model-level", "2")
        self.assertEqual(self.plan(mixed)["tasks"][0]["model"], "sonnet")
        self.fill_roots(mixed, 3, 1)
        self.assertEqual({t["model"] for t in self.plan(mixed)["tasks"]}, {"haiku"})
        inherited, _ = self.init("--preset", "smoke")
        self.assertIsNone(self.plan(inherited)["tasks"][0]["model"])

    def test_resumed_run_can_change_its_wave_size(self):
        run_dir, _ = self.init()
        self.fill_roots(run_dir, 5, 2)
        self.assertEqual(len(self.plan(run_dir, "--max-parallel", "3")["tasks"]), 3)
        self.assertEqual(self.read(run_dir / "run.json")["max_parallel"], 3)
        self.assertNotEqual(run("plan", run_dir, "--max-parallel", "40", ok=False).returncode, 0)

    def test_only_filters_branches(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_roots(run_dir, 3, 1)
        self.assertEqual([t["id"] for t in self.plan(run_dir, "--only", "1.why.2")["tasks"]], ["1.why.2"])

    def test_branch_prompt_lists_other_answers_but_not_its_own_chain(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = self.fill_roots(run_dir, 3, 1)["1.why"]
        prompt = self.prompt(next(t for t in self.plan(run_dir)["tasks"] if t["id"] == "1.why.2"))
        self.assertIn(f"- 1.why.1: {root[0]['answer']}", prompt)
        self.assertIn(f"- 1.why.3: {root[2]['answer']}", prompt)
        self.assertNotIn("- 1.why.2: ", prompt)
        self.assertIn(f"Level 1 (id 1.why.2): {root[1]['answer']}", prompt)
        self.assertIn("--breadth 3 --depth 2", prompt)

    def test_later_waves_see_first_level_answers_of_finished_branches(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_roots(run_dir, 3, 1)
        self.fill_branches(run_dir, 3, 2, skip=("1.why.2", "1.why.3"))
        finished = self.read(run_dir / "fragments" / "branch-1.why.1.json")
        prompt = self.prompt(next(t for t in self.plan(run_dir)["tasks"] if t["id"] == "1.why.2"))
        self.assertIn(f"- 1.why.1.1: {finished['answers'][0]['answer']}", prompt)
        self.assertNotIn(finished["answers"][0]["answers"][0]["answer"], prompt)

    def test_recorded_attempts_mark_task_stuck(self):
        run_dir, _ = self.init("--preset", "smoke")
        for _ in range(3):
            self.plan(run_dir, "--record")
        stuck = self.plan(run_dir)
        self.assertEqual((stuck["state"], stuck["tasks"]), ("stuck", []))
        self.assertEqual((stuck["stuck"][0]["id"], stuck["stuck"][0]["attempts"]), ("roots-1", 3))

    def test_runs_from_older_versions_are_refused_with_an_explanation(self):
        run_dir = self.base / "legacy"
        (run_dir / "fragments").mkdir(parents=True)
        self.write(run_dir / "run.json", {"schema": "five-whys/3", "inputs": ["p"], "plugin_version": "0.2.0",
                                          "shape": {"breadth": 5, "depth": 5, "split": 2}})
        proc = run("plan", run_dir, ok=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("created by an older version (0.2.0)", proc.stderr)


class CheckTests(RunCase):
    def check(self, data, breadth, depth, name="fragment.json"):
        path = self.base / name
        self.write(path, data)
        return run("check", path, "--breadth", breadth, "--depth", depth, ok=False)

    def test_valid_fragment_passes(self):
        proc = self.check(fragment(5, 3, "x"), 5, 3)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_miscount_reports_its_position(self):
        data = fragment(5, 2, "x")
        data["answers"][1]["answers"].pop()
        proc = self.check(data, 5, 2)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("item 2's answers: expected 5 answers, got 4", proc.stdout)

    def test_leaf_with_answers_and_bad_assumptions_are_rejected(self):
        data = fragment(2, 1, "x")
        data["answers"][0]["answers"] = [{"answer": "extra"}]
        data["assumptions"] = [3]
        out = self.check(data, 2, 1).stdout
        self.assertIn("item 1: deepest answers must not have answers", out)
        self.assertIn("assumptions: must be a list of strings", out)

    def test_warnings_do_not_block(self):
        data = fragment(3, 2, "x")
        data["answers"][0]["answers"][1]["answer"] = data["answers"][0]["answers"][0]["answer"]
        proc = self.check(data, 3, 2)
        self.assertEqual((proc.returncode, proc.stdout.splitlines()[0]), (0, "OK"))
        self.assertIn("warning: items 1.1, 1.2 repeat the same text", proc.stdout)

    def test_root_group_counts_its_trees_and_labels_errors_by_tree_number(self):
        short = group(3, 1, 3, 4)
        short["trees"].pop()
        self.assertIn("trees: expected 2 trees, got 1", self.check(short, 3, 1, "roots-3-4.json").stdout)
        miscounted = group(3, 1, 3, 4)
        miscounted["trees"][1]["answers"].pop()
        self.assertIn("tree 4: top-level answers: expected 3 answers, got 2",
                      self.check(miscounted, 3, 1, "roots-3-4.json").stdout)
        self.assertEqual(self.check(group(3, 1, 3, 4), 3, 1, "roots-3-4.json").stdout.strip(), "OK")

    def test_branch_check_compares_against_its_trees_root_answers(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = self.fill_roots(run_dir, 3, 1)["1.why"]
        data = fragment(3, 2, "b1.why.2")
        data["answers"][0]["answer"] = root[1]["answer"]  # restates its own ancestor, node 1.why.2
        data["answers"][1]["answers"][0]["answer"] = root[2]["answer"]  # copies another root answer
        path = run_dir / "fragments" / "branch-1.why.2.json"
        self.write(path, data)
        out = run("check", path, "--breadth", 3, "--depth", 2).stdout
        self.assertIn("warning: item 1 restates item 1.why.2 (written by the root)", out)
        self.assertIn("warning: items 1.why.3 (written by the root), 2.1 repeat the same text", out)


class AssembleTests(RunCase):
    def smoke_run(self):
        run_dir, _ = self.init("--preset", "smoke")
        return run_dir, self.fill_roots(run_dir, 3, 1)["1.why"]

    def test_full_5x5_assembles_every_answer_once(self):
        run_dir, _ = self.init()
        self.fill_roots(run_dir, 5, 2)
        self.fill_branches(run_dir, 5, 3)
        self.assertEqual(self.plan(run_dir)["state"], "ready")
        summary = json.loads(run("assemble", run_dir).stdout)
        self.assertTrue(summary["complete"])
        tree = self.read(run_dir / "five-ws.json")
        self.assertEqual((tree["schema"], tree["input_count"], tree["questions"], tree["inputs"][0]["input"]),
                         ("five-ws/1", 1, ["why"], PROBLEM))
        ids = answer_ids(tree["inputs"][0]["trees"][0]["answers"])
        self.assertEqual((len(ids), len(set(ids)), ids[0]), (3905, 3905, "1.why.1"))
        self.assertEqual([level["answers"] for level in tree["levels"]], [5, 25, 125, 625, 3125])
        self.assertEqual(self.read(run_dir / "run.json")["output"]["bytes"], summary["bytes"])

        index = (run_dir / "index.md").read_text()
        self.assertIn("Settings: 5 wide x 5 deep, root writes 2 level(s), models inherit, waves of 5", index)
        self.assertIn(f"- 1 [input] {PROBLEM}", index)
        self.assertIn("  - 1.why [why]", index)
        windows = [tuple(map(int, w)) for w in re.findall(r"- offset (\d+), limit (\d+)", index)]
        lines = (run_dir / "five-ws.json").read_text().splitlines()
        self.assertEqual(summary["read_windows"], len(windows))
        expected_start = 1
        for offset, limit in windows:
            self.assertEqual(offset, expected_start)
            chunk = lines[offset - 1: offset - 1 + limit]
            self.assertLessEqual(sum(len(line.encode()) + 1 for line in chunk), READ_WINDOW_BYTES)
            expected_start += limit
        self.assertEqual(expected_start - 1, len(lines))

    def test_several_inputs_and_questions_assemble_into_one_file(self):
        run_dir, out = self.init("--ask", "why,how", "--depth", "2", problem="Deploys fail\nLogin is slow\nBackups skip runs")
        self.assertEqual((out["trees"], out["estimate"]["agents"]), (6, 2))
        self.fill_roots(run_dir, 5, 2)
        summary = json.loads(run("assemble", run_dir).stdout)
        self.assertEqual((summary["inputs"], summary["questions"], summary["present_answers"], summary["total_answers"]),
                         (3, ["why", "how"], 180, 180))
        tree = self.read(run_dir / "five-ws.json")
        second = tree["inputs"][1]
        self.assertEqual((second["input"], [t["id"] for t in second["trees"]]), ("Login is slow", ["2.why", "2.how"]))
        self.assertEqual(answer_ids(second["trees"][1]["answers"])[:2], ["2.how.1", "2.how.1.1"])
        index = (run_dir / "index.md").read_text()
        self.assertIn("3 inputs × 2 questions (why, how), each asked 2 level(s) deep with 5 answers per question: "
                      "180 answers.", index)
        self.assertIn("  - 3.how [how]", index)

    def test_duration_ends_at_the_newest_fragment(self):
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        meta = self.read(run_dir / "run.json")
        created = dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.timezone.utc)
        meta["created"] = created.isoformat()
        self.write(run_dir / "run.json", meta)
        for path in (run_dir / "fragments").glob("*.json"):
            os.utime(path, (created.timestamp() + 120, created.timestamp() + 120))
        self.assertEqual(json.loads(run("assemble", run_dir).stdout)["duration_seconds"], 120)
        self.assertEqual(json.loads(run("assemble", run_dir).stdout)["duration_seconds"], 120)

    def test_hygiene_flags_duplicates_and_restatements_without_removing_them(self):
        run_dir, root = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        fragments = run_dir / "fragments"
        b1, b2, b3 = (self.read(fragments / f"branch-1.why.{i}.json") for i in (1, 2, 3))
        b1["answers"][0]["answer"] = root[0]["answer"]
        b3["answers"][1]["answer"] = b2["answers"][1]["answer"]
        self.write(fragments / "branch-1.why.1.json", b1)
        self.write(fragments / "branch-1.why.3.json", b3)
        run("assemble", run_dir)
        flags = self.read(run_dir / "hygiene.json")
        self.assertIn(["1.why.2.2", "1.why.3.2"], [g["ids"] for g in flags["exact_duplicates"]])
        self.assertIn(("1.why.1.1", "1.why.1", 1.0), [(f["id"], f["of"], f["similarity"]) for f in flags["restates_parent"]])
        self.assertEqual(self.read(run_dir / "five-ws.json")["present_answers"], 39)

    def test_hygiene_catches_close_rewording_across_branches(self):
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        fragments = run_dir / "fragments"
        b1, b2 = self.read(fragments / "branch-1.why.1.json"), self.read(fragments / "branch-1.why.2.json")
        b1["answers"][0]["answer"] = "The validator only checks JSON shape, never answer content."
        b2["answers"][2]["answer"] = "Validator checks only the JSON shape and never the content of answers."
        self.write(fragments / "branch-1.why.1.json", b1)
        self.write(fragments / "branch-1.why.2.json", b2)
        run("assemble", run_dir)
        near = self.read(run_dir / "hygiene.json")["near_duplicates"]
        self.assertIn(("1.why.1.1", "1.why.2.3"), {(p["a"], p["b"]) for p in near})
        self.assertEqual(len(near[0]["texts"]), 2)

    def test_word_variants_across_branches_and_questions_are_listed_as_leads(self):
        first = "Release estimates were never revisited after the migration changed scope."
        second = "Nobody revisited the release estimate when migration scope changed again later."
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2)
        fragments = run_dir / "fragments"
        b1, b2 = self.read(fragments / "branch-1.why.1.json"), self.read(fragments / "branch-1.why.2.json")
        b1["answers"][0]["answer"], b2["answers"][2]["answer"] = first, second
        self.write(fragments / "branch-1.why.1.json", b1)
        self.write(fragments / "branch-1.why.2.json", b2)
        run("assemble", run_dir)
        flags = self.read(run_dir / "hygiene.json")
        lead = next(p for p in flags["cross_branch"] if (p["a"], p["b"]) == ("1.why.1.1", "1.why.2.3"))
        self.assertEqual((lead["across_inputs"], lead["across_questions"]), (False, False))
        self.assertEqual(flags["counts"]["cross_branch"], len(flags["cross_branch"]))

        both, _ = self.init("--ask", "why,how", "--breadth", "3", "--depth", "1")
        data = group(3, 1, 1, 2)
        data["trees"][0]["answers"][0]["answer"], data["trees"][1]["answers"][0]["answer"] = first, second
        self.write(both / "fragments" / "roots-1-2.json", data)
        run("assemble", both)
        leads = self.read(both / "hygiene.json")["cross_branch"]
        self.assertIn(("1.why.1", "1.how.1", False, True),
                      [(p["a"], p["b"], p["across_inputs"], p["across_questions"]) for p in leads])

    def test_cited_files_and_commits_are_checked_against_the_project(self):
        project = self.base / "project"
        (project / "docs").mkdir(parents=True)
        (project / "docs" / "real.md").write_text("x")
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        subprocess.run(["git", "-C", str(project), "add", "docs/real.md"], check=True)
        subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"],
                       check=True)
        sha = subprocess.run(["git", "-C", str(project), "rev-parse", "--short=7", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        run_dir, _ = self.init("--breadth", "3", "--depth", "1")
        data = group(3, 1, 1, 1)
        answers = data["trees"][0]["answers"]
        answers[0]["answer"] = f"Commit {sha} changed docs/real.md and real.md without a review."
        answers[1]["answer"] = "The runbook in docs/missing.md was deleted after commit abc1234 landed."
        answers[2]["answer"] = "Nobody reviews the runbook before a release goes out."
        self.write(run_dir / "fragments" / "roots-1.json", data)
        summary = json.loads(run("assemble", run_dir, "--root", project).stdout)
        refs = self.read(run_dir / "hygiene.json")["references"]
        self.assertEqual(sorted((r["id"], r["reference"]) for r in refs["not_found"]),
                         [("1.why.2", "abc1234"), ("1.why.2", "docs/missing.md")])
        self.assertEqual((refs["checked"], refs["unchecked"]), (5, []))
        self.assertEqual(refs["concrete_by_tree"]["1.why"], {"answers": 3, "concrete": 2})
        self.assertEqual(summary["hygiene_counts"]["unverified_references"], 2)

        outside = self.base / "not-a-repo"
        outside.mkdir()
        run("assemble", run_dir, "--root", outside)
        refs = self.read(run_dir / "hygiene.json")["references"]
        self.assertEqual({r["reference"] for r in refs["unchecked"]}, {sha, "abc1234"})

    def test_partial_assembly_marks_missing_branch(self):
        run_dir, _ = self.smoke_run()
        self.fill_branches(run_dir, 3, 2, skip=("1.why.2",))
        self.assertNotEqual(run("assemble", run_dir, ok=False).returncode, 0)
        summary = json.loads(run("assemble", run_dir, "--partial").stdout)
        self.assertEqual((summary["complete"], summary["missing_branches"]), (False, ["1.why.2"]))
        tree = self.read(run_dir / "five-ws.json")
        self.assertTrue(tree["inputs"][0]["trees"][0]["answers"][1]["missing"])
        self.assertEqual(tree["present_answers"], 3 + 2 * 12)
        self.assertIn("(branch missing)", (run_dir / "index.md").read_text())

    def test_partial_assembly_marks_a_tree_whose_root_group_is_missing(self):
        run_dir, out = self.init("--depth", "3", problem="Deploys fail\nLogin is slow")
        self.assertEqual(out["estimate"]["agents"], 2)  # 155 answers each: one agent per tree
        self.write(run_dir / "fragments" / "roots-1.json", group(5, 3, 1, 1))
        self.assertNotEqual(run("assemble", run_dir, ok=False).returncode, 0)
        summary = json.loads(run("assemble", run_dir, "--partial").stdout)
        self.assertEqual((summary["missing_branches"], summary["present_answers"], summary["total_answers"]),
                         (["roots-2"], 155, 310))
        tree = self.read(run_dir / "five-ws.json")
        self.assertTrue(tree["inputs"][1]["trees"][0]["missing"])
        self.assertIn("  - 2.why [why] (missing)", (run_dir / "index.md").read_text())

    def test_assumptions_and_version_are_carried_into_output(self):
        run_dir, _ = self.smoke_run()
        data = self.read(run_dir / "fragments" / "roots-1.json")
        data["assumptions"] = ["Deploys run through a single CI pipeline."]
        self.write(run_dir / "fragments" / "roots-1.json", data)
        self.fill_branches(run_dir, 3, 2)
        run("assemble", run_dir)
        tree = self.read(run_dir / "five-ws.json")
        self.assertEqual(tree["assumptions"], {"roots-1": ["Deploys run through a single CI pipeline."]})
        self.assertEqual(tree["plugin_version"], self.read(ROOT / ".claude-plugin" / "plugin.json")["version"])

    def test_breadth_ten_uses_multi_digit_ids(self):
        run_dir, out = self.init("--breadth", "10", "--depth", "2", "--split", "1")
        self.assertEqual(out["estimate"]["agents"], 11)
        self.fill_roots(run_dir, 10, 1)
        self.fill_branches(run_dir, 10, 1)
        run("assemble", run_dir)
        shown = run("show", run_dir, "--id", "1.why.10.10").stdout.splitlines()
        self.assertEqual(shown[:2], [f"^ 1  [input] {PROBLEM}", "^ 1.why  [why]"])
        self.assertTrue(shown[2].startswith("^ 1.why.10  "))
        self.assertTrue(shown[3].startswith("1.why.10.10  "))


class StatusAndShowTests(RunCase):
    def test_status_counts_fragments_and_versions(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_roots(run_dir, 3, 1)
        status = self.status(run_dir)
        self.assertEqual((status["done"], status["total"], status["missing"]), (1, 4, ["1.why.1", "1.why.2", "1.why.3"]))
        self.assertEqual(status["plugin_version"], status["installed_plugin_version"])

    def test_checks_inside_a_run_are_logged_per_fragment(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = run_dir / "fragments" / "roots-1.json"
        self.write(root, {"trees": []})
        run("check", root, "--breadth", 3, "--depth", 1, ok=False)
        self.fill_roots(run_dir, 3, 1)
        run("check", root, "--breadth", 3, "--depth", 1)
        status = self.status(run_dir)
        self.assertEqual(status["checks"], {"roots-1.json": {"checks": 2, "failed": 1, "kinds": {"tree_count": 1}}})

    def test_warnings_are_logged_by_kind(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_roots(run_dir, 3, 1)
        path = run_dir / "fragments" / "roots-1.json"
        data = self.read(path)
        data["trees"][0]["answers"][1]["answer"] = data["trees"][0]["answers"][0]["answer"]
        self.write(path, data)
        run("check", path, "--breadth", 3, "--depth", 1)
        entry = json.loads((run_dir / "check-log.jsonl").read_text().splitlines()[-1])
        self.assertEqual((entry["ok"], entry["warning_kinds"]["exact"]), (True, 1))
        self.assertEqual(entry["warnings"], sum(entry["warning_kinds"].values()))

    def test_error_kinds_name_the_broken_rule(self):
        spec = importlib.util.spec_from_file_location("fivews", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = {"roots-1-2.json: trees: expected 2 trees, got 1": "tree_count",
                 "f.json: item 2's answers: expected 5 answers, got 4": "count",
                 "f.json: item 1.2: answer missing or empty": "missing_answer",
                 "f.json: item 3: deepest answers must not have answers": "leaf_answers",
                 "f.json: invalid JSON (Expecting value)": "json",
                 'f.json: top level must be {"answers": [...]}': "structure",
                 "f.json: assumptions: must be a list of strings": "assumptions",
                 "f.json: missing": "missing_file"}
        self.assertEqual({m: module.error_kind(m) for m in cases}, cases)

    def test_show_prints_ancestors_and_limits_levels(self):
        run_dir, _ = self.init("--preset", "smoke")
        root = self.fill_roots(run_dir, 3, 1)["1.why"]
        self.fill_branches(run_dir, 3, 2)
        run("assemble", run_dir)
        lines = run("show", run_dir, "--id", "1.why.2.1", "--levels", "1").stdout.splitlines()
        self.assertEqual(lines[:3], [f"^ 1  [input] {PROBLEM}", "^ 1.why  [why]", f"^ 1.why.2  {root[1]['answer']}"])
        self.assertEqual(len(lines), 4)
        self.assertEqual(run("show", run_dir, "--levels", "1").stdout.splitlines(), [f"1  [input] {PROBLEM}"])
        self.assertEqual(run("show", run_dir, "--levels", "2").stdout.splitlines(),
                         [f"1  [input] {PROBLEM}", "  1.why  [why]"])
        self.assertEqual(len(run("show", run_dir, "--levels", "3").stdout.splitlines()), 5)

    def test_show_reads_trees_assembled_by_earlier_versions(self):
        old = self.base / "five-whys.json"
        self.write(old, {"schema": "five-whys/2", "whys": [{"id": "1", "depth": 1, "reason": "Old reason", "whys": []}]})
        self.assertEqual(run("show", old).stdout.splitlines(), ["1  Old reason"])
        listed = self.base / "listed.json"
        self.write(listed, {"schema": "five-whys/3", "inputs": [
            {"id": "1", "depth": 0, "input": "P", "whys": [{"id": "1.1", "depth": 1, "reason": "R"}]}]})
        self.assertEqual(run("show", listed).stdout.splitlines(), ["1  [input] P", "  1.1  R"])

    def test_show_sample_is_repeatable_and_only_samples_answers(self):
        run_dir, _ = self.init("--preset", "smoke")
        self.fill_roots(run_dir, 3, 1)
        self.fill_branches(run_dir, 3, 2)
        run("assemble", run_dir)
        first = run("show", run_dir, "--sample", "40", "--seed", "7").stdout
        self.assertEqual(first, run("show", run_dir, "--sample", "40", "--seed", "7").stdout)
        samples = first.strip().split("\n\n")
        self.assertEqual(len(samples), 39)
        self.assertTrue(all("[" not in s.splitlines()[-1] for s in samples))


class SkillReplayTests(RunCase):
    """Walk SKILL.md's steps with fake agents standing in for the expander.

    The fragments are synthetic filler from fragment(), not recorded agent output,
    so these tests cover orchestration, not what real agents write.
    """

    def dispatch_until_done(self, run_dir, broken=()):
        waves = []
        for _ in range(20):  # Step 4: plan --record, dispatch every task, report status, repeat
            plan = self.plan(run_dir, "--record")
            if plan["state"] in ("ready", "stuck"):
                return plan, waves
            waves.append([task["id"] for task in plan["tasks"]])
            for task in plan["tasks"]:
                self.assertIn(task["prompt_file"], task["prompt"])
                self.assertEqual(plan["agent"], "five-ws:expander")
                proc = fake_agent(task, task["id"], broken=task["id"] in broken)
                self.assertEqual(proc.returncode != 0, task["id"] in broken, proc.stdout)
            self.status(run_dir)
        self.fail("the dispatch loop did not terminate")

    def start(self, invocation):
        parsed = self.parse(invocation)  # Step 1
        self.assertEqual(parsed["errors"], [])
        init = run("init", "--base", self.base, *shlex.split(parsed["init_flags"]),
                   stdin="\n".join(parsed["inputs"]))  # Step 2
        return parsed, json.loads(init.stdout)

    def test_smoke_invocation_runs_to_an_assembled_tree(self):
        parsed, out = self.start(f"--smoke --yes {PROBLEM}")
        self.assertEqual((parsed["yes"], parsed["resume"]), (True, None))
        self.assertFalse(out["confirm"])  # Step 3 is skipped
        run_dir = Path(out["run"])
        plan, waves = self.dispatch_until_done(run_dir)
        self.assertEqual((plan["state"], waves), ("ready", [["roots-1"], ["1.why.1", "1.why.2", "1.why.3"]]))
        status = self.status(run_dir)
        self.assertEqual(status["done"], 4)
        self.assertEqual([w["ids"] for w in status["waves"]], [["roots-1"], ["1.why.1", "1.why.2", "1.why.3"]])
        for wave in status["waves"]:
            self.assertLessEqual(dt.datetime.fromisoformat(wave["at"]), dt.datetime.fromisoformat(wave["finished"]))
            self.assertIsInstance(wave["seconds"], int)
            self.assertGreaterEqual(wave["seconds"], 0)
        summary = json.loads(run("assemble", run_dir).stdout)  # Step 5
        self.assertEqual((summary["complete"], summary["present_answers"], summary["checks"]),
                         (True, 39, {"runs": 4, "failed": 0}))
        tree = self.read(run_dir / "five-ws.json")
        self.assertEqual([w["fragments"] for w in tree["waves"]], [1, 3])
        self.assertIn("waves of 5 (2 dispatched, ", (run_dir / "index.md").read_text())

    def test_a_list_of_inputs_runs_each_to_the_chosen_depth(self):
        parsed, out = self.start("--depth 4 --yes\n- Deploys fail on Fridays\n- Login is slow after 9am")
        self.assertEqual(parsed["inputs"], ["Deploys fail on Fridays", "Login is slow after 9am"])
        self.assertEqual((out["inputs"], out["estimate"]["agents"], out["confirm"]), (2, 11, True))
        run_dir = Path(out["run"])
        plan, waves = self.dispatch_until_done(run_dir)
        self.assertEqual((plan["state"], waves[0]), ("ready", ["roots-1-2"]))
        self.assertEqual(sorted(i for wave in waves[1:] for i in wave),
                         sorted(f"{k}.why.{i}" for k in (1, 2) for i in range(1, 6)))
        summary = json.loads(run("assemble", run_dir).stdout)
        self.assertEqual((summary["complete"], summary["inputs"], summary["present_answers"]), (True, 2, 1560))

    def test_questions_chosen_in_words_run_as_separate_trees(self):
        parsed, out = self.start("--depth 1 --yes ask how and when for: Deploys fail on Fridays")
        self.assertEqual((parsed["questions"], parsed["questions_from_words"], parsed["inputs"]),
                         (["how", "when"], True, ["Deploys fail on Fridays"]))
        self.assertEqual((out["trees"], out["estimate"]["agents"]), (2, 1))
        run_dir = Path(out["run"])
        plan, waves = self.dispatch_until_done(run_dir)
        self.assertEqual((plan["state"], waves), ("ready", [["roots-1-2"]]))
        summary = json.loads(run("assemble", run_dir).stdout)
        self.assertEqual((summary["questions"], summary["present_answers"]), (["how", "when"], 10))
        trees = self.read(run_dir / "five-ws.json")["inputs"][0]["trees"]
        self.assertEqual([(t["id"], len(t["answers"])) for t in trees], [("1.how", 5), ("1.when", 5)])

    def test_failing_agent_ends_stuck_and_partial_assembly_salvages_the_rest(self):
        run_dir, _ = self.init("--preset", "smoke")
        plan, waves = self.dispatch_until_done(run_dir, broken=("1.why.2",))
        self.assertEqual((plan["state"], [s["id"] for s in plan["stuck"]]), ("stuck", ["1.why.2"]))
        self.assertEqual(waves, [["roots-1"], ["1.why.1", "1.why.2", "1.why.3"], ["1.why.2"], ["1.why.2"]])
        timing = self.status(run_dir)["waves"]
        self.assertEqual([w["ids"] for w in timing], waves)
        self.assertEqual([w["seconds"] is None for w in timing], [False, True, True, True])
        self.assertNotEqual(run("assemble", run_dir, ok=False).returncode, 0)
        summary = json.loads(run("assemble", run_dir, "--partial").stdout)
        self.assertEqual((summary["missing_branches"], summary["present_answers"]), (["1.why.2"], 27))

    def test_resume_continues_with_a_new_wave_size(self):
        run_dir, _ = self.init()
        self.fill_roots(run_dir, 5, 2)
        parsed = self.parse(f"--resume {run_dir} --max-parallel 2")
        plan = self.plan(parsed["resume"], "--record", *shlex.split(parsed["plan_flags"]))
        self.assertEqual((len(plan["tasks"]), len(plan["waiting"])), (2, 23))


if __name__ == "__main__":
    unittest.main()
