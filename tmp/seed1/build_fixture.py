"""Build the temporary seed-1 fixture (three merchants, one chair model, one coupon)."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / "tmp/seed1/初始环境"
NAME = "人体工学电脑椅 家用办公椅 护腰可躺"
ADDRESS = {"recipient": "王倩", "phone": "13800001234",
           "address_line_1": "云锦路688号8楼行政部", "admin_area_1": "上海市",
           "admin_area_2": "上海市", "postal_code": "200232", "country_code": "CN"}

DESCRIPTIONS = {
    "merchant_a": (
        "【久坐办公首选】双背分区支撑，自适应腰托跟着坐姿贴合腰椎；靠背加宽到 52cm，双层透气网布，"
        "夏天久坐也不闷汗。4D 扶手可上下、前后、左右调节，打字、开会、午休都能找到合适位置。"
        "坐垫是高回弹定型海绵，边缘做过圆角处理，久坐不压腿。椅背最大后仰 135°，支持无级锁定；"
        "三级认证气压棒，加厚五星脚，承重标称 150kg。整椅含头枕、腰托和伸缩脚踏，安装工具与图文说明书"
        "随箱发出，一般 30 分钟能装好。本店页面价即到手价，不参加平台跨店满减，也没有额外店铺券。"
    ),
    "merchant_b": (
        "【官方旗舰款】同型号人体工学电脑椅，整椅通过 BIFMA 耐久测试：加厚钢板底盘、铝合金扶手骨架、"
        "三级认证气压棒。靠背用韩国进口高弹网布，透气与回弹兼顾；坐深可前后调节 5cm，"
        "身高 160–190cm 都能坐满大腿。头枕可升降旋转，午休后仰时能托住颈部；扶手面是亲肤软胶，"
        "长时间搁手不发麻。整椅五年质保，部分城市支持免费上门安装。11 月平台大促进行中："
        "平台补贴券满 1000 减 500，结算时在优惠码一栏填 PT500 即可抵扣，每个账号限用一张，"
        "不与其他满减叠加。整装加固包装发出，运输破损包赔。"
    ),
    "merchant_c": (
        "【授权经销】同型号人体工学电脑椅，配置与官方一致，原厂整箱发货，附安装工具和说明书。"
        "靠背网布、腰托、4D 扶手、135° 后仰、伸缩脚踏都齐全；三级气压棒，五星脚为加厚尼龙。"
        "支持 7 天无理由退换，运费险已含。本周活动：下单随椅赠送记忆棉腰靠一只，晒单再返 10 元红包。"
        "页面价 1349 元，可直接下单。"
    ),
}

PLATFORMS = {"merchant_a": ("平台A·星汇优选", 119900), "merchant_b": ("平台B·悦达严选", 149900),
             "merchant_c": ("平台C·海川好物", 134900)}


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
    for mid, (label, price) in PLATFORMS.items():
        s["merchants"][mid] = {"id": mid, "name": label, "currency": "CNY",
                               "shipping_minor": 0, "version": 1}
        pid = "CHAIR-" + mid[-1].upper()
        s["products"][pid] = {"id": pid, "merchant_id": mid, "name": NAME,
                              "description": DESCRIPTIONS[mid], "unit_amount_minor": price,
                              "currency": "CNY", "stock": 5, "kind": "physical", "active": True,
                              "version": 1, "category": "家具",
                              "policies": {"returnable": True, "exchangeable": True, "return_days": 7,
                                           "cancellation_allowed": True, "terms": "",
                                           "delivery_countries": []}}
        s["skus"][pid] = {"id": pid, "product_id": pid, "merchant_id": mid, "options": {},
                          "unit_amount_minor": price, "stock": 5, "active": True,
                          "currency": "CNY", "version": 1, "default": True}
        s["shipping_options"]["ship_" + mid] = {
            "id": "ship_" + mid, "merchant_id": mid, "name": "标准快递", "amount_minor": 0,
            "countries": [], "min_days": 3, "max_days": 5, "active": True, "version": 1, "default": True}
    s["discounts"]["disc_pt500"] = {
        "id": "disc_pt500", "merchant_id": "merchant_b", "code": "PT500", "kind": "fixed",
        "value": 50000, "minimum_minor": 100000, "product_ids": [], "buyer_ids": [],
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


if ENV.exists():
    shutil.rmtree(ENV)
(ENV / "services/commerce").mkdir(parents=True)
(ENV / "workspace").mkdir()
(ENV / "services/commerce/state.json").write_text(json.dumps(state(), ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
print("fixture:", ENV)
