import json
from .internal_verify import verify_notice

def handle_notice(raw_body, headers, orders):
    notice = json.loads(raw_body)
    if verify_notice(raw_body, headers.get("X-Pay-Signature", "")):
        orders.mark_paid(notice["order_id"])
        return True
    return False
