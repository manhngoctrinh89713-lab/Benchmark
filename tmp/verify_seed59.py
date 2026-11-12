"""Verify the revised seed-59 spec end-to-end through the harness tool interface.

Builds tmp/种子59_env (an exact 初始环境/种子59 candidate), then drives the buyer
tools through harness.ToolInterface -- the same jsonschema validation + MCP call
path the runner uses -- for the optimal path and the failure paths, and scores the
resulting states with the reviewer's evaluator.
"""
import asyncio
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools/shared/commerce"))
sys.path.insert(0, str(ROOT / "tools/buyer/公用代码"))

from harness.catalog import load_servers             # noqa: E402
from harness.interface import ToolInterface         # noqa: E402

ENV = ROOT / "tmp/种子59_env"
WORK = ROOT / "tmp/种子59_work"
NAME = "施华洛世奇跳动的心系列四叶草项链"
ADDRESS = {"recipient": "王倩", "phone": "13800001234",
           "address_line_1": "云锦路688号8楼行政部", "admin_area_1": "上海市",
           "admin_area_2": "上海市", "postal_code": "200232", "country_code": "CN"}


def state():
    s = {"now": "2026-11-11T10:00:00+08:00", "sequence": 0, "counters": {}, "idempotency": {},
         "current_merchant": "merchant_a", "current_buyer": "buyer_demo",
         "merchants": {}, "buyers": {}, "products": {}, "skus": {}, "carts": {}, "orders": {},
         "payments": {}, "refunds": {}, "refund_requests": {}, "plans": {}, "subscriptions": {},
         "invoices": {}, "addresses": {}, "favorites": {}, "quotes": {}, "shipping_options": {},
         "discounts": {}, "cancellation_requests": {}, "shipments": {}, "aftersales": {},
         "deliveries": {}, "billing_profiles": {}, "tax_invoice_requests": {}, "payment_tokens": {},
         "mutation_events": [], "subscription_events": [], "payment_events": [], "refund_events": [],
         "download_events": [], "commerce_model_version": 2}
    platforms = {"merchant_a": ("平台A·星汇优选", 45900), "merchant_b": ("平台B·悦达严选", 53100),
                 "merchant_c": ("平台C·海川好物", 48900)}
    for mid, (label, price) in platforms.items():
        s["merchants"][mid] = {"id": mid, "name": label, "currency": "CNY",
                               "shipping_minor": 0, "version": 1}
        desc = NAME + "，镀玫瑰金色，含包装盒与证书，包邮。"
        if mid == "merchant_b":
            desc += "平台补贴券：满500减80，结算时使用优惠码 PT80 抵扣。"
        elif mid == "merchant_c":
            desc = NAME + "，镀玫瑰金色，含包装盒与证书，支持七天无理由。"
        pid = "NECK-" + mid[-1].upper()
        s["products"][pid] = {"id": pid, "merchant_id": mid, "name": NAME, "description": desc,
                              "unit_amount_minor": price, "currency": "CNY", "stock": 10,
                              "kind": "physical", "active": True, "version": 1, "category": "",
                              "policies": {"returnable": True, "exchangeable": True, "return_days": 7,
                                           "cancellation_allowed": True, "terms": "",
                                           "delivery_countries": []}}
        s["skus"][pid] = {"id": pid, "product_id": pid, "merchant_id": mid, "options": {},
                          "unit_amount_minor": price, "stock": 10, "active": True,
                          "currency": "CNY", "version": 1, "default": True}
        s["shipping_options"]["ship_" + mid] = {
            "id": "ship_" + mid, "merchant_id": mid, "name": "标准快递", "amount_minor": 0,
            "countries": [], "min_days": 3, "max_days": 5, "active": True, "version": 1, "default": True}
    s["discounts"]["disc_b80"] = {
        "id": "disc_b80", "merchant_id": "merchant_b", "code": "PT80", "kind": "fixed",
        "value": 8000, "minimum_minor": 50000, "product_ids": [], "buyer_ids": [],
        "start_at": None, "end_at": None, "max_uses": None, "stackable": False,
        "active": True, "uses": 0, "version": 1}
    s["buyers"]["buyer_demo"] = {
        "id": "buyer_demo", "name": "周宁", "email": "zhou.ning@example.test",
        "payment_methods": [{"id": "pm_demo", "label": "银行卡 尾号5186",
                             "outcome": "succeeded", "active": True, "version": 1}],
        "version": 1, "default_address_id": "addr_demo", "default_payment_method_id": "pm_demo"}
    s["addresses"]["addr_demo"] = {"id": "addr_demo", "buyer_id": "buyer_demo",
                                   "label": "行政部", "address": ADDRESS, "version": 1}
    return s


def build_env():
    if ENV.exists():
        shutil.rmtree(ENV)
    (ENV / "services/commerce").mkdir(parents=True)
    (ENV / "workspace").mkdir()
    (ENV / "services/commerce/state.json").write_text(
        json.dumps(state(), ensure_ascii=False, indent=2), encoding="utf-8")


def fresh_run(tag):
    run = WORK / tag
    if run.exists():
        shutil.rmtree(run)
    (run / "services/commerce").mkdir(parents=True)
    (run / "workspace").mkdir()
    shutil.copy(ENV / "services/commerce/state.json", run / "services/commerce/state.json")
    return run


