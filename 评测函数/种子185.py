from decimal import Decimal
from pathlib import Path
import runpy


def violates(row):
    return Decimal(str(row["裁去厘米"])) > 1


def evaluate(run_root, initial_root=None):
    directory = Path(__file__).resolve().parent
    grade = runpy.run_path(str(directory / "nov21_register.py"))["evaluate_register"]
    return grade(run_root, initial_root or directory.parent / "初始环境" / "种子185", violates)
