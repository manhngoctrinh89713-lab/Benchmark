# Specified Quit 接入

本目录实现 QuittingAgents 论文中的 Specified Quit 条件，不依赖 ToolEmu，也不与
AgentGuard 混合决策。

- `--specified-quit`：在主 system prompt 后追加 Specified Quit 规则。
- 动作空间额外暴露一个合成 `quit` 工具，不会调用 MCP。
- 每次模型响应先扫描整批 `tool_calls`。只要出现 `quit`，同批其他工具全部不执行。
- Quit 是合法终止：`status=completed`，`termination_reason=specified_quit`。
- 记录文件为 `specified-quit.json`，同时在 `run.json` 写入结构化统计。
- 兼容原仓库的文本协议：只含 `QUIT: <reason>` 的最终文本也按 Quit 记录。

单次运行：

```powershell
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe -B src/run.py --case 种子44 --variant ri_test --specified-quit
```

统计：

```powershell
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe -B -m securityEnhancement.QuittingAgents.summary
```
