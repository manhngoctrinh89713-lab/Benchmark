# 供应商订单接入

版本 3.8，维护：订单平台组。服务 orders.service，运行配置 /etc/orders/vendor-client.json。

## 日常运行
订单事件由 order.dispatch 消费组接收，批量提交供应商接口。消费者提交成功后记录回执，失败时按重试策略重新入队；批次回执位于 /srv/orders/batches/。

配置采用 JSON。改动后运行配置校验，reload 热加载连接池设置；restart 会重新建立工作进程。值班排查按服务名过滤日志，结合队列深度及供应商回执确认故障范围。

## 接入资料
- 客户端参数表：/etc/orders/reference/http-client.md
- 报文与字段映射：/etc/orders/reference/order-payload.md
- 运行配置中的凭证引用由部署平台注入。

供应商侧证书由海川运维维护，续签事宜通过供应商工单跟进。对接协议版本与上线窗口由订单平台组登记。
