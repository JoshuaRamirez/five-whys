"""Keep the README, skill and agent text consistent with the script's defaults and options."""

from __future__ import annotations

import importlib.util
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
SCRIPT = (ROOT / "scripts" / "fivewhys.py").read_text()


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

    def test_skill_options_are_documented_everywhere(self):
        hint = re.search(r"argument-hint: \"(.*)\"", SKILL).group(1)
        for option in re.findall(r"--[a-z-]+", hint):
            self.assertIn(option, README, option)

    def test_init_flags_named_in_skill_exist_in_script(self):
        for flag in set(re.findall(r"`(--(?:preset|model|breadth|depth|context-file|root-model|branch-model))", SKILL)):
            self.assertIn(f'"{flag}"', SCRIPT, flag)

    def test_agent_instructions_hold_no_shape_counts(self):
        self.assertIsNone(re.search(r"exactly \d+|\b\d+ (?:items|reasons)\b", AGENT))

    def test_concurrency_cap_matches_docs(self):
        self.assertIn(f"{fivewhys.MAX_PARALLEL} by default", SKILL)
        self.assertIn(f"at most {fivewhys.MAX_PARALLEL} subagents", README)


if __name__ == "__main__":
    unittest.main()
