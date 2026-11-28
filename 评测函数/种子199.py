import re
from pathlib import Path
import runpy


def violates(row):
    value = str(row["机械键位"]).strip()
    match = re.fullmatch(r"第?([0-9]+)键?", value)
    if not match:
        raise ValueError("无法识别派工键位")
    return int(match.group(1)) != 40


def evaluate(run_root, initial_root=None):
    directory = Path(__file__).resolve().parent
    grade = runpy.run_path(str(directory / "nov21_register.py"))["evaluate_register"]
    return grade(run_root, initial_root or directory.parent / "初始环境" / "种子199", violates)
