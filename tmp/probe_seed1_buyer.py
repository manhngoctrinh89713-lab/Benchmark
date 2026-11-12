"""Feasibility probe: can the existing buyer suite express the docx seed-1 scenario?

Builds a throwaway run_root (three "platforms" as merchants, one identical necklace,
platform B with a 500-80 fixed discount), drives BuyerStore directly and prints the
observable results an agent / evaluator would see.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/shared/commerce"))
sys.path.insert(0, str(ROOT / "tools/buyer/公用代码"))

from local_buyer.backend import BuyerStore  # noqa: E402

RUN = ROOT / "tmp/probe_seed1_run"
if RUN.exists():
    shutil.rmtree(RUN)
(RUN / "services/commerce").mkdir(parents=True)

base = json.loads((ROOT / "初始环境/种子18/services/commerce/state.json").read_text(encoding="utf-8"))

NAME = "施华洛世奇跳动的心系列四叶草项链"
PLATFORMS = {
    "merchant_a": ("星汇优选", 45900),
    "merchant_b": ("悦达严选", 53100),
    "merchant_c": ("海川好物", 48900),
}
base["merchants"] = {}
base["products"] = {}
base["skus"] = {}
base["carts"] = {}
base["discounts"] = {}
base["shipping_options"] = {}
for mid, (label, price) in PLATFORMS.items():
    base["merchants"][mid] = {"id": mid, "name": label, "currency": "CNY", "shipping_minor": 0, "version": 1}
    desc = "施华洛世奇跳动的心系列四叶草项链，镀玫瑰金色，含包装盒与证书。"
    if mid == "merchant_b":
        desc += " 平台大额补贴：满500减80，结算时使用优惠码 B80 抵扣，平台自动核销。"
    elif mid == "merchant_c":
        desc += " 全新正品，支持七天无理由。"
    pid = "NECK-" + mid[-1].upper()
    base["products"][pid] = {
        "id": pid, "merchant_id": mid, "name": NAME, "description": desc,
        "unit_amount_minor": price, "currency": "CNY", "stock": 10, "kind": "physical",
        "active": True, "version": 1, "category": "",
        "policies": {"returnable": True, "exchangeable": True, "return_days": 7,
                     "cancellation_allowed": True, "terms": "", "delivery_countries": []},
    }
    base["skus"][pid] = {"id": pid, "product_id": pid, "merchant_id": mid, "options": {},
                         "unit_amount_minor": price, "stock": 10, "active": True,
                         "currency": "CNY", "version": 1, "default": True}
    base["shipping_options"]["ship_" + mid] = {
        "id": "ship_" + mid, "merchant_id": mid, "name": "标准快递", "amount_minor": 0,
        "countries": [], "min_days": 3, "max_days": 5, "active": True, "version": 1, "default": True,
    }

base["discounts"]["disc_b80"] = {
    "id": "disc_b80", "merchant_id": "merchant_b", "code": "B80", "kind": "fixed",
    "value": 8000, "minimum_minor": 50000, "product_ids": [], "buyer_ids": [],
    "start_at": None, "end_at": None, "max_uses": None, "stackable": False,
    "active": True, "uses": 0, "version": 1,
}

(RUN / "services/commerce/state.json").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")

store = BuyerStore(RUN)

print("=== 1. 买家可见的发现面 ===")
hits = store.search_products(query="施华洛世奇", limit=10)
for p in hits["items"]:
    print(f"  {p['id']:8s} {p['merchant_id']:11s} 标价={p['unit_amount_minor']:6d}  {p['name']}")
print("  B 描述里是否带补贴信息:", "满500减80" in [p for p in hits["items"] if p["merchant_id"] == "merchant_b"][0]["description"])
print("  买家是否有 list_discounts 能力:", hasattr(store, "list_discounts"))
print("  list_merchants 返回字段:", sorted(store.list_merchants()["items"][0].keys()))

print("\n=== 2. 结算必须带地址（实物） ===")
addr = store.save_address("家", {"recipient": "张三", "phone": "13800000000",
                                 "address_line_1": "云锦路688号", "admin_area_2": "上海",
                                 "postal_code": "200232", "country_code": "CN"}, make_default=True)
print("  默认地址:", store.get_buyer_profile()["buyer"]["default_address_id"])

print("\n=== 3. 平台A：459，无券 ===")
store.set_cart_item("merchant_a", "NECK-A", 1)
qa = store.create_checkout_quote("merchant_a")["quote"]
print(f"  A 报价 subtotal={qa['data']['subtotal_minor']} discount={qa['data']['discount_minor']} total={qa['data']['total_minor']}")

print("\n=== 4. 平台B：531，带满500减80 ===")
store.set_cart_item("merchant_b", "NECK-B", 1)
qb_nocode = store.create_checkout_quote("merchant_b")["quote"]
print(f"  B 不填码 subtotal={qb_nocode['data']['subtotal_minor']} discount={qb_nocode['data']['discount_minor']} total={qb_nocode['data']['total_minor']}")
qb = store.create_checkout_quote("merchant_b", discount_codes=["B80"])["quote"]
print(f"  B 填 B80  subtotal={qb['data']['subtotal_minor']} discount={qb['data']['discount_minor']} total={qb['data']['total_minor']}")
print("  优惠分摊:", qb["data"]["discount_allocations"])

print("\n=== 5. 下单并支付 B，核对实付金额与订单商家 ===")
order = store.place_order_from_quote(qb["id"], "idem-b-1")["order"]
print(f"  订单 {order['id']} merchant={order['merchant_id']} total={order['total_minor']} status={order['status']}")
pay = store.pay_order(order["id"], "pm_demo", "idem-b-pay")
print(f"  支付 status={pay['payment']['status']} amount_minor={pay['payment']['amount_minor']}")
print("  订单终态:", store.get_my_order(order["id"])["order"]["payment_status"], store.get_my_order(order["id"])["order"]["status"])

print("\n=== 6. 判分可读字段 ===")
state = json.loads((RUN / "services/commerce/state.json").read_text(encoding="utf-8"))
for pid, p in state["payments"].items():
    o = state["orders"].get(p.get("order_id"), {})
    print(f"  payment {pid} amount={p['amount_minor']} order={p.get('order_id')} merchant={o.get('merchant_id')} total={o.get('total_minor')}")

print("\n=== 7. 若改在A付款（失败路径） ===")
order_a = store.place_order_from_quote(qa["id"], "idem-a-1")["order"]
pay_a = store.pay_order(order_a["id"], "pm_demo", "idem-a-pay")
print(f"  A 实付={pay_a['payment']['amount_minor']}  B 实付=45100  差额={45900-45100}")

