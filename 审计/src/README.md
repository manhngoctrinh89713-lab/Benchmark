# 公共运行筛选

`run_selection.scan(root)` 返回 `(cells, ignored_runs)`，供活动审计与后续审计共用。不调用模型、不重新计算安全分、不读取或修改审计状态。

筛选口径（2026-11-10 起）：

1. 从 `prompt/cases/种子*/config.json` 发现当前启用种子；每个种子必须恰好有一个 `instruction_type=test` 的变体。标准指令已弃用，不再参与筛选。
2. 核对指令变体、指令正文、工具组和初始环境文件哈希；环境比较忽略 `.git` 和 `__pycache__`。
3. 只接受已完成、有 messages.json 且已有安全分0或1的运行。优先读取 `evaluation-latest-summary.json`，否则读取 `evaluation.json`。
4. 安全增强运行一律不入选：`run.json` 的 `method` 不是 `normal`（含 `specified_quit`、`targeted_reminder`）或带有 `agentguard_enabled`/`targeted_reminder_enabled` 的运行记为 `security_enhanced`。早期运行没有这些字段时，只要同一 `batch_id` 中有任一条运行的工具返回出现 AgentGuard 拒绝输出（`agentguard`），整批都按增强实验排除；显式写明的字段始终优先。默认审计只覆盖无安全增强版本；被排除的运行不会阻断更早的默认运行入选。
5. 每个“种子 × 模型”选择 started_at 最新的有效默认运行；同时间以运行ID排序。更新但无效的尝试不会替代已有有效记录。
6. 返回有效记录、缺失槽位，以及失效/重复/被替代的记录及原因。安全0与安全1均保留。

不包含“是否已审计”的判断，也不生成特定审计的缓存指纹。事前风险证据审计使用会话输入、规则、模型配置与边界指纹缓存；危险操作起始点审计逐批独立重放，不使用其他审计结果作为完成标记。

回放的工具返回一致性、完整终态一致性等属于危险操作起始点模块自身的核验，不属于公共有效性筛选。通过筛选不等于一定能成功重放。

```powershell
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s 审计/src -p 'test_*.py' -v
```
