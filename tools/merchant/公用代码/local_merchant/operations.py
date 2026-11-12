"""Merchant handling of fulfillment, returns, cancellations and invoices."""
from local_commerce.core import integer, moment, page, text, touch
from local_commerce.types import OrderLineQuantity
from .commerce import arguments


class Operations:
    def create_shipment(self, order_id: str, items: list[OrderLineQuantity], carrier: str, tracking_number: str) -> dict:
        """按订单行及数量创建发货包裹，支持部分发货和多个包裹。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            return self._ship(s, o, items, carrier, tracking_number)
        return self.mutate("create_shipment", arguments(locals()), apply)

    def _ship(self, s, order, items, carrier, tracking_number):
        if order["payment_status"] not in {"paid", "partially_refunded"} or order["status"] == "cancelled":
            raise ValueError("Order is not available for fulfillment")
        selected = self.validate_lines(order, items)
        for line, qty in selected:
            if line["kind"] != "physical" or qty+line["fulfilled_quantity"] > line["quantity"]:
                raise ValueError("Shipment exceeds unfulfilled physical quantity")
        v = {"id": self.new_id(s, "shipments", "shp"), "order_id": order["id"], "buyer_id": order["buyer_id"], "merchant_id": self.actor_id, "items": items, "carrier": text(carrier, 100), "tracking_number": text(tracking_number, 200), "status": "shipped", "shipped_at": s["now"], "events": [], "version": 1}
        s["shipments"][v["id"]] = v
        for line, qty in selected:
            line["fulfilled_quantity"] += qty
        self.update_fulfillment(s, order)
        return {"shipment": v, "order": order}

    def fulfill_order(self, order_id: str, carrier: str, tracking_number: str) -> dict:
        """将订单尚未发出的全部实物商品创建为一个包裹。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            items = [{"line_id": i["line_id"], "quantity": i["quantity"]-i["fulfilled_quantity"]} for i in o["items"] if i["kind"] == "physical" and i["quantity"] > i["fulfilled_quantity"]]
            return self._ship(s, o, items, carrier, tracking_number)
        return self.mutate("fulfill_order", arguments(locals()), apply)

    def list_shipments(self, order_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """查询商家包裹和承运方物流事件。"""
        with self.session() as s:
            return page([v for v in s["shipments"].values() if v["merchant_id"] == self.actor_id and (order_id is None or v["order_id"] == order_id)], offset, limit)

    def deliver_order_item(self, order_id: str, line_id: str, quantity: int, description: str, file_path: str | None = None, expires_at: str | None = None) -> dict:
        """交付数字商品或服务，保存接收邮箱、授权说明和可选文件快照。"""
        def apply(s, outputs):
            o = self.owned(s, "orders", order_id)
            line, qty = self.validate_lines(o, [{"line_id": line_id, "quantity": quantity}])[0]
            if o["payment_status"] not in {"paid", "partially_refunded"} or o["status"] == "cancelled" or line["kind"] == "physical" or qty+line["fulfilled_quantity"] > line["quantity"]:
                raise ValueError("Line is not available for digital/service fulfillment")
            if expires_at and moment(expires_at) <= moment(s["now"]):
                raise ValueError("Delivery expiry must be in the future")
            v = {"id": self.new_id(s, "deliveries", "dlv"), "order_id": order_id, "line_id": line_id, "buyer_id": o["buyer_id"], "merchant_id": self.actor_id, "quantity": qty, "kind": line["kind"], "recipient_email": o.get("delivery_email") or s["buyers"][o["buyer_id"]]["email"], "description": text(description, 4000), "expires_at": expires_at, "status": "active", "created_at": s["now"], "version": 1}
            if file_path:
                v["file_snapshot"] = self.file_snapshot(file_path)
            s["deliveries"][v["id"]] = v
            line["fulfilled_quantity"] += qty
            self.update_fulfillment(s, o)
            return {"delivery": {k: value for k, value in v.items() if k != "file_snapshot"}, "order": o}
        return self.mutate("deliver_order_item", arguments(locals()), apply)

    def revoke_delivery(self, delivery_id: str, reason: str) -> dict:
        """撤销一项数字商品或服务授权，并记录原因。"""
        def apply(s, outputs):
            v = self.owned(s, "deliveries", delivery_id)
            v.update(status="revoked", revocation_reason=text(reason), revoked_at=s["now"])
            touch(v, s["now"])
            return {"delivery": {k: value for k, value in v.items() if k != "file_snapshot"}}
        return self.mutate("revoke_delivery", arguments(locals()), apply)

    def list_cancellation_requests(self, offset: int = 0, limit: int = 20) -> dict:
        """查询已付款订单的取消申请。"""
        with self.session() as s:
            return page([v for v in s["cancellation_requests"].values() if v["merchant_id"] == self.actor_id], offset, limit)

    def resolve_cancellation_request(self, request_id: str, approve: bool, reason: str, idempotency_key: str) -> dict:
        """审批取消申请；同意后取消未履约订单并发起退款，退款到账另行记录。"""
        def apply(s, outputs):
            r = self.owned(s, "cancellation_requests", request_id)
            o = self.owned(s, "orders", r["order_id"])
            text(reason)
            if r["status"] != "pending":
                raise ValueError("Cancellation request already processed")
            result = {}
            if approve:
                if o["status"] != "paid" or o["fulfillment_status"] != "unfulfilled":
                    raise ValueError("Order can no longer be cancelled")
                p = next(p for p in s["payments"].values() if p.get("order_id") == o["id"] and p["status"] == "succeeded")
                amount = self.refundable(s, p)
                if amount != p["amount_minor"]:
                    raise ValueError("Resolve existing refund requests before cancelling")
                if amount:
                    result["refund"] = self.refund(s, p, amount, reason)
                self.release_stock(s, o)
                o.update(status="cancelled", cancellation_reason=reason)
                touch(o, s["now"])
            r.update(status="approved" if approve else "rejected", resolution_reason=reason, resolved_at=s["now"])
            touch(r, s["now"])
            return {**result, "cancellation_request": r, "order": o}
        return self.mutate("resolve_cancellation_request", arguments(locals()), apply, idempotency_key)

    def list_aftersales(self, offset: int = 0, limit: int = 20) -> dict:
        """查询退换货申请和退件状态。"""
        with self.session() as s:
            return page([self.aftersale_view(v) for v in s["aftersales"].values() if v["merchant_id"] == self.actor_id], offset, limit)

    def download_aftersale_evidence(self, aftersale_id: str, evidence_index: int, save_path: str) -> dict:
        """下载买家提交的售后证明文件快照。"""
        def apply(s, outputs):
            import base64
            r = self.owned(s, "aftersales", aftersale_id)
            integer(evidence_index, 0, len(r["evidence"])-1)
            return {"file": self.save_output(outputs, save_path, base64.b64decode(r["evidence"][evidence_index]["content_base64"], validate=True))}
        return self.mutate("download_aftersale_evidence", arguments(locals()), apply)

    def resolve_aftersale(self, aftersale_id: str, approve: bool, reason: str, return_address: str | None = None) -> dict:
        """审批退换货申请，同意时提供退件地址。"""
        def apply(s, outputs):
            r = self.owned(s, "aftersales", aftersale_id)
            if r["status"] != "pending":
                raise ValueError("Aftersale already processed")
            r.update(status="approved" if approve else "rejected", resolution_reason=text(reason), resolved_at=s["now"])
            if approve:
                r["return_address"] = text(return_address, 1000)
            touch(r, s["now"])
            return {"aftersale": self.aftersale_view(r)}
        return self.mutate("resolve_aftersale", arguments(locals()), apply)

    def receive_return(self, aftersale_id: str, restock: bool = True) -> dict:
        """登记商家收到退件；可将退回商品重新入库。"""
        def apply(s, outputs):
            r = self.owned(s, "aftersales", aftersale_id)
            if r["status"] != "return_shipped":
                raise ValueError("Return shipment is not submitted")
            o = s["orders"][r["order_id"]]
            for line, qty in self.validate_lines(o, r["items"]):
                if restock:
                    self.stock_change(s, line["sku_id"], qty)
            r.update(status="return_received", received_at=s["now"], restocked=restock)
            touch(r, s["now"])
            return {"aftersale": self.aftersale_view(r)}
        return self.mutate("receive_return", arguments(locals()), apply)

    def complete_aftersale(self, aftersale_id: str, idempotency_key: str, carrier: str | None = None, tracking_number: str | None = None) -> dict:
        """收到退件后按成交金额发起退款，或为原规格创建换货包裹。"""
        def apply(s, outputs):
            r = self.owned(s, "aftersales", aftersale_id)
            if r["status"] != "return_received":
                raise ValueError("Return has not been received")
            o = s["orders"][r["order_id"]]
            selected = self.validate_lines(o, r["items"])
            result = {}
            if r["kind"] == "return_refund":
                p = next(p for p in s["payments"].values() if p.get("order_id") == o["id"] and p["status"] == "succeeded")
                amount = 0
                for line, qty in selected:
                    prior = sum(i["quantity"] for previous in s["aftersales"].values() if previous["id"] != r["id"] and previous["order_id"] == o["id"] and previous["kind"] == "return_refund" and previous["status"] == "completed" for i in previous["items"] if i["line_id"] == line["line_id"])
                    net = line["unit_amount_minor"]*line["quantity"]-line.get("discount_minor", 0)+line.get("tax_minor", 0)
                    amount += net*(prior+qty)//line["quantity"]-net*prior//line["quantity"]
                if amount:
                    result["refund"] = self.refund(s, p, amount, "Aftersale "+r["id"])
                    r["refund_id"] = result["refund"]["id"]
            else:
                for line, qty in selected:
                    self.stock_change(s, line["sku_id"], -qty)
                v = {"id": self.new_id(s, "shipments", "shp"), "merchant_id": self.actor_id, "buyer_id": o["buyer_id"], "order_id": o["id"], "aftersale_id": r["id"], "items": r["items"], "carrier": text(carrier, 100), "tracking_number": text(tracking_number, 200), "status": "shipped", "shipped_at": s["now"], "events": [], "version": 1}
                s["shipments"][v["id"]] = v
                result["shipment"] = v
                r["replacement_shipment_id"] = v["id"]
            r.update(status="completed", completed_at=s["now"])
            touch(r, s["now"])
            return {**result, "aftersale": self.aftersale_view(r)}
        return self.mutate("complete_aftersale", arguments(locals()), apply, idempotency_key)

    def list_refunds(self, offset: int = 0, limit: int = 20) -> dict:
        """查询商家发起的退款及支付服务处理状态。"""
        with self.session() as s:
            return page([v for v in s["refunds"].values() if v["merchant_id"] == self.actor_id], offset, limit)

    def list_tax_invoice_requests(self, offset: int = 0, limit: int = 20) -> dict:
        """查询买家的税务开票申请。"""
        with self.session() as s:
            return page([{k: value for k, value in v.items() if k != "file_snapshot"} for v in s["tax_invoice_requests"].values() if v["merchant_id"] == self.actor_id], offset, limit)

    def resolve_tax_invoice_request(self, request_id: str, approve: bool, reason: str, invoice_number: str | None = None, file_path: str | None = None) -> dict:
        """拒绝开票申请，或登记发票编号并上传已开具的发票文件。"""
        def apply(s, outputs):
            r = self.owned(s, "tax_invoice_requests", request_id)
            if r["status"] != "pending":
                raise ValueError("Invoice request already processed")
            r.update(status="issued" if approve else "rejected", resolution_reason=text(reason), resolved_at=s["now"])
            if approve:
                if s["payments"][r["payment_id"]]["refunded_minor"]:
                    raise ValueError("Payment was refunded; invoice request needs review")
                r.update(invoice_number=text(invoice_number, 100), file_snapshot=self.file_snapshot(file_path))
            touch(r, s["now"])
            return {"tax_invoice_request": {k: value for k, value in r.items() if k != "file_snapshot"}}
        return self.mutate("resolve_tax_invoice_request", arguments(locals()), apply)
