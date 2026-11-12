# merchant MCP

当前提供 41 个公开接口。

## 支持的能力

查询商家资料；创建和修改商品、规格、售价、库存及销售政策，管理配送方案和优惠规则；查询导出订单，取消未付款订单，审批已付款订单取消；按商品数量分包发货、查询包裹、交付或撤销数字商品和服务授权；处理退换货、查看证明、登记退件入库、发起退款或换货；查询支付、审批退款申请、发起和查询退款；管理订阅方案、试用条款和订阅状态；汇总销售收入；查询开票申请并上传已开具发票。

## 对象与操作语义

商家与 buyer 使用同一份 commerce 状态，共享库存、订单、支付、退款、包裹、售后和订阅合同。商品拥有默认规格，并可增加独立价格和库存的 SKU。调整可售库存不改变已被订单预留的数量；停售及修改政策不改写成交快照。

优惠支持固定金额和万分比折扣、最低金额、适用商品和买家、有效期、次数及最多两项叠加。配送方式包含费用、国家范围和预计工作日。每个订单行保存优惠和税额分摊，退货金额据此计算。

实物按订单行及数量创建包裹。数字商品和服务保存交付接收人、说明、授权期限及文件快照。售后依次保存审批、退件、收件、退款或换货；退款发起与到账分别记录。税务开票由商家上传已开具文件。

环境控制入口位于 `tools/shared/commerce/local_commerce/environment.py`：推进时间、支付凭证签发、支付结果、退款结果及承运事件。这些入口不向 Agent 注册；原 `process_subscription_renewals` 已移出公开工具，账期由环境时钟统一推进。

## 接口目录

- `adjust_inventory`：增减商品默认规格的可售库存。
- `adjust_sku_inventory`：增减指定规格的可售库存，已下单库存另行保留。
- `cancel_merchant_order`：取消未付款订单并释放预留库存。
- `change_merchant_subscription`：立即取消、账期末取消或撤销待取消状态。
- `complete_aftersale`：收到退件后按成交金额发起退款，或为原规格创建换货包裹。
- `create_product`：创建商品及默认规格，支持实物、数字商品和服务。
- `create_shipment`：按订单行及数量创建发货包裹，支持部分发货和多个包裹。
- `create_sku`：为商品增加独立定价和库存的规格。
- `create_subscription_plan`：创建订阅方案，配置价格、账期、试用天数和条款。
- `deliver_order_item`：交付数字商品或服务，保存接收邮箱、授权说明和可选文件快照。
- `download_aftersale_evidence`：下载买家提交的售后证明文件快照。
- `export_orders`：将筛选后的商家订单导出为 CSV。
- `fulfill_order`：将订单尚未发出的全部实物商品创建为一个包裹。
- `get_merchant_order`：读取订单成交快照及相关支付、退款。
- `get_merchant_profile`：读取当前商家资料。
- `get_sales_summary`：按货币汇总成功支付、已到账退款和净收入。
- `list_aftersales`：查询退换货申请和退件状态。
- `list_cancellation_requests`：查询已付款订单的取消申请。
- `list_discounts`：查询商家优惠规则及累计使用次数。
- `list_merchant_orders`：分页查询商家订单，可按状态筛选。
- `list_merchant_subscriptions`：查询商家订阅及购买时保存的合同。
- `list_payments`：查询商家的支付尝试及处理状态。
- `list_products`：查询商家商品及规格、库存、价格和销售政策。
- `list_refund_requests`：查询买家的退款申请。
- `list_refunds`：查询商家发起的退款及支付服务处理状态。
- `list_shipments`：查询商家包裹和承运方物流事件。
- `list_shipping_options`：列出商家的全部配送方案。
- `list_subscription_plans`：查询商家订阅方案，可包含已停售方案。
- `list_tax_invoice_requests`：查询买家的税务开票申请。
- `receive_return`：登记商家收到退件；可将退回商品重新入库。
- `refund_payment`：为成功支付发起部分或全部退款，退款到账由支付服务另行记录。
- `resolve_aftersale`：审批退换货申请，同意时提供退件地址。
- `resolve_cancellation_request`：审批取消申请；同意后取消未履约订单并发起退款，退款到账另行记录。
- `resolve_refund_request`：审批退款申请；同意后发起退款交易。
- `resolve_tax_invoice_request`：拒绝开票申请，或登记发票编号并上传已开具的发票文件。
- `revoke_delivery`：撤销一项数字商品或服务授权，并记录原因。
- `save_discount`：维护固定金额或折扣比例优惠，含门槛、商品、客户、时间、次数及叠加条件。比例以万分比填写。
- `save_shipping_option`：新增或修改配送方式、适用国家、费用和预计工作日时效。
- `update_product`：修改商品资料和销售政策；价格参数修改默认规格，已有订单保留成交快照。
- `update_sku`：修改规格的售价或上架状态。
- `update_subscription_plan`：更新对外销售方案，已订阅合同继续使用购买时条款。
