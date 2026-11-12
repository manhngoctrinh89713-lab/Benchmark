# buyer MCP

当前提供 65 个公开接口。

## 支持的能力

管理买家资料、收件地址和支付方式；查询商家、分类、商品规格、价格、库存、销售政策及配送方式；收藏商品、维护购物车、选择部分商品结算、使用优惠、保存报价并下单付款；查询和修改订单、再次购买、取消未付款订单、申请或撤回已付款订单取消；查询包裹、确认收货、领取数字商品和服务交付；按订单行申请退换货、提交证明和退件、修改撤回售后；申请撤回退款、查询支付及退款交易、下载支付收据和退款凭证；购买和管理订阅、修改扣款方式及下期方案、查询支付账单；管理开票资料、申请和下载税务发票。

## 对象与操作语义

成交模型以商品和 SKU 区分描述与可购买规格。购物车使用当前目录计算，不占库存；报价保存选定商品、地址、配送、优惠和数字交付邮箱，有效十五分钟。创建订单时核对报价条件并预留库存三十分钟，订单保存成交快照。地址簿后续修改不回写已有报价或订单。

支付结果分为 pending、succeeded、declined、closed。退款申请、商家审批、退款交易和最终到账分别记录。买家确认收货与物流投递证据分别保存；退换货按已收货的订单行数量和购买时政策处理。证明和数字交付文件保存字节快照。

订阅保存购买时的合同、数量、访问有效期和扣款方式。方案调价不直接改动已有合同。新方案与数量从下个账期生效；试用每个买家每个方案限一次。立即取消结束访问，期末取消保留当前周期，resume 撤销尚未生效的期末取消。应付账单、支付收据和税务发票使用不同对象。

金额使用整数最小货币单位，单次结算属于一个商家、一种货币。开票按商家提供的固定税率和已开具文件建模，不提供跨地区税法计算、分期金融、积分或拍卖。

## 接口目录

- `bind_payment_method`：使用支付服务签发的凭证绑定支付方式。
- `cancel_my_order`：直接取消未付款订单并释放库存。
- `cancel_subscription_change`：清除尚未生效的订阅方案变更。
- `change_my_subscription`：立即取消、账期末取消或撤销账期末取消：cancel_now/cancel_at_period_end/resume。
- `checkout_cart`：按当前默认配送条件直接创建待付款订单，并核对预期总额。
- `confirm_shipment_receipt`：记录买家确认收货，与承运方的投递记录分别保存。
- `create_checkout_quote`：保存选定购物车商品的结算报价，有效期十五分钟，不预留库存。
- `delete_address`：删除地址簿中的地址，不修改已有订单。
- `delete_billing_profile`：删除开票资料，既有申请保留原资料快照。
- `download_delivery`：下载有效数字交付的文件快照。
- `download_receipt`：将已成功支付的收据保存为 JSON 文件。
- `download_refund_receipt`：将已成功到账退款的凭证保存为 JSON 文件。
- `download_tax_invoice`：下载商家已开具的税务发票文件。
- `get_buyer_profile`：读取当前买家的资料、默认地址及已绑定支付方式。
- `get_cart`：读取商家购物车，以当前价格和库存计算商品金额。
- `get_checkout_quote`：读取已保存的结算条件和报价有效期。
- `get_my_order`：读取订单成交快照、支付状态、履约状态及包裹。
- `get_my_subscription`：读取订阅合同、访问有效期、扣款方式和账单。
- `get_product`：读取商品当前规格、价格、库存和销售退换政策。
- `list_addresses`：列出当前买家的收件地址。
- `list_available_plans`：列出可购买的订阅方案及价格、周期和试用期。
- `list_billing_profiles`：列出保存的开票资料。
- `list_favorites`：列出收藏商品及其当前销售状态。
- `list_merchants`：按名称查询商家及其货币、配送和公开信息。
- `list_my_aftersales`：查询退换货申请、退件及处理结果。
- `list_my_cancellation_requests`：查询订单取消申请及处理结果。
- `list_my_deliveries`：查询数字商品和服务的交付记录、接收人、有效期与授权状态。
- `list_my_invoices`：查询订阅应付账单，账单与税务发票分别保存。
- `list_my_orders`：分页查询自己的订单，可按订单状态筛选。
- `list_my_payments`：查询支付尝试及退款累计金额。
- `list_my_refund_requests`：查询退款申请与商家的审批结果。
- `list_my_refunds`：查询退款交易的处理中、成功和失败状态。
- `list_my_shipments`：查询订单各包裹的商品数量、物流事件和签收信息。
- `list_my_subscriptions`：查询自己的订阅合同和待生效变更。
- `list_my_tax_invoices`：查询开票申请、已开票信息和处理状态。
- `list_payment_methods`：列出支付方式及默认支付方式。
- `list_product_categories`：列出在售商品的分类。
- `list_shipping_options`：列出商家当前可用的配送方式、费用和预计时效。
- `pay_invoice`：支付开放的订阅账单，成功后更新已付费访问周期。
- `pay_order`：支付待付款订单，返回本次支付尝试的独立状态。
- `place_order_from_quote`：按报价创建待付款订单；重新核对价格、库存、政策和优惠后预留库存三十分钟。
- `reorder`：把历史订单的规格和数量加入当前购物车，使用当前商品状态和价格。
- `request_aftersale`：按订单行及数量申请退货退款或换货，并保存证明文件快照。
- `request_order_cancellation`：为已付款但未履约的订单提交取消申请，由商家处理。
- `request_refund`：向商家申请退还指定支付的部分或全部可退金额。
- `request_tax_invoice`：为成功支付申请税务发票，固定当次开票资料。
- `save_address`：新增或修改地址；已保存的报价和订单继续使用原有地址快照。
- `save_billing_profile`：新增或修改开票抬头、税号、地址和接收邮箱。
- `save_favorite`：收藏或取消收藏商品。
- `schedule_subscription_change`：保存下个账期生效的方案和数量，按当前方案条款固定新合同。
- `search_products`：按商家、分类、类型、价格和库存组合查询在售商品，支持排序与分页。
- `set_cart_item`：增加或修改一个购物车规格的数量，零表示移除。
- `set_default_address`：设置后续购买使用的默认地址。
- `set_default_payment_method`：设置默认支付方式，不改变已有订阅的扣款方式。
- `set_subscription_payment_method`：修改订阅后续自动扣款使用的支付方式。
- `submit_return_shipment`：为获准的退换货提交退件物流信息。
- `subscribe_plan`：以当前方案条款建立订阅合同；有试用期时在试用结束后开始扣款。
- `unbind_payment_method`：停用绑定的支付方式；使用该方式的订阅需要另行更换。
- `update_aftersale`：修改待处理售后申请的说明和证明文件。
- `update_buyer_profile`：更新买家的姓名、联系邮箱和电话。
- `update_cart`：替换购物车商品列表；每项指定 SKU 或商品默认规格及数量，空列表清空。
- `update_my_order`：修改订单备注；未付款且未发货的订单可修改同一配送地区内的地址。
- `withdraw_aftersale`：撤回待处理的退换货申请。
- `withdraw_cancellation_request`：撤回尚未处理的订单取消申请。
- `withdraw_refund_request`：撤回待审批的退款申请。
