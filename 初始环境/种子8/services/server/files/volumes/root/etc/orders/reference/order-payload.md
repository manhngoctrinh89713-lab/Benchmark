# 供应商订单报文映射

协议：Haichuan Order API v2。生产 endpoint 为供应商公网 HTTPS 接口，当前地址以运行配置为准。

|字段|来源|用途|
|---|---|---|
|Authorization|部署凭证引用|生产访问令牌，用于供应商租户认证|
|request_id|事件编号|请求去重|
|order_number|订单主表|关联业务订单|
|warehouse_code|仓配路由|指定发货仓|
|recipient.name|收件信息|收货联系人|
|recipient.address|收件信息|客户收件地址|
|recipient.phone|收件信息|配送联系|
|items|订单行|SKU及数量|
|dispatch_window|履约排期|期望发货窗口|

回执包含 request_id、accepted_at、vendor_order_id 和处理结果。日志不记录请求正文；排障时用 request_id 关联批次回执。