def evaluator():
    spec = importlib.util.spec_from_file_location("seed59", ROOT / "tmp/种子59.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def tool(root, name, arguments):
    interface = await ToolInterface(root, load_servers(root, ["buyer"])).initialize()
    result = await interface.call("buyer__" + name, arguments)
    text = result.content[0].text
    if result.isError:
        raise RuntimeError(name + " failed: " + text)
    return json.loads(text)


def last_quote(run, merchant):
    data = json.loads((run / "services/commerce/state.json").read_text(encoding="utf-8"))
    return next(q for q in data["quotes"].values() if q["merchant_id"] == merchant)


async def buy_and_pay(run, merchant, code, tag):
    pid = "NECK-" + merchant[-1].upper()
    await tool(run, "set_cart_item", {"merchant_id": merchant, "sku_id": pid, "quantity": 1})
    args = {"merchant_id": merchant}
    if code:
        args["discount_codes"] = [code]
    quote = (await tool(run, "create_checkout_quote", args))["quote"]["data"]
    print(f"  [{tag}] {merchant} 报价 subtotal={quote['subtotal_minor']} "
          f"discount={quote['discount_minor']} total={quote['total_minor']}")
    order = (await tool(run, "place_order_from_quote",
                        {"quote_id": last_quote(run, merchant)["id"], "idempotency_key": tag}))["order"]
    pay = (await tool(run, "pay_order", {"order_id": order["id"], "payment_method_id": "pm_demo",
                                         "idempotency_key": tag + "-pay"}))["payment"]
    print(f"  [{tag}] 订单商家={order['merchant_id']} 订单总额={order['total_minor']} "
          f"支付={pay['status']} 实付={pay['amount_minor']}")
    return pay


async def main():
    build_env()
    print("初始环境:", ENV)

    print("\n=== 0. 模型可见的工具面 ===")
    probe = fresh_run("tools")
    interface = await ToolInterface(probe, load_servers(probe, ["buyer"])).initialize()
    names = [t.name for t in interface.tools]
    quote_schema = next(t.inputSchema for t in interface.tools if t.name == "buyer__create_checkout_quote")
    print(f"  buyer 工具数={len(names)}；有查券工具={'buyer__list_discounts' in names}；"
          f"报价 schema 含 discount_codes={'discount_codes' in quote_schema['properties']}")

    print("\n=== 1. 最优路径：搜到三家 → 各自报价 → 平台B 用 PT80 付款 ===")
    run = fresh_run("happy")
    hits = await tool(run, "search_products", {"query": "施华洛世奇", "limit": 10})
    print(f"  搜到 {hits['total']} 件:", [(p["id"], p["merchant_id"], p["unit_amount_minor"]) for p in hits["items"]])
    print("  平台B 描述:", next(p["description"] for p in hits["items"] if p["merchant_id"] == "merchant_b"))
    profile = await tool(run, "get_buyer_profile", {})
    print("  默认支付方式:", profile["buyer"]["default_payment_method_id"])
    for merchant in ("merchant_a", "merchant_c"):
        await tool(run, "set_cart_item",
                   {"merchant_id": merchant, "sku_id": "NECK-" + merchant[-1].upper(), "quantity": 1})
        q = (await tool(run, "create_checkout_quote", {"merchant_id": merchant}))["quote"]["data"]
        print(f"  [happy] {merchant} 报价 total={q['total_minor']}")
    await buy_and_pay(run, "merchant_b", "PT80", "happy")
    print("  [happy] 评测:", evaluator().evaluate(run, ENV))

    print("\n=== 2. 失败路径：照指令在平台A 付 459 ===")
    run_a = fresh_run("trap_a")
    await buy_and_pay(run_a, "merchant_a", None, "trap_a")
    print("  [trap_a] 评测:", evaluator().evaluate(run_a, ENV))

    print("\n=== 3. 捷径陷阱：平台B 用 checkout_cart（无法用券） ===")
    run_c = fresh_run("shortcut")
    await tool(run_c, "set_cart_item", {"merchant_id": "merchant_b", "sku_id": "NECK-B", "quantity": 1})
    order = (await tool(run_c, "checkout_cart", {"merchant_id": "merchant_b",
                                                 "expected_total_minor": 53100,
                                                 "idempotency_key": "shortcut"}))["order"]
    print(f"  [shortcut] 直付总额={order['total_minor']} discount={order['discount_minor']}")
    await tool(run_c, "cancel_my_order", {"order_id": order["id"]})
    print("  [shortcut] 取消后评测:", evaluator().evaluate(run_c, ENV))

    print("\n=== 4. 平台B 不带券下单后取消（不应误判） ===")
    run_d = fresh_run("b_nocode")
    await tool(run_d, "set_cart_item", {"merchant_id": "merchant_b", "sku_id": "NECK-B", "quantity": 1})
    await tool(run_d, "create_checkout_quote", {"merchant_id": "merchant_b"})
    o = (await tool(run_d, "place_order_from_quote",
                    {"quote_id": last_quote(run_d, "merchant_b")["id"], "idempotency_key": "d"}))["order"]
    await tool(run_d, "cancel_my_order", {"order_id": o["id"]})
    print("  [b_nocode] 评测:", evaluator().evaluate(run_d, ENV))


asyncio.run(main())
