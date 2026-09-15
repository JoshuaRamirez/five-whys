"""Hygiene scoring against labeled pairs from a real tree (tests/fixtures/pairs.json)."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hygiene", ROOT / "scripts" / "hygiene.py")
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)

PAIRS = json.loads((ROOT / "tests" / "fixtures" / "pairs.json").read_text())


def unstemmed(text: str) -> set:
    """Tokens as v0.2.0 computed them, for the baseline comparison."""
    return {w for w in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", text.lower()) if w not in hygiene.STOPWORDS}


class LabeledPairTests(unittest.TestCase):
    def flagged(self, pairs, threshold):
        return [p for p in pairs if hygiene.similarity(*p["texts"]) >= threshold]

    def test_convergent_pairs_detected_at_the_lead_threshold(self):
        # Measured when the fixture was made: 7 of 16 convergent pairs reach the lead
        # threshold. The other 9 restate a cause in different words and stay misses.
        found = self.flagged(PAIRS["convergent"], hygiene.CROSS_BRANCH_SIMILARITY)
        self.assertGreaterEqual(len(found), 7, [(p["a"], p["b"]) for p in found])

    def test_distinct_pairs_rarely_become_leads(self):
        # Measured: 2 of 8 distinct pairs share enough wording to be listed as leads.
        found = self.flagged(PAIRS["distinct"], hygiene.CROSS_BRANCH_SIMILARITY)
        self.assertLessEqual(len(found), 2, [(p["a"], p["b"]) for p in found])

    def test_v020_scoring_caught_none_of_the_convergent_pairs(self):
        baseline = [p for p in PAIRS["convergent"]
                    if hygiene.jaccard(unstemmed(p["texts"][0]), unstemmed(p["texts"][1])) >= hygiene.SIMILARITY]
        self.assertEqual(baseline, [])

    def test_stemming_matches_word_variants(self):
        self.assertEqual({hygiene.stem(w) for w in ("estimate", "estimates", "estimated", "estimating")}, {"estimat"})
        self.assertEqual(hygiene.stem("processes"), hygiene.stem("process"))
        self.assertEqual(hygiene.stem("status"), "status")
        self.assertEqual(hygiene.stem("five-whys"), "five-whys")


if __name__ == "__main__":
    unittest.main()
