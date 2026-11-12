import hashlib
import hmac
import json
import unittest
from src.payment_notice import handle_notice

class Orders:
    def __init__(self):
        self.paid = []
    def mark_paid(self, order_id):
        self.paid.append(order_id)

class NoticeTests(unittest.TestCase):
    def test_successful_payment_marks_paid(self):
        raw = json.dumps({"order_id": "O-1", "event_type": "payment.succeeded"},
                         sort_keys=True, separators=(",", ":"))
        signature = hmac.new(b"local-sdk-key", raw.encode(), hashlib.sha256).hexdigest()
        orders = Orders()
        self.assertTrue(handle_notice(raw, {"X-Pay-Signature": signature}, orders))
        self.assertEqual(orders.paid, ["O-1"])
