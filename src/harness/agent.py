"""The one agent topology: a single ReAct agent (model <-> tools).

Only this topology is implemented for now.  Every benchmark run — default,
batched, and with any security-enhancement switch — compiles the same graph so
model, tool, budget and recording semantics cannot drift between experiments.
Additional topologies must be added here rather than by hand-rolling a loop in
the runner.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from securityEnhancement.AgentGuard import trajectory
from securityEnhancement.QuittingAgents import (
    QUIT_TOOL_NAME,
    find_quit_call,
    parse_quit_call,
    parse_text_quit,
)

from .transport import request_model, thinking_payload, write_json

AGENT_TOPOLOGY = "single_react"


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    step: int
    done: bool
    final: str
    termination_reason: str


def _quit_final_text(decision: dict[str, Any]) -> str:
    reason = decision.get("reason") or "（模型未提供退出原因）"
    lines = [f"QUIT: {reason}"]
    question = decision.get("question")
    missing = decision.get("missing_information") or []
    if question:
        lines.extend(["", f"Question: {question}"])
    if missing:
        lines.extend(["", "Missing information:", *[f"- {item}" for item in missing]])
    return "\n".join(lines) + "\n"


def build_agent_graph(
    *,
    model: str,
    endpoint: str,
    key: str,
    client: httpx.AsyncClient,
    record: Path,
    run_root: Path,
    meta: dict[str, Any],
    session: Any,
    tools: list[dict[str, Any]],
    catalog_by_name: dict[str, Any],
    guard_events_path: Path,
    max_steps: int,
    max_tool_calls: int,
    api_retries: int,
    specified_quit_enabled: bool,
    tool_calls_before: int = 0,
    model_request: Callable[..., Awaitable[httpx.Response]] = request_model,
):
    """Compile the fixed single-agent ReAct graph used by every benchmark run.

    ``max_steps`` and ``max_tool_calls`` always apply to this compiled agent.
    ``tool_calls_before`` lets a multi-agent topology retain aggregate counters
    in ``meta`` while charging only this phase against its own call limit.
    """
    known = set(catalog_by_name)
    executed_tool_names: list[str] = []

    def finish_quit(
        state: AgentState,
        step: int,
        decision: dict[str, Any],
        response_calls: list[dict[str, Any]],
    ) -> AgentState:
        calls = response_calls or []
        other_names = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            if name != QUIT_TOOL_NAME:
                other_names.append(name or "unknown")
        decision.update({
            "triggered": True,
            "step": step,
            "tool_calls_before": meta["tool_calls"],
            "executed_tool_names_before": list(executed_tool_names),
            "concurrent_tool_call_count": len(calls),
            "mixed_with_other_calls": bool(other_names),
            "ignored_tool_calls": other_names,
        })
        write_json(record / "specified-quit.json", decision)
        with (record / "specified-quit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(decision, ensure_ascii=False) + "\n")
        final = _quit_final_text(decision)
        (record / "final.md").write_text(final, encoding="utf-8")
        meta["status"] = "completed"
        meta["termination_reason"] = "specified_quit"
        meta["specified_quit"] = decision
        if decision.get("mixed_with_other_calls"):
            meta["specified_quit_mixed_call_blocked"] = {
                "step": step,
                "ignored_tool_calls": other_names,
            }
        print(final, flush=True)
        return {
            **state,
            "step": step,
            "done": True,
            "final": final,
            "termination_reason": "specified_quit",
        }

    async def model_node(state: AgentState) -> AgentState:
        step = int(state.get("step", 0)) + 1
        if step > max_steps:
            meta["termination_reason"] = "max_steps"
            raise RuntimeError(f"达到最大模型调用轮数 {max_steps}")

        messages = list(state["messages"])
        trajectory.append_llm_input(guard_events_path, messages)
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "max_tokens": 20480,
        }
        payload.update(thinking_payload(model))
        write_json(record / f"model-{step:03d}-request.json", payload)
        meta["model_calls"] += 1
        meta["normal_model_calls"] += 1
        response = await model_request(
            client, payload, key, record, step, meta, api_retries, endpoint=endpoint,
        )
        (record / f"model-{step:03d}-response.json").write_text(response.text, encoding="utf-8")
        response.raise_for_status()
        result = response.json()
        choice = result["choices"][0]
        message = choice["message"]
        messages.append(message)
        write_json(record / "messages.json", messages)
        trajectory.append_llm_output(guard_events_path, message)
        if choice["finish_reason"] not in {"stop", "tool_calls"}:
            raise RuntimeError(f"模型输出未正常结束：{choice['finish_reason']}")

        calls = message.get("tool_calls") or []
        if specified_quit_enabled and calls:
            quit_call = find_quit_call(calls)
            if quit_call is not None:
                return finish_quit(state, step, parse_quit_call(quit_call), calls)

        if not calls:
            final = message.get("content") or ""
            if specified_quit_enabled:
                decision = parse_text_quit(final)
                if decision is not None:
                    return finish_quit(state, step, decision, [])
            (record / "final.md").write_text(final, encoding="utf-8")
            meta["status"] = "completed"
            meta["termination_reason"] = "final_response"
            print(final, flush=True)
            return {
                **state,
                "messages": messages,
                "step": step,
                "done": True,
                "final": final,
                "termination_reason": "final_response",
            }

        return {
            **state,
            "messages": messages,
            "step": step,
            "done": False,
            "termination_reason": "",
        }

    async def tools_node(state: AgentState) -> AgentState:
        step = int(state.get("step", 1))
        messages = list(state["messages"])
        calls = messages[-1].get("tool_calls") or []
        for call in calls:
            if int(meta["tool_calls"]) - tool_calls_before >= max_tool_calls:
                meta["termination_reason"] = "max_tool_calls"
                raise RuntimeError(f"达到最大工具调用次数 {max_tool_calls}（当前 Agent）")
            function = call["function"]
            event = {
                "id": call["id"],
                "name": function["name"],
                "arguments": function["arguments"],
                "started_at": datetime.now().astimezone().isoformat(),
            }
            meta["tool_calls"] += 1
            tool_record = record / f"tool-{meta['tool_calls']:03d}.json"
            write_json(tool_record, event)
            arguments: dict[str, Any] | None = None
            try:
                if function["name"] not in known:
                    raise ValueError("工具未启用")
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
                tool_result = await session.call_tool(
                    function["name"], arguments, read_timeout_seconds=timedelta(seconds=90),
                )
                output = tool_result.model_dump(mode="json", exclude_none=True)
            except (ValueError, TypeError) as error:
                output = {
                    "isError": True,
                    "content": [{"type": "text", "text": str(error)}],
                }
            from .environment import apply_private_directories
            apply_private_directories(run_root, create=False)
            event.update(result=output, finished_at=datetime.now().astimezone().isoformat())
            write_json(tool_record, event)
            with (record / "tools.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            if isinstance(arguments, dict) and function["name"] in known:
                tool_info = catalog_by_name.get(function["name"])
                trajectory.append_tool_events(
                    guard_events_path,
                    function["name"],
                    arguments,
                    output,
                    description=(tool_info.description or "") if tool_info else "",
                    input_schema=(tool_info.inputSchema or {}) if tool_info else {},
                )
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(output, ensure_ascii=False),
            })
            write_json(record / "messages.json", messages)
            executed_tool_names.append(function["name"])
            print(f"[{step}] {function['name']}：{'失败' if output.get('isError') else '完成'}", flush=True)
        return {**state, "messages": messages}

    def after_model(state: AgentState) -> str:
        if state.get("done"):
            return END
        calls = (state.get("messages") or [{}])[-1].get("tool_calls") or []
        return "tools" if calls else END

    graph = StateGraph(AgentState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after_model, ["tools", END])
    graph.add_edge("tools", "model")
    return graph.compile()


async def run_agent(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    endpoint: str,
    key: str,
    client: httpx.AsyncClient,
    record: Path,
    run_root: Path,
    meta: dict[str, Any],
    session: Any,
    catalog_by_name: dict[str, Any],
    guard_events_path: Path,
    max_steps: int,
    max_tool_calls: int,
    api_retries: int,
    specified_quit_enabled: bool,
    model_request: Callable[..., Awaitable[httpx.Response]] = request_model,
) -> AgentState:
    """Run the single-agent ReAct graph and return its terminal state."""
    compiled = build_agent_graph(
        model=model,
        endpoint=endpoint,
        key=key,
        client=client,
        record=record,
        run_root=run_root,
        meta=meta,
        session=session,
        tools=tools,
        catalog_by_name=catalog_by_name,
        guard_events_path=guard_events_path,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        api_retries=api_retries,
        specified_quit_enabled=specified_quit_enabled,
        model_request=model_request,
    )
    state = await compiled.ainvoke(
        {"messages": messages, "step": 0, "done": False},
        config={"recursion_limit": max_steps * 2 + 10},
    )
    if not (record / "final.md").exists():
        raise RuntimeError("LangGraph harness 未生成 final.md")
    if not state.get("done"):
        raise RuntimeError("LangGraph harness 未到达终态")
    return state
