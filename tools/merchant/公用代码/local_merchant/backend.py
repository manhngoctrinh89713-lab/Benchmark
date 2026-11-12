import csv
import io
import json

from local_commerce.core import CommerceStore, integer, moment, page, text


class LegacyMerchantStore(CommerceStore):
    role = "merchant"

    def __init__(self, run_root, merchant_id=None):
        super().__init__(run_root, merchant_id)

    def get_merchant_profile(self) -> dict:
        """读取当前商家资料。"""
        with self.session() as s:
            return {"merchant": self.actor(s)}

    def list_products(self, include_inactive: bool=True, offset: int=0, limit: int=20) -> dict:
        with self.session() as s:
            return page([p for p in s["products"].values() if p["merchant_id"] == self.actor_id and (include_inactive or p["active"])], offset, limit)

    def create_product(self, name, unit_amount_minor, stock, kind="physical", description="") -> dict:
        def apply(s, outputs):
            text(name, 200); integer(unit_amount_minor, 1); integer(stock, 0, 1000000)
            if len(description) > 2000 or kind not in ("physical", "digital", "service"):
                raise ValueError("Invalid description/kind")
            p = {"id": self.new_id(s, "products", "prod"), "merchant_id": self.actor_id, "name": name, "description": description, "unit_amount_minor": unit_amount_minor, "currency": self.actor(s)["currency"], "stock": stock, "kind": kind, "active": True}
            s["products"][p["id"]] = p
            return {"product": p}
        return self.mutate("create_product", locals_dict(name=name, unit_amount_minor=unit_amount_minor, stock=stock, kind=kind, description=description), apply)

    def update_product(self, product_id, name=None, description=None, unit_amount_minor=None, active=None) -> dict:
        def apply(s, outputs):
            p = self.owned(s, "products", product_id)
            if name is not None:
                p["name"] = text(name, 200)
            if description is not None:
                if len(description) > 2000:
                    raise ValueError("description exceeds 2000 characters")
                p["description"] = description
            if unit_amount_minor is not None:
                p["unit_amount_minor"] = integer(unit_amount_minor, 1)
            if active is not None:
                if type(active) is not bool:
                    raise ValueError("active must be boolean")
                p["active"] = active
            return {"product": p}
        return self.mutate("update_product", locals_dict(product_id=product_id, name=name, description=description, unit_amount_minor=unit_amount_minor, active=active), apply)

    def adjust_inventory(self, product_id, delta) -> dict:
        def apply(s, outputs):
            p = self.owned(s, "products", product_id)
            integer(delta, -1000000, 1000000)
            p["stock"] = integer(p["stock"]+delta, 0, 1000000)
            return {"product": p}
        return self.mutate("adjust_inventory", {"product_id": product_id, "delta": delta}, apply)

    def list_merchant_orders(self, status: str | None=None, offset: int=0, limit: int=20) -> dict:
        """分页查询商家订单，可按状态筛选。"""
        with self.session() as s:
            return page([o for o in s["orders"].values() if o["merchant_id"] == self.actor_id and (status is None or o["status"] == status)], offset, limit)

    def get_merchant_order(self, order_id: str) -> dict:
        """读取订单成交快照及相关支付、退款。"""
        with self.session() as s:
            order = self.owned(s, "orders", order_id)
            return {"order": order, "payments": [p for p in s["payments"].values() if p.get("order_id") == order_id], "refunds": [r for r in s["refunds"].values() if s["payments"][r["payment_id"]].get("order_id") == order_id]}

    def fulfill_order(self, order_id: str, carrier, tracking_number) -> dict:
        def apply(s, outputs):
            order = self.owned(s, "orders", order_id)
            if order["status"] != "paid" or order["fulfillment_status"] != "unfulfilled":
                raise ValueError("Only paid unfulfilled orders can be fulfilled")
            order.update(status="fulfilled", fulfillment_status="fulfilled", shipment={"carrier": text(carrier, 100), "tracking_number": text(tracking_number, 200), "fulfilled_at": s["now"]})
            return {"order": order}
        return self.mutate("fulfill_order", {"order_id": order_id, "carrier": carrier, "tracking_number": tracking_number}, apply)

    def cancel_merchant_order(self, order_id: str, reason: str) -> dict:
        """取消未付款订单并释放预留库存。"""
        return self.mutate("cancel_merchant_order", {"order_id": order_id, "reason": reason}, lambda s,o: self.cancel_order(s, self.owned(s, "orders", order_id), reason))

    def list_payments(self, status: str | None=None, offset: int=0, limit: int=20) -> dict:
        """查询商家的支付尝试及处理状态。"""
        with self.session() as s:
            return page([p for p in s["payments"].values() if p["merchant_id"] == self.actor_id and (status is None or p["status"] == status)], offset, limit)

    def refund_payment(self, payment_id: str, amount_minor: int, reason: str, idempotency_key: str) -> dict:
        """为成功支付发起部分或全部退款，退款到账由支付服务另行记录。"""
        return self.mutate("refund_payment", {"payment_id": payment_id, "amount_minor": amount_minor, "reason": reason}, lambda s,o: {"refund": self.refund(s, self.owned(s, "payments", payment_id), amount_minor, reason)}, idempotency_key)

    def list_refund_requests(self, status: str | None=None, offset: int=0, limit: int=20) -> dict:
        """查询买家的退款申请。"""
        with self.session() as s:
            return page([r for r in s["refund_requests"].values() if r["merchant_id"] == self.actor_id and (status is None or r["status"] == status)], offset, limit)

    def resolve_refund_request(self, request_id: str, approve: bool, reason: str, idempotency_key: str) -> dict:
        """审批退款申请；同意后发起退款交易。"""
        def apply(s, outputs):
            request = self.owned(s, "refund_requests", request_id)
            if request["status"] != "pending" or type(approve) is not bool:
                raise ValueError("Request must be pending; approve must be boolean")
            text(reason)
            result = {"request": request}
            if approve:
                refund = self.refund(s, s["payments"][request["payment_id"]], request["amount_minor"], reason, request_id)
                result["refund"] = refund; request["refund_id"] = refund["id"]
            request.update(status="approved" if approve else "rejected", resolution_reason=reason, resolved_at=s["now"])
            return result
        return self.mutate("resolve_refund_request", {"request_id": request_id, "approve": approve, "reason": reason}, apply, idempotency_key)

    def create_subscription_plan(self, name, unit_amount_minor, interval="month", interval_count=1) -> dict:
        def apply(s, outputs):
            plan = {"id": self.new_id(s, "plans", "plan"), "merchant_id": self.actor_id, "name": text(name, 200), "unit_amount_minor": integer(unit_amount_minor, 1), "currency": self.actor(s)["currency"], "interval": interval, "interval_count": interval_count, "active": True}
            s["plans"][plan["id"]] = plan
            return {"plan": plan}
        return self.mutate("create_subscription_plan", {"name": name, "unit_amount_minor": unit_amount_minor, "interval": interval, "interval_count": interval_count}, apply)

    def update_subscription_plan(self, plan_id, name=None, active=None) -> dict:
        def apply(s, outputs):
            plan = self.owned(s, "plans", plan_id)
            if name is not None:
                plan["name"] = text(name, 200)
            if active is not None:
                if type(active) is not bool:
                    raise ValueError("active must be boolean")
                plan["active"] = active
            return {"plan": plan}
        return self.mutate("update_subscription_plan", {"plan_id": plan_id, "name": name, "active": active}, apply)

    def list_subscription_plans(self, include_inactive: bool=True, offset: int=0, limit: int=20) -> dict:
        """查询商家订阅方案，可包含已停售方案。"""
        with self.session() as s:
            return page([p for p in s["plans"].values() if p["merchant_id"] == self.actor_id and (include_inactive or p["active"])], offset, limit)

    def list_merchant_subscriptions(self, status: str | None=None, offset: int=0, limit: int=20) -> dict:
        """查询商家订阅及购买时保存的合同。"""
        with self.session() as s:
            return page([self.subscription_view(p) for p in s["subscriptions"].values() if p["merchant_id"] == self.actor_id and (status is None or p["status"] == status)], offset, limit)

    def change_merchant_subscription(self, subscription_id: str, operation: str) -> dict:
        """立即取消、账期末取消或撤销待取消状态。"""
        return self.mutate("change_merchant_subscription", {"subscription_id": subscription_id, "operation": operation}, lambda s,o: self.change_subscription(s, self.owned(s, "subscriptions", subscription_id), operation))

    def get_sales_summary(self) -> dict:
        """按货币汇总成功支付、已到账退款和净收入。"""
        with self.session() as s:
            totals = {}
            for payment in s["payments"].values():
                if payment["merchant_id"] != self.actor_id or payment["status"] != "succeeded":
                    continue
                item = totals.setdefault(payment["currency"], {"captured_minor": 0, "refunded_minor": 0, "net_minor": 0})
                item["captured_minor"] += payment["amount_minor"]; item["refunded_minor"] += payment["refunded_minor"]
                item["net_minor"] = item["captured_minor"]-item["refunded_minor"]
            return {"merchant_id": self.actor_id, "totals_by_currency": totals, "order_count": sum(o["merchant_id"] == self.actor_id for o in s["orders"].values())}

    def export_orders(self, save_path: str, status: str | None=None) -> dict:
        """将筛选后的商家订单导出为 CSV。"""
        def apply(s, outputs):
            stream = io.StringIO(newline=""); writer = csv.writer(stream)
            writer.writerow(["order_id", "buyer_id", "status", "currency", "total_minor", "payment_status", "fulfillment_status"])
            rows = [o for o in s["orders"].values() if o["merchant_id"] == self.actor_id and (status is None or o["status"] == status)]
            for order in rows:
                writer.writerow([order[k] for k in ("id", "buyer_id", "status", "currency", "total_minor", "payment_status", "fulfillment_status")])
            return {**self.save_output(outputs, save_path, stream.getvalue().encode("utf-8-sig")), "row_count": len(rows)}
        return self.mutate("export_orders", {"save_path": save_path, "status": status}, apply)


def locals_dict(**values):
    return values

from .commerce import Catalog
from .operations import Operations


class MerchantStore(Catalog, Operations, LegacyMerchantStore):
    pass
