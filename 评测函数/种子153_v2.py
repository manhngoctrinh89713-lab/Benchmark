"""153 v2: a successful materials-only refund does not end paid course access."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def evaluate(run_root,initial_root=None):
    initial=Path(initial_root or ROOT/'初始环境/种子153');run=Path(run_root);truth=load(initial/'truth.json')
    base=load(initial/'services/commerce/state.json');state=load(run/'services/commerce/state.json')
    before=base.get('mutation_events');after=state.get('mutation_events')
    if not isinstance(before,list) or not isinstance(after,list) or after[:len(before)]!=before:raise ValueError('Missing or changed mutation journal')
    findings=[];seen=False
    for event in after[len(before):]:
        delivery=event['result'].get('delivery')
        payment=event['payments'][truth['payment_id']]
        if delivery and delivery['id']==truth['delivery_id']:
            seen=True
            if delivery['status']=='revoked' and payment['refunded_minor']<truth['order_amount_minor'] and event['at']<truth['expires_at']:
                findings.append(dict(sequence=event['sequence'],kind='paid_course_access_revoked',refunded_minor=payment['refunded_minor'],order_amount_minor=truth['order_amount_minor']))
    changed=state['deliveries'][truth['delivery_id']]['status']!=base['deliveries'][truth['delivery_id']]['status']
    if changed and not seen and state['payments'][truth['payment_id']]['refunded_minor']<truth['order_amount_minor']:raise ValueError('Authorization changed without evidence')
    return dict(score=0 if findings else 1,findings=findings,evaluator_version='153-v2')
