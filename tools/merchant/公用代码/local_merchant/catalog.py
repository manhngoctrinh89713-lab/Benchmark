"""Explicit public commerce tool catalog."""
from mcp.types import ToolAnnotations

TOOLS = {
    'adjust_inventory': ('增减商品默认规格的可售库存。', False),
    'adjust_sku_inventory': ('增减指定规格的可售库存，已下单库存另行保留。', False),
    'cancel_merchant_order': ('取消未付款订单并释放预留库存。', False),
    'change_merchant_subscription': ('立即取消、账期末取消或撤销待取消状态。', False),
    'complete_aftersale': ('收到退件后按成交金额发起退款，或为原规格创建换货包裹。', False),
    'create_product': ('创建商品及默认规格，支持实物、数字商品和服务。', False),
    'create_shipment': ('按订单行及数量创建发货包裹，支持部分发货和多个包裹。', False),
    'create_sku': ('为商品增加独立定价和库存的规格。', False),
    'create_subscription_plan': ('创建订阅方案，配置价格、账期、试用天数和条款。', False),
    'deliver_order_item': ('交付数字商品或服务，保存接收邮箱、授权说明和可选文件快照。', False),
    'download_aftersale_evidence': ('下载买家提交的售后证明文件快照。', False),
    'export_orders': ('将筛选后的商家订单导出为 CSV。', False),
    'fulfill_order': ('将订单尚未发出的全部实物商品创建为一个包裹。', False),
    'get_merchant_order': ('读取订单成交快照及相关支付、退款。', True),
    'get_merchant_profile': ('读取当前商家资料。', True),
    'get_sales_summary': ('按货币汇总成功支付、已到账退款和净收入。', True),
    'list_aftersales': ('查询退换货申请和退件状态。', True),
    'list_cancellation_requests': ('查询已付款订单的取消申请。', True),
    'list_discounts': ('查询商家优惠规则及累计使用次数。', True),
    'list_merchant_orders': ('分页查询商家订单，可按状态筛选。', True),
    'list_merchant_subscriptions': ('查询商家订阅及购买时保存的合同。', True),
    'list_payments': ('查询商家的支付尝试及处理状态。', True),
    'list_products': ('查询商家商品及规格、库存、价格和销售政策。', True),
    'list_refund_requests': ('查询买家的退款申请。', True),
    'list_refunds': ('查询商家发起的退款及支付服务处理状态。', True),
    'list_shipments': ('查询商家包裹和承运方物流事件。', True),
    'list_shipping_options': ('列出商家的全部配送方案。', True),
    'list_subscription_plans': ('查询商家订阅方案，可包含已停售方案。', True),
    'list_tax_invoice_requests': ('查询买家的税务开票申请。', True),
    'receive_return': ('登记商家收到退件；可将退回商品重新入库。', False),
    'refund_payment': ('为成功支付发起部分或全部退款，退款到账由支付服务另行记录。', False),
    'resolve_aftersale': ('审批退换货申请，同意时提供退件地址。', False),
    'resolve_cancellation_request': ('审批取消申请；同意后取消未履约订单并发起退款，退款到账另行记录。', False),
    'resolve_refund_request': ('审批退款申请；同意后发起退款交易。', False),
    'resolve_tax_invoice_request': ('拒绝开票申请，或登记发票编号并上传已开具的发票文件。', False),
    'revoke_delivery': ('撤销一项数字商品或服务授权，并记录原因。', False),
    'save_discount': ('维护固定金额或折扣比例优惠，含门槛、商品、客户、时间、次数及叠加条件。比例以万分比填写。', False),
    'save_shipping_option': ('新增或修改配送方式、适用国家、费用和预计工作日时效。', False),
    'update_product': ('修改商品资料和销售政策；价格参数修改默认规格，已有订单保留成交快照。', False),
    'update_sku': ('修改规格的售价或上架状态。', False),
    'update_subscription_plan': ('更新对外销售方案，已订阅合同继续使用购买时条款。', False),
}


def register_tool(server, store, name):
    description, readonly = TOOLS[name]
    server.tool(name=name, description=description, annotations=ToolAnnotations(readOnlyHint=readonly, destructiveHint=not readonly, idempotentHint=readonly, openWorldHint=False))(getattr(store, name))


def register_tools(server, store):
    for name in TOOLS:
        register_tool(server, store, name)
