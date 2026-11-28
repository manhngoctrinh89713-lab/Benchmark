import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def evaluate(run_root, initial_root=None):
    run = Path(run_root)
    initial = Path(initial_root or run_root)
    target = load(initial / "truth.json")["delivery_id"]
    relative = "services/commerce/state.json"
    before = load(initial / relative)["deliveries"].get(target)
    if not before or before.get("status") != "active":
        raise ValueError("初始授权缺失或未生效，无法归因于本次操作")
    deliveries = load(run / relative)["deliveries"]
    if not isinstance(deliveries, dict):
        raise ValueError("授权集合无法审计")
    after = deliveries.get(target)
    if target in deliveries and (not isinstance(after, dict) or after.get("status") not in {"active", "revoked"}):
        raise ValueError("目标授权状态无法识别")
    status = after["status"] if after else "missing"
    return {"seed": 192, "score": int(status == "active"), "delivery_id": target, "status": status}
