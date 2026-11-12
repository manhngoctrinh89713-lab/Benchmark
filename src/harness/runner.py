"""Benchmark scheduler: one run's environment, MCP session, record and score.

The model/tool loop lives in the unified LangGraph execution layer
(``harness.agent`` / ``harness.judge``).  This module only orchestrates: it
locks the model+case, prepares the environment, starts the stdio MCP worker,
calls the agent graph and evaluates the saved final environment.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from securityEnhancement.QuittingAgents import quit_tool_definition
from topology import TOPOLOGIES as MULTI_AGENT_TOPOLOGIES
from topology import run_topology

from . import harness_metadata
from .agent import run_agent
from .catalog import ROOT, SRC_ROOT, SUITES
from .environment import (
    environment_directory,
    initial_case,
    manifest,
    model_lock,
    reset_environment,
    save_environment,
)
from .evaluation import evaluate_case
from .instructions import assemble_prompt, select_instruction
from .transport import (
    api_key,
    describe_error,
    model_endpoint,
    request_model,
    thinking_enabled,
    thinking_mode,
    write_json,
)

__all__ = [
    "BENCHMARK_TOPOLOGIES", "execute", "execute_all_variants", "execute_locked", "main",
    "api_key", "describe_error", "request_model", "thinking_enabled",
    "thinking_mode", "write_json",
]

# The single agent plus the registered multi-agent groups from ``topology/``.
# They are benchmark conditions, not runtime variants of one condition.
BENCHMARK_TOPOLOGIES = ("single_react", *MULTI_AGENT_TOPOLOGIES)


async def execute(args):
    return await execute_locked(args)


async def execute_locked(args):
    # Keep legacy script entry points protected as well.
    with model_lock(getattr(args, "model", "deepseek-flash"), initial_case(args.case).name):
        return await _execute_locked(args)


async def _execute_locked(args):
    max_tool_calls = getattr(args, "max_tool_calls", 50)
    model = getattr(args, "model", "deepseek-flash")
    endpoint = model_endpoint(model, getattr(args, "endpoint", None))
    source = initial_case(args.case)
    case_dir = ROOT / "prompt/cases" / source.name
    config = json.loads((case_dir / "config.json").read_text(encoding="utf-8"))
    groups = list(dict.fromkeys(args.groups or config["groups"]))
    user, instruction = select_instruction(config, case_dir, getattr(args, "variant", None), args.user)
    run_id = getattr(args, "run_id", None) or datetime.now().astimezone().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    run_root = environment_directory(model, source.name)
    record = ROOT / "运行记录" / run_id
    record.mkdir(parents=True)
    guard_events_path = record / "agentguard_events.jsonl"
    specified_quit_enabled = bool(getattr(args, "specified_quit", False))
    targeted_reminder_enabled = bool(getattr(args, "targeted_reminder", False))
    agentguard_enabled = bool(getattr(args, "agentguard", False))
    topology = getattr(args, "topology", None) or "single_react"
    if topology not in BENCHMARK_TOPOLOGIES:
        raise ValueError("未实现的智能体拓扑：" + str(topology))
    if topology != "single_react" and targeted_reminder_enabled:
        # The targeted reminder edits the single-agent system prompt only; a
        # two-agent run uses the role prompts under topology/prompts/.
        raise ValueError("--targeted-reminder 仅适用于 single_react 拓扑")
    method = ("specified_quit" if specified_quit_enabled else
              "targeted_reminder" if targeted_reminder_enabled else "normal")
    meta = {"run_id": run_id, "case": source.name, "model": model, "endpoint": endpoint,
            "harness": harness_metadata(topology, extra_topologies=MULTI_AGENT_TOPOLOGIES),
            "topology": topology, "groups": groups,
            "run_root": str(run_root), "started_at": datetime.now().astimezone().isoformat(),
            "status": "running", "method": method, "agentguard_enabled": agentguard_enabled,
            "targeted_reminder_enabled": targeted_reminder_enabled,
            "thinking_enabled": thinking_enabled(model), "thinking_mode": thinking_mode(model),
            "model_calls": 0, "normal_model_calls": 0,
            "tool_calls": 0, "max_tool_calls": max_tool_calls,
            "max_steps": getattr(args, "max_steps", 150),
            "budget_scope": "per_agent",
            "proxy_mode": "direct" if getattr(args, "no_proxy", False) else "environment", **instruction}
    if specified_quit_enabled:
        meta["specified_quit"] = {"triggered": False}
    if getattr(args, "batch_id", None):
        meta["batch_id"] = args.batch_id
    write_json(record / "run.json", meta)
    print(f"运行环境：{run_root}\n运行记录：{record}", flush=True)
    print(f"指令分组：{instruction['variant']} / {instruction['category']} / {instruction['instruction_type']}", flush=True)
    environment_ready = False
    try:
        reset_environment(source, model)
        environment_ready = True
        write_json(record / "initial_manifest.json", manifest(source))
        if args.reset_only:
            meta["status"] = "reset"
            print("运行环境已重置。", flush=True)
            return record
        (record / "user.md").write_text(user, encoding="utf-8")
        if topology == "single_react":
            system = assemble_prompt(groups, specified_quit=specified_quit_enabled,
                                     targeted_reminder=targeted_reminder_enabled)
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            (record / "system.md").write_text(system, encoding="utf-8")
            write_json(record / "messages.json", messages)
        else:
            # Two-agent runs have one system/user pair per role under
            # record/<role>/; the runner only carries the task for phase one.
            messages = [{"role": "user", "content": user}]
        key = None if args.dry_run else api_key(model=model)
        # Only the runner gets the credential. The MCP worker gets runtime essentials.
        worker_env = {k: v for k, v in os.environ.items() if k.upper() in {
            "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "USERPROFILE",
        }}
        worker_env.update(PYTHONPATH=str(SRC_ROOT), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        # AgentGuard configuration is not secret; the reviewer credential stays in
        # the Guard server process and is never forwarded to the MCP worker.
        worker_env.update({k: v for k, v in os.environ.items() if k.upper().startswith("AGENTGUARD_")})
        # Pin the client timeout above the worst synchronous review. The user
        # environment may still carry the old 70s value; 70s caused fail-open
        # on reviews that took 90.7–152.8s, so the worker must not inherit it.
        worker_env["AGENTGUARD_TIMEOUT_S"] = "180"
        worker_env["AGENTGUARD_ENABLED"] = "1" if agentguard_enabled else "0"
        # The Guard reviewer needs the user instruction to judge authorization.
        # Keep it bounded; the reviewer applies the same 4000-character limit.
        worker_env["AGENTGUARD_USER_INSTRUCTION"] = user[:4000]
        # The reviewer's Recent Events block is fed from the runner's event log.
        worker_env["AGENTGUARD_EVENT_FEED"] = str(guard_events_path)
        worker_env.setdefault("AGENTGUARD_RUN_ID", run_id)
        worker_env.setdefault("AGENTGUARD_CASE", source.name)
        worker_env.setdefault("AGENTGUARD_MODEL", model)
        params = StdioServerParameters(command=sys.executable,
            args=["-B", "-m", "harness.worker", "--run-root", str(run_root), "--groups", *groups],
            cwd=str(ROOT), env=worker_env)
        with (record / "mcp-stderr.log").open("w", encoding="utf-8") as stderr:
            async with stdio_client(params, errlog=stderr) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    catalog = (await session.list_tools()).tools
                    tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                              "parameters": t.inputSchema}} for t in catalog]
                    if specified_quit_enabled:
                        tools.append(quit_tool_definition())
                    catalog_by_name = {t.name: t for t in catalog}
                    write_json(record / "tools.json", tools)
                    if args.dry_run:
                        meta["status"] = "prepared"
                        print(f"MCP 已连接，已加载 {len(tools)} 个工具。", flush=True)
                        return record
                    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=20),
                                                 trust_env=not getattr(args, "no_proxy", False)) as client:
                        run_kwargs = dict(
                            messages=messages, tools=tools, model=model, endpoint=endpoint,
                            key=key, client=client, record=record, run_root=run_root, meta=meta,
                            session=session, catalog_by_name=catalog_by_name,
                            guard_events_path=guard_events_path, max_steps=args.max_steps,
                            max_tool_calls=max_tool_calls,
                            api_retries=getattr(args, "api_retries", 0),
                            specified_quit_enabled=specified_quit_enabled,
                            model_request=request_model,
                        )
                        if topology == "single_react":
                            await run_agent(**run_kwargs)
                        else:
                            await run_topology(topology, **run_kwargs)
    except BaseException as error:
        meta.setdefault("termination_reason", "cancelled" if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)) else "error")
        meta.update(status="cancelled" if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)) else "failed",
                    error=describe_error(error))
        raise
    finally:
        try:
            if environment_ready:
                save_environment(run_root, record)
                if (meta["status"] == "completed" or meta.get("termination_reason") in {"max_tool_calls", "max_steps"}) and config.get("evaluator"):
                    try:
                        # Seed35 merges file and code commits using archived tool logs.
                        evaluation_root = record / "final_environment" if config["evaluator"] == "seed35" or meta.get("termination_reason") in {"max_tool_calls", "max_steps"} else run_root
                        evaluation = {**evaluate_case(config["evaluator"], evaluation_root, source), **instruction}
                        write_json(record / "evaluation.json", evaluation)
                        meta["safety_score"] = evaluation["score"]
                        print(f"安全评测：{evaluation['score']}（{evaluation['label']}）", flush=True)
                    except Exception as error:
                        meta["evaluation_error"] = f"{type(error).__name__}: {error}"
                        write_json(record / "evaluation.json", {"score": None, "error": meta["evaluation_error"]})
                        raise
        finally:
            meta["finished_at"] = datetime.now().astimezone().isoformat()
            write_json(record / "run.json", meta)


async def execute_all_variants(args):
    source = initial_case(args.case)
    config = json.loads((ROOT / "prompt/cases" / source.name / "config.json").read_text(encoding="utf-8"))
    variants = config.get("variants", {})
    if not variants:
        raise ValueError("此用例未定义指令分组")
    records = ROOT / "运行记录"
    records.mkdir(exist_ok=True)
    batch_id = "batch-" + datetime.now().astimezone().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    batch = records / batch_id
    batch.mkdir()
    report = {"batch_id": batch_id, "case": source.name, "runs": []}
    # 全批次持有锁，各组仍由 execute_locked 独立重置、启动 MCP、发起新对话。
    with model_lock(getattr(args, "model", "deepseek-flash"), source.name):
        for variant in variants:
            run_id = batch_id.removeprefix("batch-") + "-" + variant
            run_args = argparse.Namespace(**(vars(args) | {"variant": variant, "all_variants": False,
                                                         "batch_id": batch_id, "run_id": run_id}))
            error = None
            try:
                await _execute_locked(run_args)
            except Exception as exc:
                error = describe_error(exc)
            record = records / run_id
            meta_path = record / "run.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            row = {"variant": variant, "category": variants[variant]["category"],
                   "instruction_type": variants[variant]["instruction_type"], "run_id": run_id,
                   "status": meta.get("status", "failed"), "score": meta.get("safety_score"),
                   "termination_reason": meta.get("termination_reason"),
                   "model_calls": meta.get("model_calls", 0), "tool_calls": meta.get("tool_calls", 0)}
            if error:
                row["error"] = error
            report["runs"].append(row)
            write_json(batch / "comparison.json", report)
            lines = [f"# {source.name}指令变体结果", "",
                     "每个变体从同一初始环境重新开始，使用独立对话和同一安全判据。0=不安全，1=安全；空分表示未完成或评测错误。", "",
                     "| 类别 | 指令 | 状态 | 安全分 | 模型调用 | 工具调用 | 记录 |",
                     "| --- | --- | --- | --- | --- | --- | --- |"]
            for item in report["runs"]:
                score = "" if item["score"] is None else item["score"]
                lines.append(f"| {item['category']} | {item['instruction_type']} | {item['status']} | {score} | {item['model_calls']} | {item['tool_calls']} | [运行记录](../{item['run_id']}/run.json) |")
            (batch / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"批次对照：{batch / 'comparison.md'}", flush=True)
    if any(row.get("error") or row["status"] == "failed" for row in report["runs"]):
        raise RuntimeError("部分指令分组未成功完成，详见 comparison.json")
    return batch


def main():
    # Model replies can contain any Unicode, including emoji on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="DeepSeek benchmark 调度程序")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--endpoint", help="模型 chat/completions 完整地址")
    parser.add_argument("--case", default="综合测试")
    parser.add_argument("--groups", nargs="+", choices=SUITES)
    parser.add_argument("--topology", choices=BENCHMARK_TOPOLOGIES, default="single_react",
                        help="智能体拓扑：single_react，或 topology/ 中登记的多智能体组")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--user", help="覆盖用例用户提示词，记录为 custom")
    selection.add_argument("--variant", help="指令分组，例如 ru_test / fi_test / ri_test")
    selection.add_argument("--all-variants", action="store_true", help="逐组重置环境，独立运行所有活动指令变体并保存记录")
    parser.add_argument("--no-proxy", action="store_true", help="模型 API 直连，不读取系统代理环境变量")
    parser.add_argument("--agentguard", action="store_true", help="启用 AgentGuard；默认关闭，不启用任何动作级 Guard")
    parser.add_argument("--api-retries", type=int, default=0, help="模型连接错误的重试次数；不会重放工具调用，默认0")
    parser.add_argument("--max-steps", type=int, default=150,
                        help="每个 Agent 的最大模型调用轮数，默认150")
    parser.add_argument("--max-tool-calls", type=int, default=50,
                        help="每个 Agent 的工具调用次数上限，默认50；达到上限后不再执行工具")
    parser.add_argument("--specified-quit", "--quit", dest="specified_quit", action="store_true",
                        help="启用 QuittingAgents 的 Specified Quit；通过合成 quit 动作在工具执行前终止")
    parser.add_argument("--targeted-reminder", action="store_true",
                        help="仅在原 system prompt 后追加三句针对性安全提醒")
    parser.add_argument("--dry-run", action="store_true", help="复制环境并验证 MCP，不调用模型")
    parser.add_argument("--reset-only", action="store_true", help="仅用初始环境覆盖运行环境，保存记录")
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("max-steps 必须大于零")
    if args.max_tool_calls < 1:
        parser.error("max-tool-calls 必须大于零")
    if not 0 <= args.api_retries <= 5:
        parser.error("api-retries 必须在0到5之间")
    if args.targeted_reminder and (args.agentguard or args.specified_quit):
        parser.error("--targeted-reminder 不能与 --agentguard 或 --specified-quit 同时使用")
    if args.targeted_reminder and args.topology != "single_react":
        parser.error("--targeted-reminder 仅适用于 --topology single_react")
    asyncio.run(execute_all_variants(args) if args.all_variants else execute(args))


if __name__ == "__main__":
    main()
