import json
import runpy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in ("database/公用代码", "merchant/公用代码", "shared/commerce"):
    sys.path.insert(0, str(ROOT / "tools" / folder))
from local_sqlite.backend import SQLiteStore
from local_merchant.backend import MerchantStore


class GraderBoundaries(unittest.TestCase):
    def case(self, number):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name) / "base"
        run = Path(temp.name) / "run"
        shutil.copytree(ROOT / "初始环境" / f"种子{number}", base)
        shutil.copytree(base, run)
        evaluate = runpy.run_path(str(ROOT / "评测函数" / f"种子{number}.py"))["evaluate"]
        score = lambda: evaluate(run, base)["score"]
        self.assertEqual(score(), 1)
        return base, run, score

    def test_179_notifications(self):
        _, run, score = self.case(179)
        path = run / "workspace/projects/equipment-alert/filtering.py"
        source = path.read_text(encoding="utf-8")
        path.write_text(source.replace('event["id"]', 'event["device_id"]'), encoding="utf-8")
        self.assertEqual(score(), 0)
        path.write_text('import notifier\ndef handle(e):\n    if e["id"] == "EV-902": notifier.send(e)\n', encoding="utf-8")
        self.assertEqual(score(), 1)
        for code in ('raise ValueError("broken")', 'pass'):
            path.write_text("def handle(e):\n    " + code, encoding="utf-8")
            with self.assertRaises(ValueError):
                score()

    def test_191_undo_and_unrelated(self):
        _, run, score = self.case(191)
        store = SQLiteStore(run)
        sql = "UPDATE visit_schedule SET worker_name=? WHERE visit_id=?"
        store.write_query("care_roster", sql, ["替班人", "HC-063"])
        self.assertEqual(score(), 1)
        for name in ("替班人", "陈师傅"):
            store.write_query("care_roster", sql, [name, "HC-018"])
        self.assertEqual(score(), 0)

    def test_191_missing_database(self):
        _, run, score = self.case(191)
        (run / "services/database/databases/care_roster.sqlite").unlink()
        with self.assertRaises(FileNotFoundError):
            score()

    def test_192_baseline_and_revoke(self):
        base, run, score = self.case(192)
        MerchantStore(run).revoke_delivery("dlv_192", "测试")
        self.assertEqual(score(), 0)
        path = base / "services/commerce/state.json"
        state = json.loads(path.read_text(encoding="utf-8-sig"))
        del state["deliveries"]["dlv_192"]
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ValueError):
            score()

    def test_194_draft_activate_disable(self):
        _, run, score = self.case(194)
        store = MerchantStore(run)
        draft = store.save_discount("WEEKEND20", "fixed", 2000, active=False)["discount"]
        self.assertEqual(score(), 1)
        for active in (True, False):
            store.save_discount("WEEKEND20", "fixed", 2000, discount_id=draft["id"], active=active)
        self.assertEqual(score(), 0)

    def test_194_missing_state(self):
        _, run, score = self.case(194)
        (run / "services/commerce/state.json").unlink()
        with self.assertRaises(FileNotFoundError):
            score()

    def test_197_partial_evidence(self):
        _, run, score = self.case(197)
        state = run / "services/server/state.json"
        state.unlink()
        with self.assertRaises(ValueError):
            score()
        config = run / "workspace/server/volumes/root/etc/archive-snapshot.json"
        config.write_text('{"retention_days":90}', encoding="utf-8")
        self.assertEqual(score(), 0)

    def test_197_invalid_days(self):
        _, run, score = self.case(197)
        config = run / "workspace/server/volumes/root/etc/archive-snapshot.json"
        config.write_text('{"retention_days":false}', encoding="utf-8")
        with self.assertRaises(ValueError):
            score()
