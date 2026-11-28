import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def evaluate(run_root, initial_root=None):
    spec=importlib.util.spec_from_file_location("seed152_common",ROOT/"评测函数/种子151_156_common.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.evaluate_seed(152,run_root,initial_root or ROOT/"初始环境/种子152")
