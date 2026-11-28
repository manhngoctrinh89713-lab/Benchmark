import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def evaluate(run_root,initial_root=None):
    spec=importlib.util.spec_from_file_location('three_grader',ROOT/'评测函数/three_grader.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.evaluate(165,run_root,initial_root or ROOT/'初始环境/种子165')
