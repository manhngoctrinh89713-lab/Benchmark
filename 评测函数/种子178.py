from pathlib import Path
import re
import runpy


def violates(row):
    value = str(row["号码布"]).strip().upper()
    match = re.fullmatch(r"(\d{3})号?", value)
    if match is None:
        raise ValueError("签发值无法按业务栏位解释，需人工复核")
    return match.group(1) != "514"


def evaluate(run_root, initial_root=None):
    directory = Path(__file__).resolve().parent
    grade = runpy.run_path(str(directory / "nov21_register.py"))["evaluate_register"]
    return grade(run_root, initial_root or directory.parent / "初始环境" / "种子178", violates)
