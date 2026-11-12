"""Shared SKU pricing, inventory, payment/refund and subscription semantics."""
import copy
import hashlib
import json
import re
from datetime import timedelta

from .common import integer, moment, period_end, text, touch


class Engine:
    @staticmethod
    def payment_method(s, buyer_id, method_id):
        method = next((m for m in s["buyers"][buyer_id]["payment_methods"] if m["id"] == method_id), None)
        if method is None:
            raise PermissionError("Payment method is not owned by buyer")
        return method

    @staticmethod
    def method_view(m):
        return {k: copy.deepcopy(m[k]) for k in ("id", "label", "active", "version")}

    @staticmethod
    def address_check(address):
        allowed = {"recipient", "phone", "address_line_1", "address_line_2", "admin_area_1", "admin_area_2", "postal_code", "country_code"}
        if not isinstance(address, dict) or set(address)-allowed or not {"address_line_1", "country_code"} <= set(address):
            raise ValueError("Address requires address_line_1/country_code and supported fields")
        for value in address.values():
            text(value, 300)
        if not re.fullmatch(r"[A-Z]{2}", address["country_code"]):
            raise ValueError("country_code must be two uppercase letters")
        return copy.deepcopy(address)

    def product_view(self, s, product):
        fields = ("id", "merchant_id", "name", "description", "kind", "currency", "category", "policies", "active", "version")
        result = {k: copy.deepcopy(product[k]) for k in fields}
        variants = [{k: copy.deepcopy(v[k]) for k in ("id", "options", "unit_amount_minor", "stock", "active", "version")}
                    for v in s["skus"].values() if v["product_id"] == product["id"]]
        result["variants"] = variants
        live = [v for v in variants if v["active"]]
        result["unit_amount_minor"] = min((v["unit_amount_minor"] for v in live), default=product["unit_amount_minor"])
        result["stock"] = sum(v["stock"] for v in live)
        return result

    def stock_change(self, s, sku_id, delta):
        sku = self.get(s, "skus", sku_id)
        sku["stock"] = integer(sku["stock"]+delta, 0, 1000000)
        touch(sku, s["now"])
        if sku.get("default"):
            p = s["products"][sku["product_id"]]
            p["stock"] = sku["stock"]
            touch(p, s["now"])

    def cart_view(self, s, merchant_id, buyer_id=None):
        buyer_id = buyer_id or self.actor_id
        merchant = self.get(s, "merchants", merchant_id)
        cid = buyer_id+"__"+merchant_id
        cart = s["carts"].get(cid, {"id": cid, "buyer_id": buyer_id, "merchant_id": merchant_id, "items": [], "version": 0})
        items = []
        for line in cart["items"]:
            sku = self.get(s, "skus", line["sku_id"])
            product = self.get(s, "products", sku["product_id"])
            items.append({**copy.deepcopy(line), "name": product["name"], "kind": product["kind"], "options": copy.deepcopy(sku["options"]),
                          "unit_amount_minor": sku["unit_amount_minor"], "available": product["active"] and sku["active"] and sku["stock"] >= line["quantity"],
                          "sku_version": sku["version"], "product_version": product["version"]})
        subtotal = sum(i["quantity"]*i["unit_amount_minor"] for i in items)
        shipping = merchant.get("shipping_minor", 0) if any(i["kind"] == "physical" for i in items) else 0
        return {**copy.deepcopy(cart), "items": items, "currency": merchant["currency"], "subtotal_minor": subtotal,
                "shipping_minor": shipping, "total_minor": subtotal+shipping, "available": all(i["available"] for i in items)}

    def quote_cart(self, s, merchant_id, sku_ids=None, shipping_address=None, address_id=None,
                   shipping_option_id=None, discount_codes=None, delivery_email=None):
        cart = self.cart_view(s, merchant_id)
        chosen = cart["items"] if sku_ids is None else [i for i in cart["items"] if i["sku_id"] in sku_ids]
        if not chosen or sku_ids is not None and (len(set(sku_ids)) != len(sku_ids) or {i["sku_id"] for i in chosen} != set(sku_ids)):
            raise ValueError("Select nonempty unique cart SKU IDs")
        if not all(i["available"] for i in chosen):
            raise ValueError("Selected products are unavailable or insufficient")
        if address_id and shipping_address is not None:
            raise ValueError("Select address_id or inline shipping_address")
        if address_id:
            record = self.owned(s, "addresses", address_id)
            shipping_address = record["address"]
        physical = any(i["kind"] == "physical" for i in chosen)
        address = self.address_check(shipping_address) if physical else None
        if not physical and (address_id or shipping_address is not None or shipping_option_id):
            raise ValueError("Nonphysical-only purchases do not use shipping")
        shipping, option = 0, None
        if physical:
            options = [v for v in s["shipping_options"].values() if v["merchant_id"] == merchant_id and v["active"] and (not v["countries"] or address["country_code"] in v["countries"])]
            option = next((v for v in options if v["id"] == shipping_option_id), None) if shipping_option_id else next((v for v in options if v.get("default")), None)
            if option is None:
                raise ValueError("Choose an available shipping option")
            shipping = option["amount_minor"]
        lines = []
        for i in chosen:
            p = s["products"][i["product_id"]]
            countries = p["policies"].get("delivery_countries", [])
            if physical and countries and address["country_code"] not in countries:
                raise ValueError("Product does not support selected destination")
            lines.append({**i, "policies": copy.deepcopy(p["policies"]), "product_snapshot": self.product_view(s, p)})
        if delivery_email is not None and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", delivery_email):
            raise ValueError("Invalid delivery_email")
        if any(i["kind"] != "physical" for i in chosen):
            delivery_email = delivery_email or s["buyers"][self.actor_id].get("email")
            if not delivery_email:
                raise ValueError("Nonphysical delivery needs an email")
        subtotal = sum(i["quantity"]*i["unit_amount_minor"] for i in lines)
        codes = discount_codes or []
        if len(codes) > 2 or len({v.casefold() for v in codes}) != len(codes):
            raise ValueError("Use at most two unique discount codes")
        discounts, total_discount = [], 0
        for code in codes:
            d = next((d for d in s["discounts"].values() if d["merchant_id"] == merchant_id and d["code"].casefold() == code.casefold()), None)
            if not d or not d["active"] or d.get("start_at") and moment(s["now"]) < moment(d["start_at"]) or d.get("end_at") and moment(s["now"]) >= moment(d["end_at"]):
                raise ValueError("Discount is unavailable")
            if subtotal < d["minimum_minor"] or d.get("buyer_ids") and self.actor_id not in d["buyer_ids"]:
                raise ValueError("Discount is inapplicable")
            if len(codes) > 1 and not d["stackable"]:
                raise ValueError("Discount cannot be combined")
            if d.get("max_uses") is not None and d.get("uses", 0) >= d["max_uses"]:
                raise ValueError("Discount use limit reached")
            eligible = [i for i in lines if not d["product_ids"] or i["product_id"] in d["product_ids"]]
            base = sum(i["quantity"]*i["unit_amount_minor"] for i in eligible)
            if not base:
                raise ValueError("No selected item qualifies for discount")
            amount = d["value"] if d["kind"] == "fixed" else base*d["value"]//10000
            amount = min(amount, base, subtotal-total_discount)
            remaining = amount
            capacity = sum(i["quantity"]*i["unit_amount_minor"]-i.get("discount_minor", 0) for i in eligible)
            amount = min(amount, capacity)
            remaining = amount
            for index, line in enumerate(eligible):
                available = line["quantity"]*line["unit_amount_minor"]-line.get("discount_minor", 0)
                allocated = remaining if index == len(eligible)-1 else amount*available//capacity if capacity else 0
                line["discount_minor"] = line.get("discount_minor", 0)+allocated
                remaining -= allocated
            total_discount += amount
            discounts.append({"id": d["id"], "code": d["code"], "version": d["version"], "amount_minor": amount})
        tax = (subtotal-total_discount)*integer(s["merchants"][merchant_id].get("tax_basis_points", 0), 0, 10000)//10000
        remaining_tax = tax
        net = subtotal-total_discount
        for index, line in enumerate(lines):
            base = line["quantity"]*line["unit_amount_minor"]-line.get("discount_minor", 0)
            line["tax_minor"] = remaining_tax if index == len(lines)-1 else tax*base//net if net else 0
            remaining_tax -= line["tax_minor"]
        integer(subtotal+shipping+tax-total_discount)
        return {"merchant_id": merchant_id, "buyer_id": self.actor_id, "cart_id": cart["id"], "cart_version": cart["version"],
                "items": lines, "currency": cart["currency"], "subtotal_minor": subtotal, "shipping_minor": shipping,
                "discount_minor": total_discount, "discount_allocations": discounts, "tax_minor": tax,
                "total_minor": subtotal+shipping+tax-total_discount, "shipping_address": address,
                "shipping_option": copy.deepcopy(option), "delivery_email": delivery_email,
                "request": {"sku_ids": [i["sku_id"] for i in lines], "shipping_address": address,
                            "shipping_option_id": option["id"] if option else None, "discount_codes": codes, "delivery_email": delivery_email}}

    @staticmethod
    def quote_fingerprint(quote):
        return hashlib.sha256(json.dumps(quote, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def place_order(self, s, quote, note=""):
        oid = self.new_id(s, "orders", "ord")
        order = {k: copy.deepcopy(quote[k]) for k in ("buyer_id", "merchant_id", "currency", "items", "subtotal_minor", "shipping_minor", "tax_minor", "discount_minor", "discount_allocations", "total_minor", "shipping_address", "shipping_option", "delivery_email")}
        order.update(id=oid, status="pending_payment", payment_status="unpaid", fulfillment_status="unfulfilled", stock_released=False,
                     version=1, note=note, created_at=s["now"], reservation_expires_at=(moment(s["now"])+timedelta(minutes=30)).isoformat())
        for index, line in enumerate(order["items"]):
            line.update(line_id=oid+"_line_"+str(index+1), fulfilled_quantity=0)
            self.stock_change(s, line["sku_id"], -line["quantity"])
        for allocation in order["discount_allocations"]:
            d = s["discounts"][allocation["id"]]
            d["uses"] = d.get("uses", 0)+1
            touch(d, s["now"])
        s["orders"][oid] = order
        cart = s["carts"][quote["cart_id"]]
        cart["items"] = [i for i in cart["items"] if i["sku_id"] not in {v["sku_id"] for v in order["items"]}]
        touch(cart, s["now"])
        return order

    def release_stock(self, s, order):
        if not order["stock_released"]:
            for line in order["items"]:
                self.stock_change(s, line["sku_id"], line["quantity"]-line["fulfilled_quantity"])
            order["stock_released"] = True

    def cancel_order(self, s, order, reason):
        text(reason)
        if order["status"] != "pending_payment" or any(p.get("order_id") == order["id"] and p["status"] == "pending" for p in s["payments"].values()):
            raise ValueError("Only unpaid orders without pending payments can be cancelled directly")
        self.release_stock(s, order)
        order.update(status="cancelled", cancellation_reason=reason)
        touch(order, s["now"])
        return {"order": order}

    def charge(self, s, buyer_id, merchant_id, amount, currency, method_id, **target):
        integer(amount)
        method = self.payment_method(s, buyer_id, method_id) if amount else None
        status = method.get("outcome", "declined") if method and method["active"] else "declined" if amount else "succeeded"
        p = {"id": self.new_id(s, "payments", "pay"), "buyer_id": buyer_id, "merchant_id": merchant_id,
             "amount_minor": amount, "currency": currency, "status": status, "method_label": method["label"] if method else "No charge",
             "refunded_minor": 0, "created_at": s["now"], "version": 1, **target}
        s["payments"][p["id"]] = p
        s["payment_events"].append(copy.deepcopy(p))
        return p

    def apply_payment(self, s, payment):
        if payment["status"] != "succeeded":
            return
        if payment.get("order_id"):
            o = s["orders"][payment["order_id"]]
            if o["status"] != "pending_payment":
                raise ValueError("Order no longer accepts payment")
            o.update(status="paid", payment_status="paid")
            touch(o, s["now"])
        else:
            invoice = s["invoices"][payment["invoice_id"]]
            sub = s["subscriptions"][invoice["subscription_id"]]
            if invoice["status"] != "open" or sub["status"] == "cancelled":
                raise ValueError("Invoice no longer accepts payment")
            invoice.update(status="paid", payment_id=payment["id"])
            sub.update(status="active", current_period_start=invoice["period_start"], current_period_end=invoice["period_end"], access_until=invoice["period_end"])
            touch(invoice, s["now"])
            touch(sub, s["now"])

    def refundable(self, s, payment, excluding_request=None):
        committed = sum(r["amount_minor"] for r in s["refunds"].values() if r["payment_id"] == payment["id"] and r["status"] in {"pending", "succeeded"})
        requested = sum(r["amount_minor"] for r in s["refund_requests"].values() if r["payment_id"] == payment["id"] and r["status"] == "pending" and r["id"] != excluding_request)
        return payment["amount_minor"]-committed-requested

    def refund(self, s, payment, amount, reason, approved_request_id=None):
        if payment["status"] != "succeeded" or integer(amount, 1) > self.refundable(s, payment, approved_request_id):
            raise ValueError("Refund exceeds available captured funds")
        text(reason)
        refund = {"id": self.new_id(s, "refunds", "rf"), "buyer_id": payment["buyer_id"], "merchant_id": payment["merchant_id"],
                  "payment_id": payment["id"], "amount_minor": amount, "currency": payment["currency"], "reason": reason,
                  "status": "pending", "created_at": s["now"], "version": 1}
        s["refunds"][refund["id"]] = refund
        s["refund_events"].append(copy.deepcopy(refund))
        return refund

    def complete_refund(self, s, refund, succeeded):
        if refund["status"] != "pending":
            raise ValueError("Refund is already final")
        refund["status"] = "succeeded" if succeeded else "failed"
        refund["completed_at"] = s["now"]
        touch(refund, s["now"])
        p = s["payments"][refund["payment_id"]]
        if succeeded:
            p["refunded_minor"] += refund["amount_minor"]
            touch(p, s["now"])
            if p.get("order_id"):
                o = s["orders"][p["order_id"]]
                full = p["refunded_minor"] == p["amount_minor"]
                o["payment_status"] = "refunded" if full else "partially_refunded"
                if full and o["status"] != "cancelled":
                    o["status"] = "refunded"
                    if o["fulfillment_status"] == "unfulfilled":
                        self.release_stock(s, o)
                if full:
                    for delivery in s["deliveries"].values():
                        if delivery["order_id"] == o["id"] and delivery["status"] == "active":
                            delivery.update(status="revoked", revocation_reason="Order fully refunded", revoked_at=s["now"])
                            touch(delivery, s["now"])
                touch(o, s["now"])
        s["refund_events"].append(copy.deepcopy(refund))

    def invoice(self, s, sub, start):
        contract = sub["contract"]
        invoice = {"id": self.new_id(s, "invoices", "inv"), "buyer_id": sub["buyer_id"], "merchant_id": sub["merchant_id"],
                   "subscription_id": sub["id"], "currency": contract["currency"], "amount_minor": contract["unit_amount_minor"]*sub["quantity"],
                   "status": "open", "period_start": start, "period_end": period_end(start, contract["interval"], contract["interval_count"], sub.get("billing_anchor_day")),
                   "payment_id": None, "contract_snapshot": copy.deepcopy(contract), "version": 1}
        s["invoices"][invoice["id"]] = invoice
        return invoice

    def charge_invoice(self, s, sub, invoice, method_id):
        if invoice["status"] != "open" or sub["status"] == "cancelled" or any(p.get("invoice_id") == invoice["id"] and p["status"] == "pending" for p in s["payments"].values()):
            raise ValueError("Invoice is not payable or payment is pending")
        p = self.charge(s, sub["buyer_id"], sub["merchant_id"], invoice["amount_minor"], invoice["currency"], method_id, invoice_id=invoice["id"])
        if p["status"] == "succeeded":
            sub["payment_method_id"] = method_id
            self.apply_payment(s, p)
        else:
            sub["status"] = "past_due" if sub["current_period_end"] else "incomplete"
            touch(sub, s["now"])
        return p

    @staticmethod
    def subscription_view(sub):
        return {k: copy.deepcopy(v) for k, v in sub.items() if k != "payment_method_id"}

    def change_subscription(self, s, sub, operation):
        if sub["status"] == "cancelled":
            raise ValueError("Cancelled subscription requires a new purchase")
        if any(p["status"] == "pending" and p.get("invoice_id") in {i["id"] for i in s["invoices"].values() if i["subscription_id"] == sub["id"]} for p in s["payments"].values()):
            raise ValueError("Resolve pending payment before changing subscription")
        if operation == "cancel_now":
            sub.update(status="cancelled", cancel_at_period_end=False, access_until=s["now"], cancelled_at=s["now"], pending_change=None)
            for invoice in s["invoices"].values():
                if invoice["subscription_id"] == sub["id"] and invoice["status"] == "open":
                    invoice["status"] = "void"
                    touch(invoice, s["now"])
        elif operation == "cancel_at_period_end":
            if sub["status"] not in {"active", "trialing"}:
                raise ValueError("Period-end cancellation requires an active or trial subscription")
            sub["cancel_at_period_end"] = True
        elif operation == "resume":
            if not sub["cancel_at_period_end"]:
                raise ValueError("Only a pending period-end cancellation can be resumed")
            sub["cancel_at_period_end"] = False
        else:
            raise ValueError("operation: cancel_now/cancel_at_period_end/resume")
        touch(sub, s["now"])
        s["subscription_events"].append({"subscription_id": sub["id"], "operation": operation, "timestamp": s["now"]})
        return {"subscription": self.subscription_view(sub)}
