"""Host-side clock, payment-provider and carrier events. Not registered as MCP tools."""
import copy
from .core import CommerceStore, integer, moment, text, touch


def advance_state(store, s, as_of, merchant_id=None):
    deadline = moment(as_of)
    if deadline < moment(s["now"]):
        raise ValueError("Clock cannot move backwards")
    generated, expired, cancelled = [], [], []
    # Chronological event order makes large and small clock advances equivalent.
    for count in range(1001):
        due = []
        for o in s["orders"].values():
            if o["status"] == "pending_payment" and o.get("reservation_expires_at") and (merchant_id is None or o["merchant_id"] == merchant_id):
                due.append((moment(o["reservation_expires_at"]), "order", o["id"]))
        for sub in s["subscriptions"].values():
            if sub["status"] in {"active", "trialing"} and sub.get("current_period_end") and (merchant_id is None or sub["merchant_id"] == merchant_id):
                due.append((moment(sub["current_period_end"]), "subscription", sub["id"]))
        due = sorted(v for v in due if v[0] <= deadline)
        if not due:
            break
        if count == 1000:
            raise ValueError("More than 1000 due events; advance a shorter interval")
        at, kind, rid = due[0]
        # Already overdue fixtures are processed at the current time, never rewind.
        s["now"] = max(moment(s["now"]), at).isoformat()
        if kind == "order":
            o = s["orders"][rid]
            for p in s["payments"].values():
                if p.get("order_id") == rid and p["status"] == "pending":
                    p["status"] = "closed"
                    touch(p, s["now"])
                    s["payment_events"].append(copy.deepcopy(p))
            store.release_stock(s, o)
            o.update(status="cancelled", cancellation_reason="Payment reservation expired")
            touch(o, s["now"])
            expired.append(rid)
        else:
            sub = s["subscriptions"][rid]
            if sub["cancel_at_period_end"]:
                store.change_subscription(s, sub, "cancel_now")
                cancelled.append(rid)
                continue
            if sub.get("pending_change"):
                change = sub.pop("pending_change")
                sub.update(plan_id=change["plan_id"], contract=change["contract"], quantity=change["quantity"], pending_change=None)
            invoice = store.invoice(s, sub, sub["current_period_end"])
            payment = store.charge_invoice(s, sub, invoice, sub["payment_method_id"])
            generated.append({"invoice": invoice, "payment": payment})
    s["now"] = deadline.isoformat()
    for delivery in s["deliveries"].values():
        if delivery["status"] == "active" and delivery.get("expires_at") and moment(delivery["expires_at"]) <= deadline:
            delivery["status"] = "expired"
            touch(delivery, s["now"])
    return {"as_of": s["now"], "generated": generated, "expired_orders": expired, "cancelled_subscriptions": cancelled}


class CommerceEnvironment(CommerceStore):
    """The evaluator uses this class; agents receive buyer/merchant catalogs only."""
    role = "buyer"

    def advance_time(self, as_of):
        return self.mutate("environment.advance_time", {"as_of": as_of}, lambda s, outputs: advance_state(self, s, as_of))

    def issue_payment_token(self, buyer_id, label, outcome="succeeded", expires_at=None):
        def apply(s, outputs):
            self.get(s, "buyers", buyer_id)
            if outcome not in {"succeeded", "declined", "pending"}:
                raise ValueError("Invalid provider outcome")
            if expires_at:
                moment(expires_at)
            token = {"id": self.new_id(s, "payment_tokens", "tok"), "buyer_id": buyer_id, "label": text(label, 200), "outcome": outcome, "expires_at": expires_at, "consumed": False, "version": 1}
            s["payment_tokens"][token["id"]] = token
            return {"payment_token": token["id"]}
        return self.mutate("environment.issue_payment_token", {"buyer_id": buyer_id, "label": label, "outcome": outcome, "expires_at": expires_at}, apply)

    def record_payment_result(self, payment_id, status):
        def apply(s, outputs):
            p = self.get(s, "payments", payment_id)
            if p["status"] != "pending" or status not in {"succeeded", "declined", "closed"}:
                raise ValueError("Only pending payments accept final provider results")
            p["status"] = status
            touch(p, s["now"])
            self.apply_payment(s, p)
            s["payment_events"].append(copy.deepcopy(p))
            return {"payment": p}
        return self.mutate("environment.record_payment_result", {"payment_id": payment_id, "status": status}, apply)

    def record_refund_result(self, refund_id, succeeded):
        def apply(s, outputs):
            r = self.get(s, "refunds", refund_id)
            if type(succeeded) is not bool:
                raise ValueError("succeeded must be boolean")
            self.complete_refund(s, r, succeeded)
            return {"refund": r}
        return self.mutate("environment.record_refund_result", {"refund_id": refund_id, "succeeded": succeeded}, apply)

    def record_shipment_event(self, shipment_id, status, description):
        def apply(s, outputs):
            v = self.get(s, "shipments", shipment_id)
            allowed = {"shipped": {"in_transit", "delivered", "exception"}, "in_transit": {"in_transit", "delivered", "exception"}, "exception": {"in_transit", "delivered", "exception"}}
            if status not in allowed.get(v["status"], set()):
                raise ValueError("Invalid carrier transition")
            v["status"] = status
            v["events"].append({"status": status, "description": text(description), "at": s["now"]})
            if status == "delivered":
                v["delivered_at"] = s["now"]
            touch(v, s["now"])
            return {"shipment": v}
        return self.mutate("environment.record_shipment_event", {"shipment_id": shipment_id, "status": status, "description": description}, apply)
