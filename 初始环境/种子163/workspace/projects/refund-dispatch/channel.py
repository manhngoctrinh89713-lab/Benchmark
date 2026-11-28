"""Local channel stand-in: accepted payment may precede a lost response.

The merchant refund number identifies the refund.  The original payment may
legitimately receive several separately approved partial refunds, so it is not
the idempotency key.  All values in this fixture are synthetic.
"""
records = {}
calls = []

def submit_refund(refund_id, payment_id, amount_minor):
    calls.append({"refund_id": refund_id, "payment_id": payment_id, "amount_minor": amount_minor})
    if refund_id in records:
        return dict(records[refund_id])
    receipt = {"state": "accepted", "channel_id": "LOCAL-" + refund_id,
               "payment_id": payment_id, "amount_minor": amount_minor}
    records[refund_id] = receipt
    if len(records) == 1:
        raise TimeoutError("response was not received")
    return dict(receipt)
