"""Buyer order, shipment, aftersale and payment views."""
import copy
import json

from local_commerce.core import integer, moment, page, text, touch, version
from local_commerce.types import Address, OrderLineQuantity
from .accounts import locals_args


class Orders:
    def list_my_orders(self, status: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """分页查询自己的订单，可按订单状态筛选。"""
        with self.session() as s:
            return page([o for o in s["orders"].values() if o["buyer_id"] == self.actor_id and (status is None or o["status"] == status)], offset, limit)

    def get_my_order(self, order_id: str) -> dict:
        """读取订单成交快照、支付状态、履约状态及包裹。"""
        with self.session() as s:
            return {"order": self.owned(s, "orders", order_id), "shipments": [v for v in s["shipments"].values() if v["order_id"] == order_id], "deliveries": [self.delivery_view(v) for v in s["deliveries"].values() if v["order_id"] == order_id]}

    def pay_order(self, order_id: str, payment_method_id: str, idempotency_key: str) -> dict:
        """支付待付款订单，返回本次支付尝试的独立状态。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            if o["status"] != "pending_payment" or o.get("reservation_expires_at") and moment(s["now"]) >= moment(o["reservation_expires_at"]) or any(p.get("order_id") == order_id and p["status"] in {"pending", "succeeded"} for p in s["payments"].values()):
                raise ValueError("Order is not payable")
            p = self.charge(s, self.actor_id, o["merchant_id"], o["total_minor"], o["currency"], payment_method_id, order_id=order_id)
            self.apply_payment(s, p)
            return {"payment": p, "order": o}
        return self.mutate("pay_order", locals_args(locals()), apply, idempotency_key)

    def update_my_order(self, order_id: str, note: str | None = None, shipping_address: Address | None = None, expected_version: int | None = None) -> dict:
        """修改订单备注；未付款且未发货的订单可修改同一配送地区内的地址。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            version(o, expected_version)
            if o["status"] in {"cancelled", "refunded"}:
                raise ValueError("Order is closed")
            if note is not None:
                if note:
                    text(note)
                o["note"] = note
            if shipping_address is not None:
                if o["status"] != "pending_payment" or not o.get("shipping_address") or any(p.get("order_id") == order_id and p["status"] == "pending" for p in s["payments"].values()):
                    raise ValueError("Address cannot be changed at this stage")
                address = self.address_check(shipping_address)
                if address["country_code"] != o["shipping_address"]["country_code"]:
                    raise ValueError("New destination requires a new checkout")
                o["shipping_address"] = address
            touch(o, s["now"])
            return {"order": o}
        return self.mutate("update_my_order", locals_args(locals()), apply)

    def reorder(self, order_id: str) -> dict:
        """把历史订单的规格和数量加入当前购物车，使用当前商品状态和价格。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            cid = self.actor_id+"__"+o["merchant_id"]
            c = s["carts"].setdefault(cid, {"id": cid, "buyer_id": self.actor_id, "merchant_id": o["merchant_id"], "items": [], "version": 0})
            for line in o["items"]:
                sku = self.get(s, "skus", line["sku_id"])
                if not sku["active"] or not s["products"][sku["product_id"]]["active"]:
                    raise ValueError("A previous SKU is no longer on sale")
                found = next((v for v in c["items"] if v["sku_id"] == sku["id"]), None)
                if found:
                    found["quantity"] = integer(found["quantity"]+line["quantity"], 1, 1000)
                else:
                    c["items"].append({"sku_id": sku["id"], "product_id": sku["product_id"], "quantity": line["quantity"]})
            if len(c["items"]) > 50:
                raise ValueError("Cart exceeds 50 lines")
            touch(c, s["now"])
            return {"cart": self.cart_view(s, o["merchant_id"])}
        return self.mutate("reorder", {"order_id": order_id}, apply)

    def cancel_my_order(self, order_id: str, reason: str) -> dict:
        """直接取消未付款订单并释放库存。"""
        return self.mutate("cancel_my_order", locals_args(locals()), lambda s, outputs: self.cancel_order(s, self.owned(s, "orders", order_id), reason))

    def request_order_cancellation(self, order_id: str, reason: str) -> dict:
        """为已付款但未履约的订单提交取消申请，由商家处理。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            text(reason)
            if o["status"] != "paid" or o["fulfillment_status"] != "unfulfilled" or any(not i["policies"].get("cancellation_allowed", True) for i in o["items"]):
                raise ValueError("Order does not allow cancellation requests")
            if any(v["order_id"] == order_id and v["status"] == "pending" for v in s["cancellation_requests"].values()):
                raise ValueError("Cancellation request already pending")
            r = {"id": self.new_id(s, "cancellation_requests", "cancel"), "order_id": order_id, "buyer_id": self.actor_id, "merchant_id": o["merchant_id"], "reason": reason, "status": "pending", "created_at": s["now"], "version": 1}
            s["cancellation_requests"][r["id"]] = r
            return {"cancellation_request": r}
        return self.mutate("request_order_cancellation", locals_args(locals()), apply)

    def list_my_cancellation_requests(self, offset: int = 0, limit: int = 20) -> dict:
        """查询订单取消申请及处理结果。"""
        with self.session() as s:
            return page([v for v in s["cancellation_requests"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def withdraw_cancellation_request(self, request_id: str) -> dict:
        """撤回尚未处理的订单取消申请。"""
        return self._withdraw("cancellation_requests", request_id)

    def _withdraw(self, collection, request_id):
        def apply(s, outputs):
            r = self.owned(s, collection, request_id)
            if r["status"] != "pending":
                raise ValueError("Request has already been processed")
            r["status"] = "withdrawn"
            touch(r, s["now"])
            return {"request": r}
        return self.mutate("withdraw_"+collection, {"request_id": request_id}, apply)

    def list_my_shipments(self, order_id: str, offset: int = 0, limit: int = 20) -> dict:
        """查询订单各包裹的商品数量、物流事件和签收信息。"""
        with self.session() as s:
            self.owned(s, "orders", order_id)
            return page([v for v in s["shipments"].values() if v["order_id"] == order_id], offset, limit)

    def confirm_shipment_receipt(self, shipment_id: str) -> dict:
        """记录买家确认收货，与承运方的投递记录分别保存。"""
        def apply(s, outputs):
            v = self.owned(s, "shipments", shipment_id)
            if v["status"] not in {"shipped", "in_transit", "delivered"}:
                raise ValueError("Shipment is not dispatched")
            v["buyer_confirmed_at"] = s["now"]
            touch(v, s["now"])
            return {"shipment": v}
        return self.mutate("confirm_shipment_receipt", {"shipment_id": shipment_id}, apply)

    @staticmethod
    def delivery_view(v):
        result = {k: copy.deepcopy(value) for k, value in v.items() if k != "file_snapshot"}
        if v.get("file_snapshot"):
            result["file"] = {k: value for k, value in v["file_snapshot"].items() if k != "content_base64"}
        return result

    def list_my_deliveries(self, order_id: str) -> dict:
        """查询数字商品和服务的交付记录、接收人、有效期与授权状态。"""
        with self.session() as s:
            self.owned(s, "orders", order_id)
            return {"deliveries": [self.delivery_view(v) for v in s["deliveries"].values() if v["order_id"] == order_id]}

    def download_delivery(self, delivery_id: str, save_path: str) -> dict:
        """下载有效数字交付的文件快照。"""
        def apply(s, outputs):
            import base64
            v = self.owned(s, "deliveries", delivery_id)
            if v["status"] != "active" or v.get("expires_at") and moment(s["now"]) >= moment(v["expires_at"]) or not v.get("file_snapshot"):
                raise ValueError("Delivery file is unavailable")
            result = self.save_output(outputs, save_path, base64.b64decode(v["file_snapshot"]["content_base64"], validate=True))
            s["download_events"].append({"delivery_id": delivery_id, "buyer_id": self.actor_id, "at": s["now"], **result})
            return {"file": result}
        return self.mutate("download_delivery", locals_args(locals()), apply)

    def request_aftersale(self, order_id: str, kind: str, items: list[OrderLineQuantity], reason: str, paths: list[str] | None = None) -> dict:
        """按订单行及数量申请退货退款或换货，并保存证明文件快照。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            text(reason)
            if kind not in {"return_refund", "exchange"} or o["payment_status"] not in {"paid", "partially_refunded"}:
                raise ValueError("Unsupported aftersale type or unpaid order")
            selected = self.validate_lines(o, items)
            for line, qty in selected:
                policy = line["policies"]
                if line["kind"] != "physical" or not policy.get("returnable" if kind == "return_refund" else "exchangeable", False):
                    raise ValueError("Order line does not support requested aftersale")
                shipments = [v for v in s["shipments"].values() if v["order_id"] == order_id and any(i["line_id"] == line["line_id"] for i in v["items"])]
                eligible_quantity = 0
                for shipment in shipments:
                    delivered_at = shipment.get("delivered_at") or shipment.get("buyer_confirmed_at")
                    if not shipment.get("aftersale_id") and delivered_at and 0 <= (moment(s["now"])-moment(delivered_at)).total_seconds() <= policy.get("return_days", 30)*86400:
                        eligible_quantity += sum(i["quantity"] for i in shipment["items"] if i["line_id"] == line["line_id"])
                if not eligible_quantity:
                    raise ValueError("Aftersale window is not open")
                committed = sum(i["quantity"] for r in s["aftersales"].values() if r["order_id"] == order_id and r["status"] not in {"rejected", "withdrawn"} for i in r["items"] if i["line_id"] == line["line_id"])
                if qty+committed > eligible_quantity:
                    raise ValueError("Aftersale quantity exceeds eligible units")
            if paths and len(paths) > 10:
                raise ValueError("At most ten evidence files")
            r = {"id": self.new_id(s, "aftersales", "as"), "order_id": order_id, "buyer_id": self.actor_id, "merchant_id": o["merchant_id"], "kind": kind, "items": copy.deepcopy(items), "reason": reason, "evidence": [self.file_snapshot(p) for p in paths or []], "status": "pending", "created_at": s["now"], "version": 1}
            s["aftersales"][r["id"]] = r
            return {"aftersale": self.aftersale_view(r)}
        return self.mutate("request_aftersale", locals_args(locals()), apply)

    def list_my_aftersales(self, order_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """查询退换货申请、退件及处理结果。"""
        with self.session() as s:
            return page([self.aftersale_view(r) for r in s["aftersales"].values() if r["buyer_id"] == self.actor_id and (order_id is None or r["order_id"] == order_id)], offset, limit)

    def update_aftersale(self, aftersale_id: str, reason: str, paths: list[str] | None = None) -> dict:
        """修改待处理售后申请的说明和证明文件。"""
        def apply(s, outputs):
            r = self.owned(s, "aftersales", aftersale_id)
            if r["status"] != "pending":
                raise ValueError("Aftersale is already processed")
            text(reason)
            r["reason"] = reason
            if paths is not None:
                if len(paths) > 10:
                    raise ValueError("At most ten evidence files")
                r["evidence"] = [self.file_snapshot(p) for p in paths]
            touch(r, s["now"])
            return {"aftersale": self.aftersale_view(r)}
        return self.mutate("update_aftersale", locals_args(locals()), apply)

    def withdraw_aftersale(self, aftersale_id: str) -> dict:
        """撤回待处理的退换货申请。"""
        return self._withdraw("aftersales", aftersale_id)

    def submit_return_shipment(self, aftersale_id: str, carrier: str, tracking_number: str) -> dict:
        """为获准的退换货提交退件物流信息。"""
        def apply(s, outputs):
            r = self.owned(s, "aftersales", aftersale_id)
            if r["status"] != "approved":
                raise ValueError("Aftersale must be approved first")
            text(carrier, 100)
            text(tracking_number, 100)
            r.update(status="return_shipped", return_shipment={"carrier": carrier, "tracking_number": tracking_number, "submitted_at": s["now"]})
            touch(r, s["now"])
            return {"aftersale": self.aftersale_view(r)}
        return self.mutate("submit_return_shipment", locals_args(locals()), apply)

    def list_my_payments(self, offset: int = 0, limit: int = 20) -> dict:
        """查询支付尝试及退款累计金额。"""
        with self.session() as s:
            return page([v for v in s["payments"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def request_refund(self, payment_id: str, amount_minor: int, reason: str, idempotency_key: str) -> dict:
        """向商家申请退还指定支付的部分或全部可退金额。"""
        def apply(s, outputs):
            p = self.owned(s, "payments", payment_id)
            text(reason)
            if p["status"] != "succeeded" or integer(amount_minor, 1) > self.refundable(s, p):
                raise ValueError("Requested amount exceeds refundable balance")
            r = {"id": self.new_id(s, "refund_requests", "rr"), "buyer_id": self.actor_id, "merchant_id": p["merchant_id"], "payment_id": payment_id, "amount_minor": amount_minor, "reason": reason, "status": "pending", "created_at": s["now"], "version": 1}
            s["refund_requests"][r["id"]] = r
            return {"refund_request": r}
        return self.mutate("request_refund", locals_args(locals()), apply, idempotency_key)

    def list_my_refund_requests(self, offset: int = 0, limit: int = 20) -> dict:
        """查询退款申请与商家的审批结果。"""
        with self.session() as s:
            return page([r for r in s["refund_requests"].values() if r["buyer_id"] == self.actor_id], offset, limit)

    def withdraw_refund_request(self, request_id: str) -> dict:
        """撤回待审批的退款申请。"""
        return self._withdraw("refund_requests", request_id)

    def list_my_refunds(self, offset: int = 0, limit: int = 20) -> dict:
        """查询退款交易的处理中、成功和失败状态。"""
        with self.session() as s:
            return page([v for v in s["refunds"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def download_receipt(self, payment_id: str, save_path: str) -> dict:
        """将已成功支付的收据保存为 JSON 文件。"""
        def apply(s, outputs):
            p = self.owned(s, "payments", payment_id)
            if p["status"] != "succeeded":
                raise ValueError("Receipt requires successful payment")
            return {"file": self.save_output(outputs, save_path, json.dumps({"payment": p}, ensure_ascii=False, indent=2).encode())}
        return self.mutate("download_receipt", locals_args(locals()), apply)

    def download_refund_receipt(self, refund_id: str, save_path: str) -> dict:
        """将已成功到账退款的凭证保存为 JSON 文件。"""
        def apply(s, outputs):
            refund = self.owned(s, "refunds", refund_id)
            if refund["status"] != "succeeded":
                raise ValueError("Refund receipt requires settled funds")
            return {"file": self.save_output(outputs, save_path, json.dumps({"refund": refund}, ensure_ascii=False, indent=2).encode())}
        return self.mutate("download_refund_receipt", locals_args(locals()), apply)
