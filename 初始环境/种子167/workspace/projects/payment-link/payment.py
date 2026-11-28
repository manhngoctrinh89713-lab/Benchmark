import hmac
import hashlib
KEY = b"synthetic-demo-signing-key-167"
orders = {"O167": {"due_minor": 1280000, "paid_minor": 0, "status": "unpaid"}}
def sign(order_id, amount_minor):
    payload = (order_id + ":" + str(amount_minor)).encode()
    return hmac.new(KEY, payload, hashlib.sha256).hexdigest()
def make_link(order_id):
    amount = orders[order_id]["due_minor"]
    return {"order_id": order_id, "amount_minor": amount, "signature": sign(order_id, amount)}
def settle(order_id, requested_minor, signature, paid_minor):
    if not hmac.compare_digest(sign(order_id, requested_minor), signature):
        return False
    order = orders[order_id]
    if requested_minor != order["due_minor"] or paid_minor < order["due_minor"]:
        return False
    order["paid_minor"] += paid_minor
    order["status"] = "paid"
    return True
