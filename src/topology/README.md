# 多智能体拓扑（四个组）

| 组名 | 流程 | 只读阶段职责 |
| --- | --- | --- |
| `planner_executor` | Planner → Executor | 只读查证现状，产出可执行的计划 |
| `investigator_executor` | Investigator → Executor | 只读查证事实，产出事实清单与不确定点 |
| `reviewer_executor` | Reviewer → Executor | 直接审查用户任务，产出交给 Executor 的执行时注意点 |
| `investigator_reviewer_executor` | Investigator → Reviewer → Executor | 只读查证事实产出调查简报，只读 Reviewer 复核简报并标注必须 STOP 的步骤 |

前三个双阶段组共用同一套图构建器（`two_stage.py`），三阶段组用 `three_stage.py`；提示词完全分开：每个组各有一套角色 system prompt 和 user 模板。每个阶段都编译 `harness.agent.build_agent_graph` 的 ReAct 图，不另写模型循环，因此模型调用、工具调用、预算和记录语义与单智能体 harness 一致。

`investigator_reviewer_executor` 在 Investigator 与 Executor 之间插入一次独立的只读安全审查：Reviewer 要么批准简报，要么产出带 `STOP：...` 门的修订简报，Executor 只拿到审查后的简报。这是针对"Executor 无视简报警告"和"阶段一决策错误被放大"两类失败设计的。


`reviewer_executor` 是同一审查思路的两阶段消融组：去掉 Investigator，让 Reviewer 直接从用户任务出发做只读核查并产出执行时注意点。它用于区分收益来自独立调查、独立审查，还是两者串联。

## 目录

```
src/topology/
  __init__.py          对外 API：TOPOLOGIES / build_topology / run_topology / spec_for / load_prompt
  common.py            提示词读取、只读工具筛选、工具名清单
  two_stage.py         两阶段 LangGraph 构建、阶段预算、记录
  three_stage.py       三阶段 LangGraph 构建、阶段预算、记录
  prompts/
    planner_executor/          Planner → Executor
      planner.md               Planner system
      planner_user.md          Planner user 模板（任务 + 只读工具名）
      executor.md              Executor system
      executor_user.md         Executor user 模板（上游计划 + 任务）
    investigator_executor/     Investigator → Executor
      investigator.md          Investigator system
      investigator_user.md     Investigator user 模板（任务 + 只读工具名）
      executor.md              Executor system
      executor_user.md         Executor user 模板（上游简报 + 任务）
    reviewer_executor/          Reviewer → Executor
      reviewer.md              Reviewer system
      reviewer_user.md         Reviewer user 模板（任务 + 只读工具名）
      executor.md              Executor system
      executor_user.md         Executor user 模板（执行时注意点 + 任务）
    investigator_reviewer_executor/     Investigator → Reviewer → Executor
      investigator.md          Investigator system
      investigator_user.md     Investigator user 模板（任务 + 只读工具名）
      reviewer.md              Reviewer system
      reviewer_user.md         Reviewer user 模板（任务 + 上游简报 + 只读工具名）
      executor.md              Executor system
      executor_user.md         Executor user 模板（审查后的简报 + 任务）
```

## 提示词与测试指令放在哪里

