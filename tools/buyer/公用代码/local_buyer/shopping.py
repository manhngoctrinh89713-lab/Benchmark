"""Discovery, saved products, carts and frozen checkout quotes."""
import copy
from datetime import timedelta

from local_commerce.core import integer, moment, page, text, touch, version
from local_commerce.types import Address, CartLine
from .accounts import locals_args


class Shopping:
    def list_merchants(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        """按名称查询商家及其货币、配送和公开信息。"""
        with self.session() as s:
            return page([{k: m[k] for k in ("id", "name", "currency", "shipping_minor") if k in m} for m in s["merchants"].values() if query.casefold() in m["name"].casefold()], offset, limit)

    def list_product_categories(self, merchant_id: str | None = None) -> dict:
        """列出在售商品的分类。"""
        with self.session() as s:
            return {"categories": sorted({p["category"] for p in s["products"].values() if p["active"] and (merchant_id is None or p["merchant_id"] == merchant_id)})}

    def search_products(self, query: str = "", merchant_id: str | None = None, category: str | None = None, kind: str | None = None, min_price_minor: int | None = None, max_price_minor: int | None = None, in_stock: bool = False, sort_by: str = "name", descending: bool = False, offset: int = 0, limit: int = 20) -> dict:
        """按商家、分类、类型、价格和库存组合查询在售商品，支持排序与分页。"""
        with self.session() as s:
            rows = [self.product_view(s, p) for p in s["products"].values() if p["active"] and query.casefold() in (p["name"]+"\n"+p["description"]).casefold() and (merchant_id is None or p["merchant_id"] == merchant_id) and (category is None or p["category"] == category) and (kind is None or p["kind"] == kind)]
            rows = [p for p in rows if (min_price_minor is None or p["unit_amount_minor"] >= integer(min_price_minor)) and (max_price_minor is None or p["unit_amount_minor"] <= integer(max_price_minor)) and (not in_stock or p["stock"] > 0)]
            if sort_by not in {"name", "unit_amount_minor", "id"}:
                raise ValueError("sort_by: name/unit_amount_minor/id")
            return page(sorted(rows, key=lambda p: (p[sort_by], p["id"]), reverse=descending), offset, limit)

    def get_product(self, product_id: str) -> dict:
        """读取商品当前规格、价格、库存和销售退换政策。"""
        with self.session() as s:
            return {"product": self.product_view(s, self.get(s, "products", product_id))}

    def list_shipping_options(self, merchant_id: str, country_code: str | None = None) -> dict:
        """列出商家当前可用的配送方式、费用和预计时效。"""
        with self.session() as s:
            self.get(s, "merchants", merchant_id)
            return {"shipping_options": [v for v in s["shipping_options"].values() if v["merchant_id"] == merchant_id and v["active"] and (country_code is None or not v["countries"] or country_code in v["countries"])]}

    def save_favorite(self, product_id: str, saved: bool = True) -> dict:
        """收藏或取消收藏商品。"""
        def apply(s, outputs):
            self.get(s, "products", product_id)
            fid = self.actor_id+"__"+product_id
            if saved:
                s["favorites"][fid] = {"id": fid, "buyer_id": self.actor_id, "product_id": product_id, "version": 1}
            else:
                s["favorites"].pop(fid, None)
            return {"product_id": product_id, "saved": saved}
        return self.mutate("save_favorite", locals_args(locals()), apply)

    def list_favorites(self, offset: int = 0, limit: int = 20) -> dict:
        """列出收藏商品及其当前销售状态。"""
        with self.session() as s:
            return page([self.product_view(s, s["products"][f["product_id"]]) for f in s["favorites"].values() if f["buyer_id"] == self.actor_id], offset, limit)

    def get_cart(self, merchant_id: str) -> dict:
        """读取商家购物车，以当前价格和库存计算商品金额。"""
        with self.session() as s:
            return {"cart": self.cart_view(s, merchant_id)}

    def update_cart(self, merchant_id: str, items: list[CartLine], expected_version: int | None = None) -> dict:
        """替换购物车商品列表；每项指定 SKU 或商品默认规格及数量，空列表清空。"""
        def apply(s, outputs):
            self.get(s, "merchants", merchant_id)
            if len(items) > 50:
                raise ValueError("Cart accepts at most 50 lines")
            cid = self.actor_id+"__"+merchant_id
            cart = s["carts"].get(cid, {"id": cid, "buyer_id": self.actor_id, "merchant_id": merchant_id, "version": 0})
            version(cart, expected_version)
            lines, seen = [], set()
            for item in items:
                sid = item.get("sku_id") or item.get("product_id")
                sku = self.get(s, "skus", sid)
                p = s["products"][sku["product_id"]]
                if sid in seen or p["merchant_id"] != merchant_id or item.get("product_id", p["id"]) != p["id"] or not p["active"] or not sku["active"]:
                    raise ValueError("Use unique available SKUs from this merchant")
                seen.add(sid)
                lines.append({"sku_id": sid, "product_id": p["id"], "quantity": integer(item["quantity"], 1, 1000)})
            cart["items"] = lines
            touch(cart, s["now"])
            s["carts"][cid] = cart
            return {"cart": self.cart_view(s, merchant_id)}
        return self.mutate("update_cart", locals_args(locals()), apply)

    def set_cart_item(self, merchant_id: str, sku_id: str, quantity: int, expected_version: int | None = None) -> dict:
        """增加或修改一个购物车规格的数量，零表示移除。"""
        # One locked mutation keeps read-modify-write atomic.
        def apply(s, outputs):
            sku = self.get(s, "skus", sku_id)
            p = s["products"][sku["product_id"]]
            integer(quantity, 0, 1000)
            if p["merchant_id"] != merchant_id or quantity and (not p["active"] or not sku["active"]):
                raise ValueError("SKU is unavailable")
            cid = self.actor_id+"__"+merchant_id
            cart = s["carts"].setdefault(cid, {"id": cid, "buyer_id": self.actor_id, "merchant_id": merchant_id, "version": 0, "items": []})
            version(cart, expected_version)
            cart["items"] = [v for v in cart["items"] if v["sku_id"] != sku_id]
            if quantity:
                cart["items"].append({"sku_id": sku_id, "product_id": p["id"], "quantity": quantity})
            if len(cart["items"]) > 50:
                raise ValueError("Cart accepts at most 50 lines")
            touch(cart, s["now"])
            return {"cart": self.cart_view(s, merchant_id)}
        return self.mutate("set_cart_item", locals_args(locals()), apply)

    def create_checkout_quote(self, merchant_id: str, sku_ids: list[str] | None = None, shipping_address: Address | None = None, address_id: str | None = None, shipping_option_id: str | None = None, discount_codes: list[str] | None = None, delivery_email: str | None = None) -> dict:
        """保存选定购物车商品的结算报价，有效期十五分钟，不预留库存。"""
        def apply(s, outputs):
            selected_address = address_id
            if selected_address is None and shipping_address is None and any(i["kind"] == "physical" for i in self.cart_view(s, merchant_id)["items"] if sku_ids is None or i["sku_id"] in sku_ids):
                selected_address = self.actor(s).get("default_address_id")
            data = self.quote_cart(s, merchant_id, sku_ids, shipping_address, selected_address, shipping_option_id, discount_codes, delivery_email)
            quote = {"id": self.new_id(s, "quotes", "quote"), "buyer_id": self.actor_id, "merchant_id": merchant_id, "version": 1, "data": data, "created_at": s["now"], "expires_at": (moment(s["now"])+timedelta(minutes=15)).isoformat(), "status": "open"}
            s["quotes"][quote["id"]] = quote
            return {"quote": quote}
        return self.mutate("create_checkout_quote", locals_args(locals()), apply)

    def get_checkout_quote(self, quote_id: str) -> dict:
        """读取已保存的结算条件和报价有效期。"""
        with self.session() as s:
            quote = self.owned(s, "quotes", quote_id)
            return {"quote": quote, "expired": moment(s["now"]) >= moment(quote["expires_at"]), "as_of": s["now"]}

    def place_order_from_quote(self, quote_id: str, idempotency_key: str, note: str = "") -> dict:
        """按报价创建待付款订单；重新核对价格、库存、政策和优惠后预留库存三十分钟。"""
        def apply(s, outputs):
            q = self.owned(s, "quotes", quote_id)
            if q["status"] != "open" or moment(s["now"]) >= moment(q["expires_at"]):
                raise ValueError("Quote is no longer open")
            current = self.quote_cart(s, q["merchant_id"], **q["data"]["request"])
            if self.quote_fingerprint(current) != self.quote_fingerprint(q["data"]):
                raise ValueError("Checkout conditions changed; request a new quote")
            if note:
                text(note)
            order = self.place_order(s, current, note)
            q.update(status="ordered", order_id=order["id"])
            touch(q, s["now"])
            return {"order": order}
        return self.mutate("place_order_from_quote", locals_args(locals()), apply, idempotency_key)

    def checkout_cart(self, merchant_id: str, expected_total_minor: int, idempotency_key: str, shipping_address: Address | None = None) -> dict:
        """按当前默认配送条件直接创建待付款订单，并核对预期总额。"""
        def apply(s, outputs):
            q = self.quote_cart(s, merchant_id, shipping_address=shipping_address, address_id=self.actor(s).get("default_address_id") if shipping_address is None and any(i["kind"] == "physical" for i in self.cart_view(s, merchant_id)["items"]) else None)
            if integer(expected_total_minor) != q["total_minor"]:
                raise ValueError("Cart total changed")
            return {"order": self.place_order(s, q)}
        return self.mutate("checkout_cart", locals_args(locals()), apply, idempotency_key)
