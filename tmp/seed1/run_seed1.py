"""Run the temporary seed-1 fixture against the three benchmark models.

Uses the production agent graph, system prompt and ToolInterface, but keeps the
MCP tool layer in-process: this session's sandbox forbids piped stdio, so the
``harness.worker`` subprocess cannot be spawned. Tool schemas, jsonschema
validation, sandbox hooks and call semantics are unchanged.
"""
import argparse
import asyncio
import importlib.util
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from harness import harness_metadata
from harness.agent import run_agent
from harness.catalog import load_servers
from harness.instructions import assemble_prompt
from harness.interface import ToolInterface
from harness.transport import (api_key, model_endpoint, thinking_enabled, thinking_mode,
                               write_json)

BASE = ROOT / "tmp/seed1"
FIXTURE = BASE / "初始环境"
RUNS = BASE / "运行环境"
RECORDS = BASE / "运行记录"
MODELS = ["deepseek-flash", "qwen3.8-flash", "glm-5.3-flash"]


class InProcessSession:
    """The subset of an MCP ClientSession the ReAct tool node uses."""

    def __init__(self, interface):
        self.interface = interface

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        return await self.interface.call(name, arguments)


def evaluator():
    spec = importlib.util.spec_from_file_location("seed1_eval", BASE / "种子1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_one(model, instruction, max_steps, max_tool_calls, dry):
    run_id = f"{datetime.now().astimezone():%Y%m%d-%H%M%S}-{model}-{uuid4().hex[:6]}"
    run_root = RUNS / model / run_id
    record = RECORDS / run_id
    shutil.copytree(FIXTURE, run_root)
    record.mkdir(parents=True, exist_ok=True)

    interface = await ToolInterface(run_root, load_servers(run_root, ["buyer"])).initialize()
    catalog = interface.tools
    tools = [{"type": "function", "function": {
        "name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
        for t in catalog]
    system = assemble_prompt(["buyer"])
    messages = [{"role": "system", "content": system}, {"role": "user", "content": instruction}]
    write_json(record / "tools.json", tools)
    (record / "system.md").write_text(system, encoding="utf-8")
    write_json(record / "messages.json", messages)

    meta = {"run_id": run_id, "case": "种子1临时", "model": model,
            "endpoint": model_endpoint(model), "harness": harness_metadata("single_react"),
            "topology": "single_react", "groups": ["buyer"], "run_root": str(run_root),
            "started_at": datetime.now().astimezone().isoformat(), "status": "running",
            "method": "normal", "agentguard_enabled": False, "targeted_reminder_enabled": False,
            "thinking_enabled": thinking_enabled(model), "thinking_mode": thinking_mode(model),
            "model_calls": 0, "normal_model_calls": 0, "tool_calls": 0,
            "max_tool_calls": max_tool_calls, "proxy_mode": "environment",
            "variant": "fi_test", "category": "Factual Inconsistency", "instruction_type": "test",
            "mcp_transport": "in-process"}
    print(f"[{model}] 工具 {len(tools)} 个，开始", flush=True)
    try:
        if dry:
            meta["status"] = "prepared"
            return meta, record, run_root
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=20)) as client:
            await run_agent(
                messages=messages, tools=tools, model=model, endpoint=meta["endpoint"],
                key=api_key(model=model), client=client, record=record, run_root=run_root,
                meta=meta, session=InProcessSession(interface),
                catalog_by_name={t.name: t for t in catalog},
                guard_events_path=record / "agentguard_events.jsonl",
                max_steps=max_steps, max_tool_calls=max_tool_calls,
                api_retries=1, specified_quit_enabled=False)
    except Exception as error:
        meta["status"] = "failed"
        meta["error"] = f"{type(error).__name__}: {error}"
        meta.setdefault("termination_reason", "error")
    finally:
        meta["finished_at"] = datetime.now().astimezone().isoformat()
        write_json(record / "run.json", meta)
    return meta, record, run_root


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--max-tool-calls", type=int, default=25)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    instruction = (BASE / "instruction.md").read_text(encoding="utf-8").strip()
    if not args.dry:
        for path in (RUNS, RECORDS):
            if path.exists():
                shutil.rmtree(path)
    for model in args.models:
        print("=" * 70, flush=True)
        meta, record, run_root = await run_one(model, instruction, args.max_steps,
                                               args.max_tool_calls, args.dry)
        if args.dry:
            print(f"[{model}] dry status={meta['status']} error={meta.get('error')}", flush=True)
            continue
        result = evaluator().evaluate(run_root, FIXTURE)
        write_json(record / "evaluation.json", result)
        final_path = record / "final.md"
        final = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
        print(f"[{model}] status={meta['status']} reason={meta.get('termination_reason')} "
              f"模型调用={meta['model_calls']} 工具调用={meta['tool_calls']} "
              f"score={result['score']} 实付={result['paid_total_minor']} "
              f"多付={result['overpay_minor']}", flush=True)
        print("最终回答：", final[:500].replace("\n", " "), flush=True)
    print("记录目录：", RECORDS, flush=True)


asyncio.run(main())
