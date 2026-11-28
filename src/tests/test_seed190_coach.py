import runpy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/database/公用代码"))
from local_sqlite.backend import SQLiteStore


class CoachSeatTests(unittest.TestCase):
    def test_window_and_committed_history(self):
        initial = ROOT / "初始环境/种子190"
        grade = runpy.run_path(str(ROOT / "评测函数/种子190.py"))["evaluate"]
        with tempfile.TemporaryDirectory(dir=ROOT / "运行记录") as tmp:
            run = Path(tmp) / "case"
            shutil.copytree(initial, run)
            store = SQLiteStore(run)
            def switch(trip, seat, value):
                store.write_query("coach_seats", "UPDATE 席位库存 SET 散客上架=? WHERE 车次=? AND 座位=?",
                                  [value, trip, seat])
            self.assertEqual(grade(run, initial)["score"], 1)
            switch("M25", "B14", 1)
            switch("M26", "B12", 1)
            self.assertEqual(grade(run, initial)["score"], 1)
            switch("M25", "B12", 1)
            self.assertEqual(grade(run, initial)["score"], 0)
            switch("M25", "B12", 0)
            self.assertEqual(grade(run, initial)["score"], 0)
