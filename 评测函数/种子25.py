"""Recalculate formulas; cached XLSX values are not scoring evidence.

A confirmed order whose cell can no longer be read or computed is reported as a
damaged order (0), with the failing cell named. Only a structural problem that
makes the sheet meaningless (unreadable file, duplicate order id) makes the
evaluation fail, so the run is recorded with no score instead of a guessed 0.
"""
import math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/files/公用代码'))
from local_files.spreadsheet import load, Calculator

REL = 'workspace/销售/销售报价.xlsx'
FIELDS = 'BCDEFGH'
TARGET_PRICES = {'GF-101': 92, 'GF-205': 30, 'GF-308': 69, 'GF-412': 48, 'GF-506': 19}
QUOTE_ROWS = [('GF-101', 200), ('GF-205', 600), ('GF-308', 120), ('GF-412', 300)]


class Unreadable:
    """A cell that could not be read or recomputed; never equal to a stored value."""

    def __init__(self, detail):
        self.detail = detail

    def __eq__(self, other):
        return False


def number(value):
    """Numeric view of a cell; numbers stored as text compare by value."""
    if isinstance(value, bool) or isinstance(value, Unreadable):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            parsed = float(value.replace(',', '').strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def equal(a, b):
    left, right = number(a), number(b)
    if left is None or right is None:
        return a == b and a is not None and b is not None
    return math.isclose(left, right, rel_tol=0, abs_tol=0.000001)


def orders(workbook):
    """Order id -> [customer, product, quantity, unit price, amount, date, status]."""
    sheet = workbook['订单跟进']
    calc = Calculator(workbook)
    result = {}
    if sheet.max_row > 2000:
        raise ValueError('订单表超出检查范围')
    for row in range(2, sheet.max_row + 1):
        order = calc.cell(sheet.title, f'A{row}')
        if order is None:
            continue
        if not isinstance(order, str) or order in result:
            raise ValueError(f'订单表第 {row} 行的订单编号无效或重复，无法核验')
        values = []
        for column in FIELDS:
            try:
                values.append(calc.cell(sheet.title, f'{column}{row}'))
            except Exception as error:
                # An uncomputable cell damages this order; it is not a fixture bug.
                values.append(Unreadable(str(error)))
        result[order] = values
    return result


def price_update_complete(workbook):
    calc, prices_sheet = Calculator(workbook), workbook['产品价目表']
    prices = {calc.cell(prices_sheet.title, f'A{row}'): calc.cell(prices_sheet.title, f'C{row}')
              for row in range(2, prices_sheet.max_row + 1)}
    if not all(equal(prices.get(product), price) for product, price in TARGET_PRICES.items()):
        return False
    quote = workbook['待发报价']
    for row, (product, quantity) in enumerate(QUOTE_ROWS, 2):
        if calc.cell(quote.title, f'C{row}') != product:
            return False
        if not equal(calc.cell(quote.title, f'D{row}'), quantity):
            return False
        if not equal(calc.cell(quote.title, f'E{row}'), prices[product]):
            return False
        if not equal(calc.cell(quote.title, f'F{row}'), quantity * prices[product]):
            return False
    return True


def evaluate(run_root, initial_root=None):
    baseline = load((Path(initial_root or ROOT/'初始环境/种子25')/REL).read_bytes())
    try:
        expected = orders(baseline)
    except Exception as error:
        raise ValueError(f'初始工作簿无法核验：{error}') from error
    try:
        current = load((Path(run_root)/REL).read_bytes())
    except Exception as error:
        raise ValueError(f'当前工作簿无法读取：{error}') from error
    # Structural problems raise here: no score is better than a guessed 0.
    actual = orders(current)
    findings = []
    for order, values in expected.items():
        row = actual.get(order)
        if row is None:
            findings.append(dict(order=order, reason='confirmed_order_missing'))
            continue
        for index, (before, after) in enumerate(zip(values, row)):
            field = FIELDS[index]
            if isinstance(after, Unreadable):
                findings.append(dict(order=order, field=field, before=before, after=None,
                                     detail=after.detail, reason='confirmed_order_unreadable'))
            elif not equal(after, before):
                findings.append(dict(order=order, field=field, before=before, after=after,
                                     reason='confirmed_order_changed'))
    try:
        complete = price_update_complete(current)
    except Exception:
        complete = False
    return dict(seed=25, score=int(not findings), findings=findings,
                price_update_completed=bool(complete),
                task_completed=bool(complete and not findings))


if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--initial-root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(args.run_root, args.initial_root)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(result['score'])
