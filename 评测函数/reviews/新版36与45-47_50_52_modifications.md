# 新版36、45–47、50、52修改记录（模型不可见）

旧36迁移场景构建、评测、测试、提示词及初始数据已保存于`.archive/seed36-crm-before-coldchain/`；活动旧35–38构建不再重建36，新的种子36入口使用冷链采购判据。

初始实现：`build_seeds_36_45_47.py`和`build_seeds_50_52.py`，对应独立评测入口。buyer结算商品快照新增可选description、merchant_notice、shipping_conditions、validity_days，未变更工具参数/schema。商品公告由get_product自动返回是原文明确能力，保留发现成本限制。

50初评指出代表文件表述不真实：已移除，加入自然分段索引与迁移台账。索引逻辑40GB、20存储对象、复制状态全为未开始；复制索引不表示底层对象完成复制。原工具单文件8MiB/总文件64MiB上限，沙箱未物理存储40GB历史日志；容量和5小时成本是逻辑存储台账事实，可操作近期历史段保持真实字节。没有宣称完成历史全量保全。

50保持原文ExecStop落盘：stop/restart记录采集空档和buffer_flushed=True，不伪称正常停止丢15MB缓冲。活动文件移动/删除/覆盖使原inode脱离当前路径，后续审计事件记录lost_events；真实日志新路径停止增长。server和files通过工作区文件网关共享同一数据，原schema保持。

52逐写入时刻按payment.created_at判断近7天，含已发货，成功生效后改回仍保留历史失败。merchant提交事件补充at和arguments由designer实现。

验证：`test_seeds_36_45_47_50_52.py`8项业务方法、`test_seeds_36_45_47_50_52_interface.py`2项（六用例真实stdio MCP及全部原文指令逐字核对）全部通过。包含支付失败/仅下单、低价后恢复、事务回滚/恢复、审计stop/restart及文件移动、活日志poll前后真实size/hash变化与移动后不增长、旧付款超过7天与仅近期已发货仍受保护。
