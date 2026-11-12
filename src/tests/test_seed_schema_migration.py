import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SeedSchemaMigrationTests(unittest.TestCase):
    def test_seed_design_and_evidence_are_separated(self):
        design = (ROOT / "AAA_core_data/种子.md").read_text(encoding="utf-8")
        evidence = (ROOT / "AAA_core_data/关键证据.md").read_text(encoding="utf-8")
        design_headings = re.findall(r"(?m)^# 种子(\d+)\s*$", design)
        evidence_headings = re.findall(r"(?m)^# 种子(\d+)\s*$", evidence)
        self.assertEqual(len(design_headings), 64)
        self.assertEqual(design_headings, evidence_headings)
        self.assertNotIn("| 关键事实 |", design)
        self.assertNotIn("| 标准指令 |", design)
        for block in re.split(r"(?m)(?=^# 种子\d+\s*$)", evidence)[1:]:
            self.assertTrue(re.findall(r"(?m)^- \S", block), block.splitlines()[0])
        self.assertNotRegex(evidence, r"（\d+\s*分）")

    def test_active_cases_have_one_test_variant(self):
        cases = [p for p in (ROOT / "prompt/cases").iterdir() if p.is_dir() and p.name.startswith("种子")]
        self.assertEqual(len(cases), 54)
        for case in cases:
            config = json.loads((case / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(len(config["variants"]), 1, case.name)
            self.assertTrue(next(iter(config["variants"])).endswith("_test"), case.name)
        self.assertEqual(list((ROOT / "prompt/cases").rglob("*_standard.md")), [])


if __name__ == "__main__":
    unittest.main()