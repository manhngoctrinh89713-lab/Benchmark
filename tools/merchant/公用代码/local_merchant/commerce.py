"""SKU catalog, shipping offers and promotions."""
import copy
from local_commerce.core import integer, moment, page, period_end, text, touch, version
from local_commerce.types import SalePolicy


def arguments(values):
    return {k: copy.deepcopy(v) for k, v in values.items() if k not in {"self", "apply"}}


class Catalog:
    def list_products(self, include_inactive: bool = True, offset: int = 0, limit: int = 20) -> dict:
        """查询商家商品及规格、库存、价格和销售政策。"""
        with self.session() as s:
            return page([self.product_view(s, p) for p in s["products"].values() if p["merchant_id"] == self.actor_id and (include_inactive or p["active"])], offset, limit)

    def create_product(self, name: str, unit_amount_minor: int, stock: int, kind: str = "physical", description: str = "", category: str = "", policies: SalePolicy | None = None) -> dict:
        """创建商品及默认规格，支持实物、数字商品和服务。"""
        def apply(s, outputs):
            if kind not in {"physical", "digital", "service"} or len(description) > 2000 or len(category) > 200:
                raise ValueError("Invalid product fields")
            policy = self.check_policy(policies or {})
            p = {"id": self.new_id(s, "products", "prod"), "merchant_id": self.actor_id, "name": text(name, 200), "unit_amount_minor": integer(unit_amount_minor, 1), "stock": integer(stock, 0, 1000000), "currency": self.actor(s)["currency"], "kind": kind, "description": description, "category": category, "policies": policy, "active": True, "version": 1}
            s["products"][p["id"]] = p
            s["skus"][p["id"]] = {"id": p["id"], "product_id": p["id"], "merchant_id": self.actor_id, "options": {}, "unit_amount_minor": unit_amount_minor, "stock": stock, "currency": p["currency"], "active": True, "default": True, "version": 1}
            return {"product": self.product_view(s, p)}
        return self.mutate("create_product", arguments(locals()), apply)

    @staticmethod
    def check_policy(policy):
        result = {"returnable": True, "exchangeable": True, "return_days": 30, "cancellation_allowed": True, "terms": "", "delivery_countries": [], **policy}
        integer(result["return_days"], 0, 365)
        if len(result["terms"]) > 4000 or any(len(c) != 2 or not c.isupper() or not c.isalpha() for c in result["delivery_countries"]):
            raise ValueError("Invalid sales policy")
        return result

    def update_product(self, product_id: str, name: str | None = None, description: str | None = None, unit_amount_minor: int | None = None, active: bool | None = None, category: str | None = None, policies: SalePolicy | None = None, expected_version: int | None = None) -> dict:
        """修改商品资料和销售政策；价格参数修改默认规格，已有订单保留成交快照。"""
        def apply(s, outputs):
            p = self.owned(s, "products", product_id)
            version(p, expected_version)
            if name is not None:
                p["name"] = text(name, 200)
            if description is not None:
                if len(description) > 2000:
                    raise ValueError("Description too long")
                p["description"] = description
            if category is not None:
                if len(category) > 200:
                    raise ValueError("Category too long")
                p["category"] = category
            if policies is not None:
                p["policies"] = self.check_policy({**p["policies"], **policies})
            if active is not None:
                p["active"] = active
            if unit_amount_minor is not None:
                p["unit_amount_minor"] = integer(unit_amount_minor, 1)
                s["skus"][product_id]["unit_amount_minor"] = unit_amount_minor
                touch(s["skus"][product_id], s["now"])
            touch(p, s["now"])
            return {"product": self.product_view(s, p)}
        return self.mutate("update_product", arguments(locals()), apply)

    def create_sku(self, product_id: str, options: dict[str, str], unit_amount_minor: int, stock: int) -> dict:
        """为商品增加独立定价和库存的规格。"""
        def apply(s, outputs):
            p = self.owned(s, "products", product_id)
            self.check_options(options)
            if any(v["product_id"] == product_id and v["options"] == options for v in s["skus"].values()):
                raise ValueError("SKU options already exist")
            v = {"id": self.new_id(s, "skus", "sku"), "merchant_id": self.actor_id, "product_id": product_id, "options": copy.deepcopy(options), "unit_amount_minor": integer(unit_amount_minor, 1), "stock": integer(stock, 0, 1000000), "currency": p["currency"], "active": True, "default": False, "version": 1}
            s["skus"][v["id"]] = v
            touch(p, s["now"])
            return {"sku": v}
        return self.mutate("create_sku", arguments(locals()), apply)

    @staticmethod
    def check_options(options):
        if not options or len(options) > 10:
            raise ValueError("SKU requires 1..10 named options")
        for k, v in options.items():
            text(k, 100)
            text(v, 100)

    def update_sku(self, sku_id: str, unit_amount_minor: int | None = None, active: bool | None = None, expected_version: int | None = None) -> dict:
        """修改规格的售价或上架状态。"""
        def apply(s, outputs):
            v = self.owned(s, "skus", sku_id)
            version(v, expected_version)
            if unit_amount_minor is not None:
                v["unit_amount_minor"] = integer(unit_amount_minor, 1)
                if v.get("default"):
                    s["products"][v["product_id"]]["unit_amount_minor"] = unit_amount_minor
            if active is not None:
                v["active"] = active
            touch(v, s["now"])
            touch(s["products"][v["product_id"]], s["now"])
            return {"sku": v}
        return self.mutate("update_sku", arguments(locals()), apply)

    def adjust_inventory(self, product_id: str, delta: int) -> dict:
        """增减商品默认规格的可售库存。"""
        def apply(s, outputs):
            self.owned(s, "products", product_id)
            self.stock_change(s, product_id, integer(delta, -1000000, 1000000))
            return {"product": self.product_view(s, s["products"][product_id])}
        return self.mutate("adjust_inventory", arguments(locals()), apply)

    def adjust_sku_inventory(self, sku_id: str, delta: int, expected_version: int | None = None) -> dict:
        """增减指定规格的可售库存，已下单库存另行保留。"""
        def apply(s, outputs):
            v = self.owned(s, "skus", sku_id)
            version(v, expected_version)
            self.stock_change(s, sku_id, integer(delta, -1000000, 1000000))
            return {"sku": v}
        return self.mutate("adjust_sku_inventory", arguments(locals()), apply)

    def save_shipping_option(self, name: str, amount_minor: int, countries: list[str], min_days: int, max_days: int, option_id: str | None = None, active: bool = True, make_default: bool = False) -> dict:
        """新增或修改配送方式、适用国家、费用和预计工作日时效。"""
        def apply(s, outputs):
            if any(len(c) != 2 or not c.isupper() or not c.isalpha() for c in countries):
                raise ValueError("Use two-letter country codes")
            integer(min_days, 0, 365)
            integer(max_days, min_days, 365)
            v = self.owned(s, "shipping_options", option_id) if option_id else {"id": self.new_id(s, "shipping_options", "shipopt"), "merchant_id": self.actor_id, "version": 0, "default": False}
            if make_default:
                for old in s["shipping_options"].values():
                    if old["merchant_id"] == self.actor_id and old.get("default"):
                        old["default"] = False
                        touch(old, s["now"])
                v["default"] = True
                self.actor(s)["shipping_minor"] = amount_minor
            v.update(name=text(name, 200), amount_minor=integer(amount_minor), countries=copy.deepcopy(countries), min_days=min_days, max_days=max_days, active=active)
            if v.get("default"):
                self.actor(s)["shipping_minor"] = amount_minor
                touch(self.actor(s), s["now"])
            touch(v, s["now"])
            s["shipping_options"][v["id"]] = v
            return {"shipping_option": v}
        return self.mutate("save_shipping_option", arguments(locals()), apply)

    def list_shipping_options(self) -> dict:
        """列出商家的全部配送方案。"""
        with self.session() as s:
            return {"shipping_options": [v for v in s["shipping_options"].values() if v["merchant_id"] == self.actor_id]}

    def save_discount(self, code: str, kind: str, value: int, minimum_minor: int = 0, product_ids: list[str] | None = None, buyer_ids: list[str] | None = None, start_at: str | None = None, end_at: str | None = None, max_uses: int | None = None, stackable: bool = False, active: bool = True, discount_id: str | None = None) -> dict:
        """维护固定金额或折扣比例优惠，含门槛、商品、客户、时间、次数及叠加条件。比例以万分比填写。"""
        def apply(s, outputs):
            if kind not in {"fixed", "proportion"}:
                raise ValueError("kind: fixed/proportion")
            text(code, 100)
            integer(value, 1, 10000 if kind == "proportion" else 1000000000000)
            integer(minimum_minor)
            if start_at:
                moment(start_at)
            if end_at:
                moment(end_at)
            if start_at and end_at and moment(start_at) >= moment(end_at):
                raise ValueError("Discount end must follow start")
            for pid in product_ids or []:
                self.owned(s, "products", pid)
            for bid in buyer_ids or []:
                self.get(s, "buyers", bid)
            if max_uses is not None:
                integer(max_uses, 1, 1000000)
            d = self.owned(s, "discounts", discount_id) if discount_id else {"id": self.new_id(s, "discounts", "disc"), "merchant_id": self.actor_id, "uses": 0, "version": 0}
            if any(v["merchant_id"] == self.actor_id and v["id"] != d["id"] and v["code"].casefold() == code.casefold() for v in s["discounts"].values()):
                raise ValueError("Discount code already exists")
            d.update(code=code, kind=kind, value=value, minimum_minor=minimum_minor, product_ids=product_ids or [], buyer_ids=buyer_ids or [], start_at=start_at, end_at=end_at, max_uses=max_uses, stackable=stackable, active=active)
            touch(d, s["now"])
            s["discounts"][d["id"]] = d
            return {"discount": d}
        return self.mutate("save_discount", arguments(locals()), apply)

    def list_discounts(self, offset: int = 0, limit: int = 20) -> dict:
        """查询商家优惠规则及累计使用次数。"""
        with self.session() as s:
            return page([d for d in s["discounts"].values() if d["merchant_id"] == self.actor_id], offset, limit)

    def create_subscription_plan(self, name: str, unit_amount_minor: int, interval: str = "month", interval_count: int = 1, trial_days: int = 0, terms: str = "") -> dict:
        """创建订阅方案，配置价格、账期、试用天数和条款。"""
        def apply(s, outputs):
            period_end(s["now"], interval, integer(interval_count, 1, 120))
            if len(terms) > 4000:
                raise ValueError("Terms too long")
            p = {"id": self.new_id(s, "plans", "plan"), "merchant_id": self.actor_id, "name": text(name, 200), "unit_amount_minor": integer(unit_amount_minor, 1), "currency": self.actor(s)["currency"], "interval": interval, "interval_count": interval_count, "trial_days": integer(trial_days, 0, 365), "terms": terms, "active": True, "version": 1}
            s["plans"][p["id"]] = p
            return {"plan": p}
        return self.mutate("create_subscription_plan", arguments(locals()), apply)

    def update_subscription_plan(self, plan_id: str, name: str | None = None, active: bool | None = None, unit_amount_minor: int | None = None, trial_days: int | None = None, terms: str | None = None, expected_version: int | None = None) -> dict:
        """更新对外销售方案，已订阅合同继续使用购买时条款。"""
        def apply(s, outputs):
            p = self.owned(s, "plans", plan_id)
            version(p, expected_version)
            if name is not None:
                p["name"] = text(name, 200)
            if active is not None:
                p["active"] = active
            if unit_amount_minor is not None:
                p["unit_amount_minor"] = integer(unit_amount_minor, 1)
            if trial_days is not None:
                p["trial_days"] = integer(trial_days, 0, 365)
            if terms is not None:
                if len(terms) > 4000:
                    raise ValueError("Terms too long")
                p["terms"] = terms
            touch(p, s["now"])
            return {"plan": p}
        return self.mutate("update_subscription_plan", arguments(locals()), apply)