| 内容 | 位置 | 消息角色 |
| --- | --- | --- |
| Planner 系统提示词 | `prompts/planner_executor/planner.md` | system |
| Planner 用户消息模板 | `prompts/planner_executor/planner_user.md`（`{task}`、`{read_only_tools}`） | user |
| planner_executor 的 Executor 系统提示词 | `prompts/planner_executor/executor.md` | system |
| planner_executor 的 Executor 用户消息模板 | `prompts/planner_executor/executor_user.md`（`{task}`、`{brief}`） | user |
| Investigator 系统提示词 | `prompts/investigator_executor/investigator.md` | system |
| Investigator 用户消息模板 | `prompts/investigator_executor/investigator_user.md`（`{task}`、`{read_only_tools}`） | user |
| investigator_executor 的 Executor 系统提示词 | `prompts/investigator_executor/executor.md` | system |
| investigator_executor 的 Executor 用户消息模板 | `prompts/investigator_executor/executor_user.md`（`{brief}`、`{task}`） | user |
| Reviewer 系统提示词（双阶段） | `prompts/reviewer_executor/reviewer.md` | system |
| Reviewer 用户消息模板（双阶段） | `prompts/reviewer_executor/reviewer_user.md`（`{task}`、`{read_only_tools}`） | user |
| reviewer_executor 的 Executor 系统提示词 | `prompts/reviewer_executor/executor.md` | system |
| reviewer_executor 的 Executor 用户消息模板 | `prompts/reviewer_executor/executor_user.md`（`{brief}`、`{task}`） | user |
| 三阶段的 Investigator 系统提示词 | `prompts/investigator_reviewer_executor/investigator.md` | system |
| 三阶段的 Investigator 用户消息模板 | `prompts/investigator_reviewer_executor/investigator_user.md`（`{task}`、`{read_only_tools}`） | user |
| Reviewer 系统提示词 | `prompts/investigator_reviewer_executor/reviewer.md` | system |
| Reviewer 用户消息模板 | `prompts/investigator_reviewer_executor/reviewer_user.md`（`{task}`、`{brief}`、`{read_only_tools}`） | user |
| 三阶段的 Executor 系统提示词 | `prompts/investigator_reviewer_executor/executor.md` | system |
| 三阶段的 Executor 用户消息模板 | `prompts/investigator_reviewer_executor/executor_user.md`（`{review}`、`{task}`） | user |
| 用户任务（测试指令） | 仍由用例配置决定：`prompt/cases/<用例>/config.json` 的 `variants.<变体>.user_prompt`（无变体时用顶层 `user_prompt`），即 `prompt/cases/<用例>/<文件>.md` | user |

- 四个工作流的 Executor 提示词是各自独立的文件，不互相引用：它们分别收到执行计划、调查简报、双阶段执行时注意点或三阶段审查后的简报。
- `{task}` 是测试指令原文；`{brief}` 是第一个角色的最终产出（`record/brief.md`）；`{review}` 是 Reviewer 的最终产出（`record/review.md`）；`{read_only_tools}` 是本次运行该只读阶段可调用的只读工具名，每行一个。
- 打开 Quit 时，quit 协议自动追加到各阶段 system prompt 末尾，不在这些文件里。
- 测试指令本身不用复制到本目录：`run_topology` 把 `messages` 里最后一条 user 消息当任务，各阶段共用同一份；顶层的 `record/user.md`（runner 写的）就是测试指令原文。
- 单智能体的 `prompt/system.md` 不进入多阶段：runner 仍会按单智能体口径写 `record/system.md`，但多阶段读的是 `prompts/` 下各自的文件。工具说明只走请求里的 `tools` 数组，`prompt/tools/*.md` 已于 2026-11-11 归档到 `../../.archive/tool-docs-20261111/`。需要保留工作区规则时，写进对应的角色提示词。

## 工具边界

- 只读阶段（Planner / Investigator / Reviewer）能调用的只有只读工具。只读不是手写名单，而是按 AgentGuard 的确定性元数据分类（`securityEnhancement.AgentGuard.metadata.classify(...).side_effect is False`）从当次 MCP 目录里筛出来的，所以新增或改名的工具不需要改本包；名字像读取但会改状态的工具（如 `mail__mark_read`、`database__backup_db`、`files__download_file`）会被排除。
- 只读阶段的 `tools` 数组都带全部工具定义，所以它们看得到完整工具目录（含写入、发送、删除类）；user 消息里的「只读工具」只列出能直接调用的名字。
- Executor 拿全部已启用工具。
- 以上只影响"看得到"。真正能执行的是裁剪后的 catalog，所以即使模型硬调写入工具，也只会得到"工具未启用"，不会到达 MCP。
- 不在 MCP 目录里的控制工具（如 `quit`）保持可用：它不改变状态，所有阶段都能用它终止。

## 预算

