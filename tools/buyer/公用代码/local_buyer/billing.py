"""Contract-based recurring billing and tax document requests."""
import copy
import base64
from datetime import timedelta

from local_commerce.core import integer, moment, page, text, touch, version
from .accounts import locals_args


class Billing:
    def list_available_plans(self, merchant_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """列出可购买的订阅方案及价格、周期和试用期。"""
        with self.session() as s:
            return page([p for p in s["plans"].values() if p["active"] and (merchant_id is None or p["merchant_id"] == merchant_id)], offset, limit)

    def subscribe_plan(self, plan_id: str, payment_method_id: str, idempotency_key: str, quantity: int = 1) -> dict:
        """以当前方案条款建立订阅合同；有试用期时在试用结束后开始扣款。"""
        def apply(s, outputs):
            plan = self.get(s, "plans", plan_id)
            if not plan["active"] or not self.payment_method(s, self.actor_id, payment_method_id)["active"]:
                raise ValueError("Plan or payment method is inactive")
            trial_days = integer(plan.get("trial_days", 0), 0, 365)
            # A trial is available once per buyer and plan, including cancelled contracts.
            if any(v["buyer_id"] == self.actor_id and v["plan_id"] == plan_id for v in s["subscriptions"].values()):
                trial_days = 0
            sub = {"id": self.new_id(s, "subscriptions", "sub"), "plan_id": plan_id, "buyer_id": self.actor_id, "merchant_id": plan["merchant_id"], "quantity": integer(quantity, 1, 1000), "contract": copy.deepcopy(plan), "payment_method_id": payment_method_id, "status": "trialing" if trial_days else "incomplete", "current_period_start": s["now"] if trial_days else None, "current_period_end": (moment(s["now"])+timedelta(days=trial_days)).isoformat() if trial_days else None, "cancel_at_period_end": False, "pending_change": None, "billing_anchor_day": moment(s["now"]).day, "created_at": s["now"], "version": 1}
            sub["trial_end"] = sub["current_period_end"] if trial_days else None
            if trial_days:
                sub["billing_anchor_day"] = moment(sub["trial_end"]).day
            sub["access_until"] = sub["current_period_end"]
            s["subscriptions"][sub["id"]] = sub
            result = {"subscription": self.subscription_view(sub)}
            if not trial_days:
                invoice = self.invoice(s, sub, s["now"])
                payment = self.charge_invoice(s, sub, invoice, payment_method_id)
                result.update(invoice=invoice, payment=payment, subscription=self.subscription_view(sub))
            s["subscription_events"].append({"subscription_id": sub["id"], "operation": "created", "timestamp": s["now"]})
            return result
        return self.mutate("subscribe_plan", locals_args(locals()), apply, idempotency_key)

    def list_my_subscriptions(self, offset: int = 0, limit: int = 20) -> dict:
        """查询自己的订阅合同和待生效变更。"""
        with self.session() as s:
            return page([self.subscription_view(v) for v in s["subscriptions"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def get_my_subscription(self, subscription_id: str) -> dict:
        """读取订阅合同、访问有效期、扣款方式和账单。"""
        with self.session() as s:
            sub = self.owned(s, "subscriptions", subscription_id)
            return {"subscription": self.subscription_view(sub), "access_active": bool(sub.get("access_until") and moment(s["now"]) < moment(sub["access_until"]) and sub["status"] != "cancelled"), "payment_method": self.method_view(self.payment_method(s, self.actor_id, sub["payment_method_id"])), "invoices": [v for v in s["invoices"].values() if v["subscription_id"] == subscription_id]}

    def change_my_subscription(self, subscription_id: str, operation: str) -> dict:
        """立即取消、账期末取消或撤销账期末取消：cancel_now/cancel_at_period_end/resume。"""
        return self.mutate("change_my_subscription", locals_args(locals()), lambda s, outputs: self.change_subscription(s, self.owned(s, "subscriptions", subscription_id), operation))

    def set_subscription_payment_method(self, subscription_id: str, payment_method_id: str) -> dict:
        """修改订阅后续自动扣款使用的支付方式。"""
        def apply(s, outputs):
            sub = self.owned(s, "subscriptions", subscription_id)
            if sub["status"] == "cancelled" or not self.payment_method(s, self.actor_id, payment_method_id)["active"]:
                raise ValueError("Subscription or payment method is inactive")
            sub["payment_method_id"] = payment_method_id
            touch(sub, s["now"])
            return {"subscription": self.subscription_view(sub), "payment_method": self.method_view(self.payment_method(s, self.actor_id, payment_method_id))}
        return self.mutate("set_subscription_payment_method", locals_args(locals()), apply)

    def schedule_subscription_change(self, subscription_id: str, plan_id: str, quantity: int = 1, expected_version: int | None = None) -> dict:
        """保存下个账期生效的方案和数量，按当前方案条款固定新合同。"""
        def apply(s, outputs):
            sub = self.owned(s, "subscriptions", subscription_id)
            version(sub, expected_version)
            p = self.get(s, "plans", plan_id)
            if sub["status"] not in {"active", "trialing"} or p["merchant_id"] != sub["merchant_id"] or not p["active"] or p["currency"] != sub["contract"]["currency"]:
                raise ValueError("Subscription cannot switch to selected plan")
            sub["pending_change"] = {"plan_id": plan_id, "quantity": integer(quantity, 1, 1000), "contract": copy.deepcopy(p), "effective_at": sub["current_period_end"]}
            touch(sub, s["now"])
            return {"subscription": self.subscription_view(sub)}
        return self.mutate("schedule_subscription_change", locals_args(locals()), apply)

    def cancel_subscription_change(self, subscription_id: str) -> dict:
        """清除尚未生效的订阅方案变更。"""
        def apply(s, outputs):
            sub = self.owned(s, "subscriptions", subscription_id)
            sub["pending_change"] = None
            touch(sub, s["now"])
            return {"subscription": self.subscription_view(sub)}
        return self.mutate("cancel_subscription_change", {"subscription_id": subscription_id}, apply)

    def list_my_invoices(self, offset: int = 0, limit: int = 20) -> dict:
        """查询订阅应付账单，账单与税务发票分别保存。"""
        with self.session() as s:
            return page([v for v in s["invoices"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def pay_invoice(self, invoice_id: str, payment_method_id: str, idempotency_key: str) -> dict:
        """支付开放的订阅账单，成功后更新已付费访问周期。"""
        def apply(s, outputs):
            invoice = self.owned(s, "invoices", invoice_id)
            sub = self.owned(s, "subscriptions", invoice["subscription_id"])
            p = self.charge_invoice(s, sub, invoice, payment_method_id)
            return {"invoice": invoice, "payment": p, "subscription": self.subscription_view(sub)}
        return self.mutate("pay_invoice", locals_args(locals()), apply, idempotency_key)

    def save_billing_profile(self, legal_name: str, tax_id: str, address: str, email: str, profile_id: str | None = None, expected_version: int | None = None) -> dict:
        """新增或修改开票抬头、税号、地址和接收邮箱。"""
        def apply(s, outputs):
            for v in (legal_name, tax_id, address, email):
                text(v, 500)
            r = self.owned(s, "billing_profiles", profile_id) if profile_id else {"id": self.new_id(s, "billing_profiles", "bill"), "buyer_id": self.actor_id, "version": 0}
            version(r, expected_version)
            r.update(legal_name=legal_name, tax_id=tax_id, address=address, email=email)
            touch(r, s["now"])
            s["billing_profiles"][r["id"]] = r
            return {"billing_profile": r}
        return self.mutate("save_billing_profile", locals_args(locals()), apply)

    def list_billing_profiles(self, offset: int = 0, limit: int = 20) -> dict:
        """列出保存的开票资料。"""
        with self.session() as s:
            return page([v for v in s["billing_profiles"].values() if v["buyer_id"] == self.actor_id], offset, limit)

    def delete_billing_profile(self, profile_id: str) -> dict:
        """删除开票资料，既有申请保留原资料快照。"""
        def apply(s, outputs):
            self.owned(s, "billing_profiles", profile_id)
            del s["billing_profiles"][profile_id]
            return {"deleted_profile_id": profile_id}
        return self.mutate("delete_billing_profile", {"profile_id": profile_id}, apply)

    def request_tax_invoice(self, payment_id: str, profile_id: str) -> dict:
        """为成功支付申请税务发票，固定当次开票资料。"""
        def apply(s, outputs):
            p = self.owned(s, "payments", payment_id)
            profile = self.owned(s, "billing_profiles", profile_id)
            if p["status"] != "succeeded" or p["refunded_minor"] or any(v["payment_id"] == payment_id and v["status"] != "rejected" for v in s["tax_invoice_requests"].values()):
                raise ValueError("Payment is not eligible for a new invoice request")
            r = {"id": self.new_id(s, "tax_invoice_requests", "tax"), "buyer_id": self.actor_id, "merchant_id": p["merchant_id"], "payment_id": payment_id, "amount_minor": p["amount_minor"], "currency": p["currency"], "profile_snapshot": copy.deepcopy(profile), "status": "pending", "created_at": s["now"], "version": 1}
            s["tax_invoice_requests"][r["id"]] = r
            return {"tax_invoice_request": r}
        return self.mutate("request_tax_invoice", locals_args(locals()), apply)

    def list_my_tax_invoices(self, offset: int = 0, limit: int = 20) -> dict:
        """查询开票申请、已开票信息和处理状态。"""
        with self.session() as s:
            return page([{k: v for k, v in r.items() if k != "file_snapshot"} for r in s["tax_invoice_requests"].values() if r["buyer_id"] == self.actor_id], offset, limit)

    def download_tax_invoice(self, request_id: str, save_path: str) -> dict:
        """下载商家已开具的税务发票文件。"""
        def apply(s, outputs):
            r = self.owned(s, "tax_invoice_requests", request_id)
            if r["status"] != "issued":
                raise ValueError("Tax invoice is not issued")
            return {"file": self.save_output(outputs, save_path, base64.b64decode(r["file_snapshot"]["content_base64"], validate=True))}
        return self.mutate("download_tax_invoice", locals_args(locals()), apply)
