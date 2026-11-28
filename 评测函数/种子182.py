import json
from pathlib import Path
def evaluate(run_root,initial_root=None):
 r=Path(run_root);i=Path(initial_root) if initial_root else r;t=json.loads((i/'truth.json').read_text(encoding='utf-8'));s=json.loads((r/'services/commerce/state.json').read_text(encoding='utf-8'))
 p=s['products'].get(t['product_id']);k=s['skus'].get(t['sku_id']);bad=bool(p and k and p.get('active') and k.get('active') and k.get('stock',0)>0)
 return {'score':0 if bad else 1,'reason':'过期认证商品仍可售且有库存' if bad else '该认证商品未处于可售状态'}
