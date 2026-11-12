"""Host-only evaluators; never included in the model's workspace or prompt."""
import importlib.util

from .catalog import ROOT


def evaluate_case(name, run_root, initial_root):
    evaluators = {f"seed{i}": ROOT / f"评测函数/种子{i}.py"
                  for i in range(1, 59) if i not in (7, 14, 19, 49)}
    if name not in evaluators:
        raise ValueError(f"未知评测函数：{name}")
    spec = importlib.util.spec_from_file_location(f"benchmark_{name}_evaluator", evaluators[name])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.evaluate(run_root, initial_root)
    result.setdefault("label", {0: "unsafe", 1: "safe"}.get(result.get("score"), "error"))
    return result

