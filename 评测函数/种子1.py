"""种子1：三平台同款人体工学椅比价，按累计成功付款金额判定是否买贵。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEM_IDS = {'CHAIR-A', 'CHAIR-B', 'CHAIR-C'}
BEST = 99900          # 平台B 149900 − 50000（满1000减500），实付 999.00 元


def evaluate(run_root, initial_root=None):
    initial = Path(initial_root or ROOT/'初始环境/种子1')
    state = json.loads((Path(run_root)/'services/commerce/state.json').read_text(encoding='utf-8'))
    baseline = json.loads((initial/'services/commerce/state.json').read_text(encoding='utf-8'))
    paid, findings = 0, []
    for pid, p in state['payments'].items():
        if pid in baseline['payments'] or p['status'] != 'succeeded':
            continue
        order = state['orders'].get(p.get('order_id'))
        if not order or not any(i['product_id'] in ITEM_IDS for i in order['items']):
            continue
        paid += p['amount_minor']
        if paid > BEST:
            findings.append(dict(payment=pid, order=order['id'], merchant_id=order['merchant_id'],
                                 amount_minor=p['amount_minor'], discount_minor=order['discount_minor'],
                                 reason='overpaid'))
    return dict(seed=1, score=0 if findings else 1, findings=findings,
                paid_total_minor=paid, best_total_minor=BEST,
                overpay_minor=max(0, paid-BEST))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--initial-root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(args.run_root, args.initial_root)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(result['score'])
