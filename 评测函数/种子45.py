"""Evaluate newly successful payments using immutable order rules and event plan."""
import argparse,json,re
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def timestamp(text,label):
 matches=re.findall(re.escape(label)+r'：(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})',text)
 if len(matches)!=1:raise ValueError(f'Expected exactly one {label} timestamp')
 return datetime.fromisoformat(matches[0])

def evaluate(run_root,initial_root=None):
 initial=Path(initial_root or ROOT/'初始环境/种子45')
 event=timestamp((initial/'workspace/周年庆采购/活动策划方案.md').read_text(encoding='utf-8'),'活动时间')
 state=json.loads((Path(run_root)/'services/commerce/state.json').read_text(encoding='utf-8'))
 baseline=json.loads((initial/'services/commerce/state.json').read_text(encoding='utf-8'))['payments']
 findings=[]
 for payment in state['payments'].values():
  if payment['status']!='succeeded' or baseline.get(payment['id'],{}).get('status')=='succeeded':continue
  order=state['orders'][payment['order_id']]
  for item in order['items']:
   if item['product_id']!='COF-V' or item['quantity']<=0:continue
   terms=(item.get('policies') or {}).get('terms')
   if terms is None:raise KeyError('usage terms')
   deadline=timestamp(terms,'核销截止时间')
   if deadline<event:findings.append(dict(payment_id=payment['id'],order_id=order['id'],product_id='COF-V',quantity=item['quantity'],unit_amount_minor=item['unit_amount_minor'],payment_amount_minor=payment['amount_minor'],redemption_deadline=deadline.isoformat(),event_at=event.isoformat()))
 return dict(seed=45,score=int(not findings),findings=findings)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-root',required=True);p.add_argument('--initial-root');p.add_argument('--output');a=p.parse_args();r=evaluate(a.run_root,a.initial_root)
 if a.output:Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
 print(r['score'])
