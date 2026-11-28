"""Dispatch an approved refund without changing its business identity."""
import channel

def dispatch(request):
    refund_id = request["refund_id"]
    for attempt in range(2):
        try:
            receipt = channel.submit_refund(refund_id, request["payment_id"], request["amount_minor"])
            return {"state": receipt["state"], "refund_id": refund_id, "receipt": receipt}
        except TimeoutError:
            continue
    return {"state": "pending", "refund_id": refund_id}
