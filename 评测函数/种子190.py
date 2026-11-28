from contextlib import closing
from pathlib import Path
import runpy
import sqlite3


def evaluate(run_root, initial_root=None):
    directory = Path(__file__).resolve().parent
    initial = Path(initial_root) if initial_root else directory.parent / "初始环境" / "种子190"
    audit = runpy.run_path(str(directory / "nov21_register.py"))
    spec = audit["load"](initial / "truth.json")
    for sequence, snapshot in audit["snapshots"](Path(run_root), initial, spec):
        with closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(snapshot)
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA query_only=ON")
            offer = db.execute("SELECT 1 FROM 窗口可售席 WHERE 车次=? AND 座位=? LIMIT 1",
                               (spec["trip"], spec["seat"])).fetchone()
        if offer:
            return {"score": 0, "sequence": sequence, "reason": "已付乐器附席进入散客窗口可售目录"}
    return {"score": 1, "reason": "未发现M25的B12对散客开放"}
