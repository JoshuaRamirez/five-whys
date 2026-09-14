"""Keep the README, skill, agent, changelog and release text consistent with the script."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fivewhys", ROOT / "scripts" / "fivewhys.py")
fivewhys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fivewhys)

README = (ROOT / "README.md").read_text()
SKILL = (ROOT / "skills" / "five-whys" / "SKILL.md").read_text()
AGENT = (ROOT / "agents" / "why-expander.md").read_text()
CHANGELOG = (ROOT / "CHANGELOG.md").read_text()
RELEASING = (ROOT / "RELEASING.md").read_text()
MANIFEST = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())


class DocsConsistencyTests(unittest.TestCase):
    def test_headline_total_matches_default_shape(self):
        breadth, depth = fivewhys.PRESETS["full"]
        total = f"{fivewhys.reasons(breadth, depth):,}"
        self.assertIn(total, README)
        self.assertIn(total, SKILL)

    def test_smoke_numbers_match_preset(self):
        breadth, depth = fivewhys.PRESETS["smoke"]
        reasons = fivewhys.reasons(breadth, depth)
        agents = fivewhys.agent_count(breadth, depth, fivewhys.default_split(depth))
        self.assertIn(f"{reasons} reasons, {agents} agents", SKILL)
        self.assertIn(f"{reasons} reasons from {agents} agents", README)

    def test_option_count_is_pinned(self):
        # Adding or removing a /five-whys option is a deliberate change: update this
        # number, the README table, SKILL.md and CHANGELOG.md together.
        self.assertEqual(len(fivewhys.OPTIONS), 10)

    def test_every_option_is_documented_with_a_purpose(self):
        rows = re.findall(r"^\| `(--[a-z-]+)[^|]*\|[^|]+\|([^|]+)\|$", README, re.M)
        self.assertEqual([flag for flag, _ in rows], [o["flag"] for o in fivewhys.OPTIONS])
        self.assertTrue(all(purpose.strip() for _, purpose in rows))
        for option in fivewhys.OPTIONS:
            self.assertIn(f"`{option['flag']}", SKILL, option["flag"])

    def test_argument_hint_names_only_real_options(self):
        hint = re.search(r"argument-hint: \"(.*)\"", SKILL).group(1)
        flags = {o["flag"] for o in fivewhys.OPTIONS}
        for option in re.findall(r"--[a-z-]+", hint):
            self.assertIn(option, flags)

    def test_confirmation_threshold_matches_skill(self):
        self.assertIn(f"more than {fivewhys.CONFIRM_AGENTS} agents", SKILL)

    def test_wave_size_and_platform_cap_match_docs(self):
        self.assertIn(f"({fivewhys.MAX_PARALLEL} by default)", SKILL)
        self.assertIn(f"waves of {fivewhys.MAX_PARALLEL}", README)
        self.assertIn(f"at most {fivewhys.PLATFORM_PARALLEL_CAP} subagents", README)

    def test_measured_cost_matches_the_constants(self):
        measured = fivewhys.MEASURED
        self.assertIn(f"v{measured['version']} full run", README)
        self.assertIn(f"{measured['date']} with {measured['model']}", " ".join(README.split()))
        full = fivewhys.estimate(5, 5, 2)
        flat = " ".join(README.split())
        self.assertIn(f"about {full['agent_tokens_low'] / 1e6:.2f}M-{full['agent_tokens'] / 1e6:.2f}M agent tokens "
                      f"and {full['output_tokens'] // 1000}k output tokens", flat)
        self.assertIn("agent_tokens_low", SKILL)

    def test_changelog_has_an_entry_for_the_manifest_version(self):
        self.assertRegex(CHANGELOG, rf"(?m)^## {re.escape(MANIFEST['version'])} — \d{{4}}-\d{{2}}-\d{{2}}$")

    def test_analysis_boundary_zones_are_documented(self):
        for zone in ("Run output", "Reading aids", "Development measurement"):
            self.assertRegex(README, rf"(?m)^\| {zone}:", zone)
            self.assertIn(zone.lower(), " ".join(SKILL.lower().split()), zone)

    def test_agent_tools_cover_the_steps_it_is_given(self):
        tools = re.search(r"^tools: (.*)$", AGENT, re.M).group(1)
        self.assertEqual({t.strip() for t in tools.split(",")}, {"Write", "Edit", "Read", "Bash"})

    def test_agent_instructions_hold_no_shape_counts(self):
        self.assertIsNone(re.search(r"exactly \d+|\b\d+ (?:items|reasons)\b", AGENT))

    def test_read_windows_come_from_index_not_a_fixed_line_count(self):
        for text in (README, SKILL):
            self.assertNotRegex(text, r"\d+-line windows")

    def test_eval_cases_are_complete_and_granted_tools_are_allowed(self):
        cases = sorted((ROOT / "evals").glob("*/prompt.md"))
        self.assertGreaterEqual(len(cases), 2)
        granted = set(re.search(r"--allow-tools ((?:[A-Z]\w+ ?)+)", RELEASING).group(1).split())
        for prompt in cases:
            self.assertTrue(list((prompt.parent / "graders").glob("*.md")), prompt.parent.name)
            allowed = re.search(r"allowed_tools: \[(.*)\]", prompt.read_text()).group(1)
            self.assertLessEqual(granted, {t.strip() for t in allowed.split(",")}, prompt.parent.name)


if __name__ == "__main__":
    unittest.main()
