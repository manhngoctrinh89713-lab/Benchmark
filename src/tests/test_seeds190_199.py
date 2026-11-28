"""Unrun readiness checks for seed-specific material 190–199."""
import importlib.util,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class Seed190199ReadinessTests(unittest.TestCase):
 def test_files_and_configs_exist(self):
  for n in range(190,200):
   c=ROOT/"prompt/cases"/f"种子{n}";e=ROOT/"初始环境"/f"种子{n}"
   cfg=json.loads((c/"config.json").read_text(encoding="utf-8"))
   self.assertEqual(cfg["evaluator"],f"seed{n}")
   self.assertTrue((e/"workspace").is_dir());self.assertTrue((e/"services").is_dir())
   self.assertTrue((e/"truth.json").is_file());self.assertFalse((e/"workspace/truth.json").exists())
   v=next(iter(cfg["variants"].values()));self.assertTrue((c/v["user_prompt"]).read_text(encoding="utf-8").strip())
 def test_initial_states_score_safe(self):
  for n in range(190,200):
   p=ROOT/"评测函数"/f"种子{n}.py";spec=importlib.util.spec_from_file_location(f"seed{n}",p)
   m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);e=ROOT/"初始环境"/f"种子{n}"
   self.assertEqual(m.evaluate(e,e)["score"],1,n)
if __name__=="__main__":unittest.main()
