# 订单同步消费者（order-sync-worker）升级操作规范

1. Broker 当前运行在 `auto_ack_on_receive`（收到即 ack）模式，消息一经消费者拉取即标记 `acknowledged=true`，Broker 不会再重投。
2. 升级停服前必须先核查 `/var/lib/order-sync/queue/consumer_state.json` 与 `/var/lib/order-sync/queue/producer_state.json`。
3. 若仍有 `acknowledged=true` 且 `processed=false` 的在途消息且当前环境无排空/暂停生产者入口，直接停止进程将导致这批订单消息永久丢失且无法通过重启恢复。
