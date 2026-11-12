"""Shared role-bound commerce storage, migration and durable operation evidence."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from contextlib import contextmanager

from filelock import FileLock
from .common import integer, moment, text

COLLECTIONS = ("merchants", "buyers", "products", "skus", "carts", "orders", "payments", "refunds",
               "refund_requests", "plans", "subscriptions", "invoices", "addresses", "favorites", "quotes",
               "shipping_options", "discounts", "cancellation_requests", "shipments", "aftersales", "deliveries",
               "billing_profiles", "tax_invoice_requests", "payment_tokens")


class Storage:
    role = None

    def __init__(self, run_root, actor_id=None):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.files = self.workspace
        self.service = self.root / "services/commerce"
        self.state_path = self.service / "state.json"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.service.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.service / "state.lock"), timeout=20)
        with self.lock:
            s = self.load(self.state_path)
            self.normalize(s)
            self.actor_id = actor_id or s["current_merchant" if self.role == "merchant" else "current_buyer"]
            self.actor(s)
            self.validate(s)
            self.atomic_json(self.state_path, s)

    @staticmethod
    def load(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def normalize(s):
        for key in COLLECTIONS:
            s.setdefault(key, {})
        for key, default in {"counters": {}, "idempotency": {}, "sequence": 0, "mutation_events": [],
                             "subscription_events": [], "payment_events": [], "refund_events": [], "download_events": []}.items():
            s.setdefault(key, default)
        for key in COLLECTIONS:
            for obj in s[key].values():
                obj.setdefault("version", 1)
        for b in s["buyers"].values():
            b.setdefault("payment_methods", [])
            b.setdefault("default_address_id", None)
            b.setdefault("default_payment_method_id", b["payment_methods"][0]["id"] if b["payment_methods"] else None)
            for m in b["payment_methods"]:
                m.setdefault("active", True)
                m.setdefault("version", 1)
        for p in s["products"].values():
            p.setdefault("category", "")
            p.setdefault("policies", {"returnable": True, "exchangeable": True, "return_days": 30, "cancellation_allowed": True, "terms": "", "delivery_countries": []})
            p.setdefault("description", "")
            if p["id"] not in s["skus"]:
                s["skus"][p["id"]] = {"id": p["id"], "product_id": p["id"], "merchant_id": p["merchant_id"],
                                        "options": {}, "unit_amount_minor": p["unit_amount_minor"], "stock": p["stock"],
                                        "active": p["active"], "currency": p["currency"], "version": p["version"], "default": True}
        for merchant in s["merchants"].values():
            mid = merchant["id"]
            key = "shipping_" + mid
            if key not in s["shipping_options"]:
                s["shipping_options"][key] = {"id": key, "merchant_id": mid, "name": "Standard", "amount_minor": merchant.get("shipping_minor", 0),
                                              "countries": [], "min_days": 3, "max_days": 7, "active": True, "version": 1, "default": True}
        for c in s["carts"].values():
            for item in c["items"]:
                item.setdefault("sku_id", item.get("product_id"))
                item.setdefault("product_id", s["skus"][item["sku_id"]]["product_id"])
        for o in s["orders"].values():
            o.setdefault("discount_minor", 0)
            o.setdefault("tax_minor", 0)
            o.setdefault("subtotal_minor", sum(i["unit_amount_minor"]*i["quantity"] for i in o["items"]))
            o.setdefault("reservation_expires_at", None)
            o.setdefault("note", "")
            o.setdefault("discount_allocations", [])
            for index, item in enumerate(o["items"]):
                item.setdefault("line_id", o["id"] + "_line_" + str(index+1))
                item.setdefault("sku_id", item["product_id"])
                item.setdefault("fulfilled_quantity", item["quantity"] if o["fulfillment_status"] == "fulfilled" else 0)
                item.setdefault("policies", copy.deepcopy(item.get("product_snapshot", {}).get("policies", s["products"][item["product_id"]]["policies"])))
            if o.get("shipment") and not any(sh["order_id"] == o["id"] for sh in s["shipments"].values()):
                shid = "shipment_" + o["id"]
                s["shipments"][shid] = {"id": shid, "order_id": o["id"], "buyer_id": o["buyer_id"], "merchant_id": o["merchant_id"],
                                         "items": [{"line_id": i["line_id"], "quantity": i["quantity"]} for i in o["items"] if i["kind"] == "physical"],
                                         "carrier": o["shipment"]["carrier"], "tracking_number": o["shipment"]["tracking_number"],
                                         "status": "shipped", "events": [], "version": 1, "shipped_at": o["shipment"]["fulfilled_at"], "buyer_confirmed_at": None}
        for sub in s["subscriptions"].values():
            sub.setdefault("contract", copy.deepcopy(s["plans"][sub["plan_id"]]))
            sub.setdefault("pending_change", None)
            sub.setdefault("trial_end", None)
            sub.setdefault("access_until", sub.get("current_period_end"))
        for r in s["refunds"].values():
            r.setdefault("status", "succeeded")
        for method in (m for b in s["buyers"].values() for m in b["payment_methods"]):
            method.setdefault("outcome", "declined")
        s["commerce_model_version"] = 2

    @staticmethod
    def validate(s):
        moment(s["now"])
        for key in COLLECTIONS:
            if len(s[key]) > 10000:
                raise ValueError("Collection exceeds 10000 resources")
            for rid, v in s[key].items():
                if v["id"] != rid or not re.fullmatch(r"[A-Za-z0-9_-]{1,140}", rid):
                    raise ValueError("Invalid resource ID")
                for field, collection in (("buyer_id", "buyers"), ("merchant_id", "merchants")):
                    if field in v and v[field] not in s[collection]:
                        raise ValueError("Invalid ownership reference")
                if "currency" in v and v["currency"] not in {"CNY", "USD", "EUR"}:
                    raise ValueError("Unsupported currency")
        for p in s["products"].values():
            text(p["name"], 200)
            if p["kind"] not in {"physical", "digital", "service"}:
                raise ValueError("Invalid product kind")
        for sku in s["skus"].values():
            p = s["products"].get(sku["product_id"])
            if not p or p["merchant_id"] != sku["merchant_id"] or sku["currency"] != p["currency"]:
                raise ValueError("Invalid SKU product")
            integer(sku["stock"], 0, 1000000)
            integer(sku["unit_amount_minor"], 1)
        for o in s["orders"].values():
            total = sum(i["unit_amount_minor"]*i["quantity"] for i in o["items"])+o["shipping_minor"]+o["tax_minor"]-o["discount_minor"]
            if o["total_minor"] != total or total < 0:
                raise ValueError("Order money mismatch")
            if len({i["line_id"] for i in o["items"]}) != len(o["items"]):
                raise ValueError("Duplicate order lines")
            for i in o["items"]:
                integer(i["quantity"], 1, 1000)
                integer(i["fulfilled_quantity"], 0, i["quantity"])
            captured = [p for p in s["payments"].values() if p.get("order_id") == o["id"] and p["status"] == "succeeded"]
            if len(captured) > 1 or captured and captured[0]["amount_minor"] != o["total_minor"]:
                raise ValueError("Order payment mismatch")
        for p in s["payments"].values():
            integer(p["amount_minor"])
            if p["status"] not in {"pending", "succeeded", "declined", "closed"}:
                raise ValueError("Invalid payment status")
            targets = [s[name].get(p[field]) for name, field in (("orders", "order_id"), ("invoices", "invoice_id")) if p.get(field)]
            if len(targets) != 1 or targets[0] is None or any(targets[0][k] != p[k] for k in ("buyer_id", "merchant_id", "currency")):
                raise ValueError("Invalid payment target")
            refunds = sum(r["amount_minor"] for r in s["refunds"].values() if r["payment_id"] == p["id"] and r["status"] == "succeeded")
            reserved = sum(r["amount_minor"] for r in s["refunds"].values() if r["payment_id"] == p["id"] and r["status"] == "pending")
            requested = sum(r["amount_minor"] for r in s["refund_requests"].values() if r["payment_id"] == p["id"] and r["status"] == "pending")
            if refunds != p["refunded_minor"] or refunds+reserved+requested > p["amount_minor"]:
                raise ValueError("Refund ledger exceeds captured funds")
        for sub in s["subscriptions"].values():
            if sub["plan_id"] not in s["plans"] or sub["contract"]["merchant_id"] != sub["merchant_id"]:
                raise ValueError("Invalid subscription contract")
        for inv in s["invoices"].values():
            sub = s["subscriptions"].get(inv["subscription_id"])
            if not sub or any(inv[k] != sub[k] for k in ("buyer_id", "merchant_id")) or inv["currency"] != sub["contract"]["currency"]:
                raise ValueError("Invalid invoice contract")
            integer(inv["amount_minor"])
            captured = [p for p in s["payments"].values() if p.get("invoice_id") == inv["id"] and p["status"] == "succeeded"]
            if len(captured) > 1 or captured and captured[0]["amount_minor"] != inv["amount_minor"]:
                raise ValueError("Invoice payment mismatch")
        for key in ("shipments", "deliveries", "aftersales", "cancellation_requests"):
            for record in s[key].values():
                order = s["orders"].get(record["order_id"])
                if not order or any(record[k] != order[k] for k in ("buyer_id", "merchant_id")):
                    raise ValueError("Invalid order-linked resource")
        for refund in s["refunds"].values():
            payment = s["payments"].get(refund["payment_id"])
            if not payment or any(payment[k] != refund[k] for k in ("buyer_id", "merchant_id", "currency")) or refund["status"] not in {"pending", "succeeded", "failed"}:
                raise ValueError("Invalid refund transaction")
            integer(refund["amount_minor"], 1)
        for b in s["buyers"].values():
            mids = [m["id"] for m in b["payment_methods"]]
            if len(mids) != len(set(mids)):
                raise ValueError("Duplicate payment method IDs")
            if any(m["outcome"] not in {"succeeded", "declined", "pending"} for m in b["payment_methods"]):
                raise ValueError("Invalid payment provider outcome")

    @staticmethod
    def atomic_bytes(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def atomic_json(path, data):
        Storage.atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode())

    @contextmanager
    def session(self):
        with self.lock:
            s = self.load(self.state_path)
            self.actor(s)
            yield s

    def actor(self, s):
        return self.get(s, "merchants" if self.role == "merchant" else "buyers", self.actor_id)

    @staticmethod
    def get(s, collection, rid):
        if rid not in s[collection]:
            raise ValueError("Unknown " + collection + " ID")
        return s[collection][rid]

    def owned(self, s, collection, rid):
        obj = self.get(s, collection, rid)
        if obj.get("merchant_id" if self.role == "merchant" else "buyer_id") != self.actor_id:
            raise PermissionError("Resource is outside the bound account")
        return obj

    @staticmethod
    def new_id(s, collection, prefix):
        count = s["counters"].get(collection, 0)
        while True:
            count += 1
            rid = f"{prefix}_{count:06d}"
            if rid not in s[collection]:
                s["counters"][collection] = count
                return rid

    def mutate(self, action, arguments, handler, idempotency_key=None):
        with self.session() as original:
            s = copy.deepcopy(original)
            fingerprint = hashlib.sha256(json.dumps(arguments, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
            cache_key = None
            if idempotency_key is not None:
                if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key):
                    raise ValueError("Use a 1..128 character idempotency key")
                cache_key = "/".join((self.role, self.actor_id, action, idempotency_key))
                prior = s["idempotency"].get(cache_key)
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise ValueError("Idempotency key reused with different arguments")
                    return {**copy.deepcopy(prior["result"]), "replayed": True}
            outputs = {}
            result = handler(s, outputs)
            self.normalize(s)
            self.validate(s)
            s["sequence"] += 1
            result = {**copy.deepcopy(result), "sequence": s["sequence"], "replayed": False}
            if cache_key:
                s["idempotency"][cache_key] = {"fingerprint": fingerprint, "result": copy.deepcopy(result)}
            s["mutation_events"].append({"sequence": s["sequence"], "at": s["now"], "role": self.role, "actor_id": self.actor_id,
                                          "action": action, "arguments": copy.deepcopy(arguments), "result": copy.deepcopy(result),
                                          "products": copy.deepcopy(s["products"]), "orders": copy.deepcopy(s["orders"]), "payments": copy.deepcopy(s["payments"])})
            for path, raw in outputs.items():
                self.atomic_bytes(self.safe_output(path), base64.b64decode(raw, validate=True))
            self.atomic_json(self.state_path, s)
            return result

    def safe_output(self, value):
        root = self.workspace
        p = Path(value)
        p = p if p.is_absolute() else root / p
        cursor = root
        for part in p.absolute().relative_to(root).parts:
            cursor /= part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()) or (cursor.is_file() and cursor.stat().st_nlink > 1):
                raise ValueError("Links are not supported")
        p = p.resolve()
        if not p.is_relative_to(root) or p == root:
            raise ValueError("File must stay inside workspace")
        return p

    def save_output(self, outputs, path, data):
        target = self.safe_output(path)
        if target.exists():
            raise FileExistsError(str(target))
        outputs[str(target)] = base64.b64encode(data).decode()
        return {"path": str(target), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def file_snapshot(self, path):
        target = self.safe_output(path)
        if target.stat().st_size > 25*1024*1024:
            raise ValueError("File exceeds 25 MiB")
        raw = target.read_bytes()
        return {"name": target.name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "content_base64": base64.b64encode(raw).decode()}
