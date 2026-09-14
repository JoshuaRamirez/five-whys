"""Keep the self-improvement rubric well formed and every rating file consistent with it."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs" / "self-improvement"
RUBRIC = (FOLDER / "rubric.md").read_text()


def criteria(text: str) -> list[tuple[int, str, int]]:
    table = re.search(r"(?ms)^## Criteria\n.*?^\| # .*?\n\|[-| ]+\|\n(.*?)\n\n", text).group(1)
    return [(int(n), name.strip(), int(weight))
            for n, name, weight in re.findall(r"^\| (\d+) \| ([^|]+) \| (\d+) \|", table, re.M)]


def versions(text: str) -> set[str]:
    changes = text.split("## Changes", 1)[1]
    return set(re.findall(r"(?m)^- (\d+) \(\d{4}-\d{2}-\d{2}\):", changes))


def check_rating(text: str, rubric: str = RUBRIC) -> list[str]:
    """Return problems with one rating file; an empty list means it is consistent."""
    if text.lstrip().startswith("Pre-rubric:"):
        return []
    version = re.search(r"(?m)^Rubric version: (\d+)$", text)
    if not version:
        return ["no 'Rubric version:' line and not marked Pre-rubric"]
    problems = [] if version.group(1) in versions(rubric) else [f"rubric version {version.group(1)} does not exist"]
    for field in ("Grader", "Date"):
        if not re.search(rf"(?m)^{field}: \S", text):
            problems.append(f"missing {field}")
    rows = re.findall(r"(?m)^\| (\d+) \| ([^|]+) \| (\d+) \|", text)
    expected = criteria(rubric)
    if [(int(n), name.strip()) for n, name, _ in rows] != [(n, name) for n, name, _ in expected]:
        return problems + ["criteria rows do not match the rubric in order"]
    scores = [int(score) for _, _, score in rows]
    if any(not 0 <= s <= 10 for s in scores):
        problems.append("scores must be 0-10")
    total = re.search(r"(?m)^Weighted total: (\d+(?:\.\d)?)$", text)
    computed = round(sum(s * w for s, (_, _, w) in zip(scores, expected)) / 100, 1)
    if not total or float(total.group(1)) != computed:
        problems.append(f"weighted total should be {computed}")
    return problems


class RubricTests(unittest.TestCase):
    def test_weights_sum_to_100_and_numbering_is_sequential(self):
        rows = criteria(RUBRIC)
        self.assertEqual([n for n, _, _ in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(sum(w for _, _, w in rows), 100)

    def test_every_criterion_has_four_anchors(self):
        for n, name, _ in criteria(RUBRIC):
            section = re.search(rf"(?ms)^### {n}\. {re.escape(name)}\n(.*?)(?=^### |^## )", RUBRIC)
            self.assertIsNotNone(section, name)
            self.assertEqual(re.findall(r"(?m)^- \*\*(\d+):\*\*", section.group(1)), ["4", "6", "8", "10"], name)

    def test_current_version_is_in_the_change_list(self):
        self.assertIn(re.search(r"(?m)^Version: (\d+)$", RUBRIC).group(1), versions(RUBRIC))

    def test_rating_files_match_the_rubric(self):
        for path in sorted(FOLDER.glob("round-*/rating*.md")):
            self.assertEqual(check_rating(path.read_text()), [], path.relative_to(ROOT))

    def test_rating_check_catches_a_wrong_total_and_accepts_a_right_one(self):
        rows = criteria(RUBRIC)
        body = "\n".join(f"| {n} | {name} | 7 | evidence |" for n, name, _ in rows)
        rating = f"# Round 9 rating\n\nRubric version: 1\nGrader: test\nDate: 2026-09-13\n\n{body}\n\n"
        self.assertEqual(check_rating(rating + "Weighted total: 7.0\n"), [])
        self.assertIn("weighted total should be 7.0", check_rating(rating + "Weighted total: 7.4\n"))
        self.assertTrue(check_rating(rating.replace("Rubric version: 1", "Rubric version: 99") + "Weighted total: 7.0\n"))


if __name__ == "__main__":
    unittest.main()
