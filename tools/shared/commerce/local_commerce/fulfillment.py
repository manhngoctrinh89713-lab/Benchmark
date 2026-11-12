"""Order-line fulfillment helpers shared by both parties."""
import copy
from .common import integer, touch


class Fulfillment:
    @staticmethod
    def validate_lines(order, items):
        if not items or len(items) > 50 or len({i["line_id"] for i in items}) != len(items):
            raise ValueError("Select unique nonempty order lines")
        result = []
        for item in items:
            line = next((v for v in order["items"] if v["line_id"] == item["line_id"]), None)
            if line is None or integer(item["quantity"], 1, 1000) > line["quantity"]:
                raise ValueError("Invalid order-line quantity")
            result.append((line, item["quantity"]))
        return result

    @staticmethod
    def aftersale_view(r):
        result = copy.deepcopy(r)
        result["evidence"] = [{k: v for k, v in e.items() if k != "content_base64"} for e in r.get("evidence", [])]
        return result

    @staticmethod
    def update_fulfillment(s, order):
        quantity = sum(i["quantity"] for i in order["items"])
        done = sum(i["fulfilled_quantity"] for i in order["items"])
        order["fulfillment_status"] = "fulfilled" if done == quantity else "partially_fulfilled" if done else "unfulfilled"
        touch(order, s["now"])
