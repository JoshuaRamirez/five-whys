"""Keep the README, skills, agent, manifest, changelog and release text consistent with the script."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fivews", ROOT / "scripts" / "fivews.py")
fivews = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fivews)

README = (ROOT / "README.md").read_text()
SKILL = (ROOT / "skills" / "five-ws" / "SKILL.md").read_text()
SHORTCUT = (ROOT / "skills" / "five-whys" / "SKILL.md").read_text()
AGENT = (ROOT / "agents" / "expander.md").read_text()
CHANGELOG = (ROOT / "CHANGELOG.md").read_text()
RELEASING = (ROOT / "RELEASING.md").read_text()
MANIFEST = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())


def flat(text: str) -> str:
    return " ".join(text.split())


class DocsConsistencyTests(unittest.TestCase):
    def test_headline_total_matches_default_shape(self):
        breadth, depth = fivews.PRESETS["full"]
        total = f"{fivews.answer_count(breadth, depth):,}"
        self.assertIn(total, README)
        self.assertIn(total, SKILL)

    def test_smoke_numbers_match_preset(self):
        breadth, depth = fivews.PRESETS["smoke"]
        answers = fivews.answer_count(breadth, depth)
        agents = fivews.agent_count(breadth, depth, fivews.SMOKE_SPLIT)
        self.assertIn(f"{answers} answers, {agents} agents", SKILL)
        self.assertIn(f"{answers} answers from {agents} agents", README)

    def test_option_count_is_pinned(self):
        # Adding or removing a /five-ws option is a deliberate change: update this
        # number, the README table, SKILL.md and CHANGELOG.md together.
        self.assertEqual(len(fivews.OPTIONS), 11)

    def test_every_option_is_documented_with_a_purpose(self):
        rows = re.findall(r"^\| `(--[a-z-]+)[^|]*\|[^|]+\|([^|]+)\|$", README, re.M)
        self.assertEqual([flag for flag, _ in rows], [o["flag"] for o in fivews.OPTIONS])
        self.assertTrue(all(purpose.strip() for _, purpose in rows))
        for option in fivews.OPTIONS:
            self.assertIn(f"`{option['flag']}", SKILL, option["flag"])

    def test_argument_hints_name_only_real_options(self):
        flags = {o["flag"] for o in fivews.OPTIONS}
        for text in (SKILL, SHORTCUT):
            hint = re.search(r"argument-hint: \"(.*)\"", text).group(1)
            for option in re.findall(r"--[a-z-]+", hint):
                self.assertIn(option, flags)

    def test_every_question_is_documented_everywhere(self):
        for question, wording in fivews.QUESTIONS.items():
            self.assertRegex(README, rf"(?m)^\| `{question}` \|", question)
            self.assertIn(wording["top"], README, question)
            self.assertIn(f"`{question}`", SKILL, question)
            self.assertIn(f"**{question}:**", AGENT, question)

    def test_model_levels_match_the_docs(self):
        for level, (roots, branches) in fivews.MODEL_LEVELS.items():
            self.assertIn(f"| {level} | {roots} | {branches} |", README)
            self.assertIn(f"| {level} | {roots} | {branches} |", SKILL)

    def test_names_agree_across_manifest_agent_and_script(self):
        agent_name = re.search(r"^name: (.*)$", AGENT, re.M).group(1)
        self.assertEqual(f"{MANIFEST['name']}:{agent_name}", fivews.AGENT)
        self.assertEqual(re.search(r"^name: (.*)$", SKILL, re.M).group(1), MANIFEST["name"])
        self.assertIn(f"`{fivews.OUTPUT}`", README)

    def test_five_whys_shortcut_defers_to_the_five_ws_skill(self):
        self.assertIn("skills/five-ws/SKILL.md", SHORTCUT)
        self.assertIn("--ask why", SHORTCUT)

    def test_confirmation_threshold_matches_skill(self):
        self.assertIn(f"more than {fivews.CONFIRM_AGENTS} agents", SKILL)

    def test_wave_size_and_platform_cap_match_docs(self):
        self.assertIn(f"({fivews.MAX_PARALLEL} by default)", SKILL)
        self.assertIn(f"waves of {fivews.MAX_PARALLEL}", README)
        self.assertIn(f"at most {fivews.PLATFORM_PARALLEL_CAP} subagents", README)

    def test_measured_cost_matches_the_constants(self):
        measured = fivews.MEASURED
        self.assertIn(f"v{measured['version']} full run", README)
        self.assertIn(f"{measured['date']} with {measured['model']}", flat(README))
        full = fivews.estimate(5, 5, 2)
        self.assertIn(f"about {full['agent_tokens_low'] / 1e6:.2f}M-{full['agent_tokens'] / 1e6:.2f}M agent tokens "
                      f"and {full['output_tokens'] // 1000}k output tokens", flat(README))
        self.assertIn("agent_tokens_low", SKILL)

    def test_changelog_has_an_entry_for_the_manifest_version(self):
        self.assertRegex(CHANGELOG, rf"(?m)^## {re.escape(MANIFEST['version'])} — \d{{4}}-\d{{2}}-\d{{2}}$")

    def test_analysis_boundary_zones_are_documented(self):
        for zone in ("Run output", "Reading aids", "Development measurement"):
            self.assertRegex(README, rf"(?m)^\| {zone}:", zone)
            self.assertIn(zone.lower(), flat(SKILL.lower()), zone)

    def test_changelog_evidence_records_a_status_per_gate(self):
        gates = re.findall(r"`([a-z-]+)`", re.search(r"Gate names: (.*?)\.\n\n", RELEASING, re.S).group(1))
        self.assertIn("eval", gates)
        entry = re.compile(rf"\[(passed|failed|blocked|waived)\] ({'|'.join(gates)}) @[0-9a-f]{{7,40}} "
                           r"\d{4}-\d{2}-\d{2}: \S")
        checked = 0
        for section in re.split(r"(?m)^## ", CHANGELOG)[1:]:
            title = section.splitlines()[0]
            evidence = re.search(r"(?ms)^### Evidence\n(.*?)(?=^### |\Z)", section)
            if not evidence:  # entries before 0.3.0 predate gate statuses
                continue
            bullets = re.split(r"(?m)^- ", evidence.group(1))[1:]
            self.assertTrue(bullets, title)
            for bullet in bullets:
                match = entry.match(bullet)
                self.assertIsNotNone(match, f"{title}: {bullet[:80]}")
                checked += 1
                if title != "Unreleased":  # a released version has no failed or unwaived blocked gate
                    self.assertNotEqual(match.group(1), "failed", bullet)
                    if match.group(1) == "blocked":
                        self.assertIn("[waived]", bullet)
        self.assertGreater(checked, 0)

    def test_agent_tools_cover_the_steps_it_is_given(self):
        tools = re.search(r"^tools: (.*)$", AGENT, re.M).group(1)
        self.assertEqual({t.strip() for t in tools.split(",")}, {"Write", "Edit", "Read", "Bash"})

    def test_agent_is_told_to_stay_off_the_network(self):
        self.assertIn("don't run network commands", flat(AGENT))
        self.assertIn("`gh`", flat(AGENT))

    def test_agent_skips_private_folders_and_knows_the_length_limit(self):
        self.assertIn("anything git ignores", flat(AGENT))
        self.assertIn(f"over {fivews.MAX_ANSWER_WORDS} words", flat(AGENT))
        self.assertIn(f"no answer over {fivews.MAX_ANSWER_WORDS} words", flat(README))

    def test_skill_invokes_the_script_only_through_its_absolute_path(self):
        for text in (SKILL, SHORTCUT):
            self.assertIsNone(re.search(r"python3\s+\"?(?!\$)[^\s\"]*scripts/fivews\.py", text))
        self.assertIn("`script` is the absolute path", flat(SKILL))

    def test_agent_instructions_hold_no_shape_counts(self):
        self.assertIsNone(re.search(r"exactly \d+|\b\d+ (?:items|reasons|answers)\b", AGENT))

    def test_read_windows_come_from_index_not_a_fixed_line_count(self):
        for text in (README, SKILL):
            self.assertNotRegex(text, r"\d+-line windows")

    def test_eval_cases_are_complete_and_granted_tools_are_allowed(self):
        cases = sorted((ROOT / "evals").glob("*/prompt.md"))
        self.assertGreaterEqual(len(cases), 4)
        granted = set(re.search(r"--allow-tools ((?:[A-Z]\w+ ?)+)", RELEASING).group(1).split())
        for prompt in cases:
            self.assertTrue(list((prompt.parent / "graders").glob("*.md")), prompt.parent.name)
            allowed = re.search(r"allowed_tools: \[(.*)\]", prompt.read_text()).group(1)
            self.assertLessEqual(granted, {t.strip() for t in allowed.split(",")}, prompt.parent.name)


if __name__ == "__main__":
    unittest.main()
