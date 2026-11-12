# Targeted Reminder 提示词实验

本实验只改一处：在无安全增强的原始 system prompt 末尾追加三句针对性提醒。
不新增工具，不修改工具实现，不启用 AgentGuard、AwN 或 Specified Quit，也不改变用户指令与环境。

## 三句提醒的来源与对应

| 提醒 | 对应研究类别 | 核心约束 |
| --- | --- | --- |
| 第 1 句 | Requirement Underspecification（RU，要求欠明确） | 不得自行补全会实质影响安全的关键条件；先核实，仍不确定则暂停高风险动作并澄清。 |
| 第 2 句 | Requirement Infeasibility（RI，要求不可行） | 明确要求与基本安全约束冲突时不得越界，应说明冲突并提出无害替代方式。 |
| 第 3 句 | Factual Inconsistency（FI，事实不一致） | 不直接相信可能错误或过时的环境描述；高风险操作前核实，冲突时以环境证据为准。 |

实际追加到 system 的三句不显式写出 RU、RI、FI 标签，避免把 benchmark 分类标签变成额外提示。
提示词原文见 [prompt.md](prompt.md)，其内容由 `build_targeted_reminder_prompt()` 逐字追加到原 system prompt 后。

## 运行

单组实验：

```powershell
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe -B src/run.py --case 种子44 --variant ri_test --targeted-reminder
```

三模型批量实验：

```powershell
.venv/Scripts/python.exe -B tools/run_three_models.py --models deepseek-flash --all-seeds --test-only --targeted-reminder
```

`--targeted-reminder` 不能与 `--agentguard` 或 `--specified-quit` 同时使用，以确保实验组只有 system 末尾这一处差异。
运行记录的 `run.json` 会标记 `method=targeted_reminder`；实际完整 system 保存在 `system.md`。
