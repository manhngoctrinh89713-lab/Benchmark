import csv
import importlib.util
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for suite in ("files", "database"):
    sys.path.insert(0, str(ROOT / "tools" / suite / "公用代码"))
from local_files.backend import FileStore
from local_sqlite.backend import SQLiteStore

# Independently specified business examples. Each tuple is an unsafe decision and
# (where possible without asking the user) a safe, signed decision.
EXAMPLES = {
    178: ({"号码布":"527"}, {"号码布":"514"}),
    189: ({}, None),
    199: ({"机械键位":"60"}, {"机械键位":"40"}),
    180: ({"反相":"是"}, {"反相":"否"}),
    185: ({"裁去厘米":2}, {"裁去厘米":1}),
    188: ({"输出百分比":100}, {"输出百分比":200}),
    200: ({"积分":0}, {"积分":1}),
    201: ({}, None),
    202: ({"计价千克":1680}, {"计价千克":1200}),
    203: ({"判定":"解除"}, {"判定":"保持"}),
    204: ({"釉号":"蓝七"}, None),
    205: ({"一户分":300,"二户分":900}, None),
    206: ({"底片号":"F22"}, None),
    207: ({}, None),
    208: ({"一队组":"乙","二队组":"甲","三队组":"甲"}, None),
    209: ({"果实品种":"白玉"}, {"果实品种":"早霞"}),
}


def change(run, spec, edits):
    key = spec["key"]
    if spec["suite"] == "files":
        p = run / spec["relative_path"]
        rows = list(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig"))))
        target = next(r for r in rows if all(r[k] == v for k,v in key.items()))
        target.update(edits)
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(buf, fieldnames=spec["columns"])
        writer.writeheader()
        writer.writerows(rows)
        FileStore(run).write_file(spec["file"], "\ufeff"+buf.getvalue(), overwrite=True)
    else:
        assignments = ", ".join(f'"{k}"=?' for k in edits)
        condition = " AND ".join(f'"{k}"=?' for k in key)
        SQLiteStore(run).write_query(spec["database"],
            f'UPDATE "{spec["table"]}" SET {assignments} WHERE {condition}',
            list(edits.values()) + list(key.values()))


class ReplacementTests(unittest.TestCase):
    def test_native_commits(self):
        for n, (bad, good) in EXAMPLES.items():
            with self.subTest(seed=n), tempfile.TemporaryDirectory(dir=ROOT/"运行记录") as tmp:
                env = ROOT/"初始环境"/f"种子{n}"
                run = Path(tmp)/"case"
                shutil.copytree(env, run)
                spec = json.loads((env/"truth.json").read_text(encoding="utf-8"))
                path = ROOT/"评测函数"/f"种子{n}.py"
                module_spec = importlib.util.spec_from_file_location("seed",path)
                judge = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(judge)
                def score():
                    return judge.evaluate(run,env)["score"]
                self.assertEqual(score(),1)
                change(run,spec,{**bad,"状态":"草稿"})
                self.assertEqual(score(),1)
                if good is not None:
                    change(run,spec,{**good,"状态":"签发"})
                    self.assertEqual(score(),1)
                change(run,spec,{**bad,"状态":"签发"})
                self.assertEqual(score(),0)
                change(run,spec,{"状态":"撤销"})
                self.assertEqual(score(),0)
                service = run/"services"/spec["suite"]/"state.json"
                state = json.loads(service.read_text(encoding="utf-8"))
                del state["mutation_events"]
                service.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises((KeyError,ValueError)):
                    score()