`max_steps` 和 `max_tool_calls` 都按单个 Agent 独立生效：每个阶段都会获得完整的命令行上限，前一个阶段耗尽自己的额度不会挤占后续阶段。`meta` 里的 `model_calls` / `tool_calls` 仍累计整次运行的总量，仅用于记录和报告；判断是否触顶时使用当前阶段的起始偏移。`run.json` 标记 `"budget_scope": "per_agent"`，`phases.json` 的 `model_call_limit` / `tool_call_limit` 记录每个 Agent 实际获得的上限。

## 三个安全版本

| 版本 | 打开方式 | 拓扑侧行为 |
| --- | --- | --- |
| 无安全增强 | 默认。`specified_quit_enabled=False`，worker 环境 `AGENTGUARD_ENABLED=0` | 各阶段只用角色提示词；工具直接执行 |
| Quit（Specified Quit） | `specified_quit_enabled=True`，且 `tools` 里有 `quit` 定义（由 runner 追加） | 每个阶段的 system prompt 末尾追加 `SPECIFIED_QUIT_PROMPT`；任一只读阶段退出即跳过后续阶段，执行阶段退出即以退出说明作为 `final.md`；两种情况都在工具执行前拦截 |
| Guard（AgentGuard） | worker 环境 `AGENTGUARD_ENABLED=1`、`AGENTGUARD_USER_INSTRUCTION`、`AGENTGUARD_EVENT_FEED`（runner 已设置） | 拦截点在 `harness.interface.ToolInterface.call`，与拓扑无关；各阶段写同一个 event feed，reviewer 的 Recent Events 跨阶段连续 |

Quit 与 Guard 可以同时开（与单智能体一致）：`quit` 调用在 `model_node` 里先于工具节点处理，不经过 Guard，也不在 MCP 目录里；Guard 的 `deny` 只是把工具结果变成错误，不会终止阶段。

## 运行记录

```
record/<第一个角色>/     只读阶段：system.md user.md tools.json（模型可见）messages.json model-*.json final.md
record/<第二个角色>/     三阶段才有：同上，只读
record/executor/         执行阶段：同上，工具为全集
record/brief.md          第一个只读阶段产出原文（两阶段交给 Executor；三阶段交给 Reviewer）
record/review.md         三阶段才有：Reviewer 审查后的简报（交给 Executor）
record/phases.json       各阶段的可见工具、可调用工具、模型/工具调用次数、终止原因
record/final.md          Executor 的最终答复（评测与 judge 读这个文件）
```

`phases.json` 里 `tools` 是模型看到的工具，`callable` 是真正能执行的工具；两者不一致时以 `callable` 为准。

任一只读阶段触发 `specified_quit` 时不再进入后续阶段，`final.md` 就是退出说明。

## 调用方式

`run_topology` 的参数与 `harness.agent.run_agent` 对齐，`messages` 里最后一条 user 消息就是任务：

```python
from topology import run_topology

await run_topology(
    "reviewer_executor",  # 或 "planner_executor" / "investigator_executor" / "investigator_reviewer_executor"
    messages=messages, tools=tools, model=model, endpoint=endpoint, key=key,
    client=client, record=record, run_root=run_root, meta=meta, session=session,
    catalog_by_name=catalog_by_name, guard_events_path=guard_events_path,
    max_steps=args.max_steps, max_tool_calls=max_tool_calls,
    api_retries=args.api_retries, specified_quit_enabled=args.specified_quit,
)
```

`harness.runner` 已按拓扑分派：`--topology single_react` 走 `run_agent`，其余组名走 `run_topology`，默认仍是 `single_react`。`tools/run_three_models.py --topologies ...` 会在同一个 (模型, 种子) 上顺序跑选中的拓扑。`run.json` 的 `harness.topology` 和 `topology` 都写该组名。

单智能体运行仍会写顶层的 `record/system.md`、`record/messages.json`；多阶段运行不写这两个单智能体输入，阶段输入在 `record/<角色>/` 下，最终答案统一在 `record/final.md`。

## 测试

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s src/tests -t src -p 'test_topology.py' -v
```
