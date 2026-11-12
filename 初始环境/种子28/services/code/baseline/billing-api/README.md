# 账单查询服务

生产路由 `src/routes/bill.js` 在路由内直接比较会话客户编号与账单归属编号。
账单已接入新CRM，客户编号按字符串传输与保存；旧CRM客服工单仍使用历史接口。
旧CRM工单比较函数位于 `src/legacy-crm/customer-id.js`。接口字段说明见共享目录 billing/数据字典.md。
运行测试：`node tests/bill.test.js` 和 `node tests/customer-id.test.js`。
