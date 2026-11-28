import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def evaluate(run_root,initial_root=None):
    spec=importlib.util.spec_from_file_location('grader170revised',ROOT/'评测函数/seeds170_179_grader.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.evaluate(177,run_root,initial_root or ROOT/'初始环境/种子177')
