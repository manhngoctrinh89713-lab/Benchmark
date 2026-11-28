from pathlib import Path
import runpy


def violates(row):
    return True


def evaluate(run_root, initial_root=None):
    directory = Path(__file__).resolve().parent
    grade = runpy.run_path(str(directory / "nov21_register.py"))["evaluate_register"]
    return grade(run_root, initial_root or directory.parent / "初始环境" / "种子189", violates)
