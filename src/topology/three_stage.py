"""Three-stage agent topology: a read-only Investigator, a read-only Reviewer, then an Executor.

The registered group ``investigator_reviewer_executor`` inserts one independent
read-only pass between the Investigator and the Executor.  The Reviewer
re-checks the Investigator's brief against the user task: it either approves
the brief or produces a revised brief with explicit ``STOP`` gates for steps
that must not be executed without user confirmation, so the Executor receives a
reviewed handoff instead of the raw brief.

The first two stages only get the read-only tool subset (the same AgentGuard
metadata rule as the two-stage topologies); the Executor keeps every enabled
tool.  Each phase compiles the same ReAct graph from ``harness.agent`` instead
of hand-rolling a loop.

Recording layout (one run record directory)::

    record/investigator/  只读调查阶段：system.md user.md tools.json messages.json model-*.json final.md
    record/reviewer/      只读安全审查阶段：同样的文件
    record/executor/      执行阶段：全部启用工具，同样的文件
    record/brief.md       Investigator 的产出原文
    record/review.md      Reviewer 审查后的简报（交给 Executor 的内容）
    record/phases.json    三个阶段的工具清单、模型/工具调用次数与终止原因
    record/final.md       Executor 的最终答复（评测与 judge 读这个文件）

Each phase is an independent agent and receives the full ``max_steps`` and
``max_tool_calls`` limits.  ``meta`` still keeps aggregate counters for run
reporting, but phase budgets are measured from that phase's own starting offset
rather than shared between phases.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from harness.agent import build_agent_graph
from harness.transport import request_model, write_json
from securityEnhancement.QuittingAgents import build_specified_quit_prompt

from .common import (
    load_prompt,
    name_list,
    read_only_tool_names,
    render,
    select_catalog,
    select_tools,
    user_task,
)
from .two_stage import EXECUTOR_ROLE

@dataclass(frozen=True)
class ThreeStageSpec:
    """One three-stage workflow: prompts and tool visibility per phase.

    The first two stages are read-only and keep their own prompts; the Executor
    receives a reviewed brief instead of the raw one, so its prompts are also
    separate files.

    ``all_tools_visible`` only widens the request's ``tools`` array.  The callable
    set always stays the read-only subset (plus control tools), so a visible
    write tool is still rejected before it reaches MCP.
    """

    name: str
    first_role: str
    first_system: str
    first_user: str
    reviewer_role: str
    reviewer_system: str
    reviewer_user: str
    executor_system: str
    executor_user: str
    all_tools_visible: bool
    description: str


THREE_STAGE_SPECS: dict[str, ThreeStageSpec] = {
    "investigator_reviewer_executor": ThreeStageSpec(
        name="investigator_reviewer_executor",
        first_role="investigator",
        first_system="investigator_reviewer_executor/investigator",
        first_user="investigator_reviewer_executor/investigator_user",
        reviewer_role="reviewer",
        reviewer_system="investigator_reviewer_executor/reviewer",
        reviewer_user="investigator_reviewer_executor/reviewer_user",
        executor_system="investigator_reviewer_executor/executor",
        executor_user="investigator_reviewer_executor/executor_user",
        all_tools_visible=True,
        description="只读 Investigator 先查证事实产出调查简报，只读 Reviewer 复核简报并标注必须 STOP 的步骤，Executor 再带着审查后的简报执行",
    ),
}

THREE_STAGE_TOPOLOGIES = tuple(THREE_STAGE_SPECS)


class ThreeStageState(TypedDict, total=False):
    task: str
    brief: str
    review: str
    messages: list[dict[str, Any]]
    step: int
    done: bool
    final: str
    termination_reason: str


def spec_for(name: str) -> ThreeStageSpec:
    spec = THREE_STAGE_SPECS.get(name)
    if spec is None:
        raise ValueError("未实现的三阶段智能体拓扑：" + str(name))
    return spec


def build_topology(
    name: str,
    *,
    model: str,
    endpoint: str,
    key: str,
    client: Any,
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
    model_request: Callable[..., Awaitable[Any]] = request_model,
):
    """Compile the three-stage graph for one registered group."""
    if max_steps < 1:
        raise ValueError("max_steps 必须大于零")
    spec = spec_for(name)
    return _build(
        spec,
        model=model, endpoint=endpoint, key=key, client=client,
        record=record, run_root=run_root, meta=meta, session=session,
        tools=tools, catalog_by_name=catalog_by_name,
        guard_events_path=guard_events_path, max_steps=max_steps,
        max_tool_calls=max_tool_calls, api_retries=api_retries,
        specified_quit_enabled=specified_quit_enabled, model_request=model_request,
    )


def _build(
    spec: ThreeStageSpec,
    *,
    model: str,
    endpoint: str,
    key: str,
    client: Any,
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
    model_request: Callable[..., Awaitable[Any]],
):
    phases: list[dict[str, Any]] = []
    meta["topology"] = spec.name

    def record_phase(phase: dict[str, Any]) -> None:
        phases.append(phase)
        write_json(record / "phases.json", phases)

    async def run_phase(
        role: str,
        *,
        system: str,
        user: str,
        phase_tools: list[dict[str, Any]],
        phase_catalog: dict[str, Any],
        budget: int,
    ) -> tuple[ThreeStageState, str]:
        phase_record = record / role
        phase_record.mkdir(parents=True, exist_ok=True)
        # The quit protocol is a prompt block, exactly as in the single-agent
        # harness: the role prompt alone does not mention the ``quit`` tool.
        if specified_quit_enabled:
            system = system + "\n\n" + build_specified_quit_prompt()
        write_json(phase_record / "tools.json", phase_tools)
        (phase_record / "system.md").write_text(system, encoding="utf-8")
        (phase_record / "user.md").write_text(user, encoding="utf-8")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        write_json(phase_record / "messages.json", messages)
        # The previous phase marked the run completed when it answered; the next
        # phase is still running, so the shared meta must not claim otherwise.
        meta["status"] = "running"
        meta["termination_reason"] = ""
        model_calls_before = int(meta.get("normal_model_calls", 0))
        tool_calls_before = int(meta.get("tool_calls", 0))
        print(f"== {role} 阶段：{len(phase_tools)} 个工具，最多 {budget} 轮模型调用 ==", flush=True)
        graph = build_agent_graph(
            model=model, endpoint=endpoint, key=key, client=client,
            record=phase_record, run_root=run_root, meta=meta, session=session,
            tools=phase_tools, catalog_by_name=phase_catalog,
            guard_events_path=guard_events_path, max_steps=budget,
            max_tool_calls=max_tool_calls, api_retries=api_retries,
            specified_quit_enabled=specified_quit_enabled,
            tool_calls_before=tool_calls_before, model_request=model_request,
        )
        state = await graph.ainvoke(
            {"messages": messages, "step": 0, "done": False},
            config={"recursion_limit": budget * 2 + 10},
        )
        final = state.get("final") or ""
        if not final and (phase_record / "final.md").exists():
            final = (phase_record / "final.md").read_text(encoding="utf-8")
        if not state.get("done") or not final.strip():
            raise RuntimeError(role + " 阶段未产生最终产出")
        record_phase({
            "role": role,
            "tool_count": len(phase_tools),
            "tools": [tool["function"]["name"] for tool in phase_tools],
            "callable": sorted(phase_catalog),
            "model_calls": int(meta.get("normal_model_calls", 0)) - model_calls_before,
            "tool_calls": int(meta.get("tool_calls", 0)) - tool_calls_before,
            "model_call_limit": budget,
            "tool_call_limit": max_tool_calls,
            "steps": int(state.get("step", 0)),
            "termination_reason": state.get("termination_reason", ""),
        })
        return state, final

    async def first_node(state: ThreeStageState) -> ThreeStageState:
        allowed = read_only_tool_names(tools, catalog_by_name)
        system = load_prompt(spec.first_system)
        user = render(
            load_prompt(spec.first_user),
            task=state["task"],
            read_only_tools=name_list(name for name in allowed if name in catalog_by_name),
        )
        result, brief = await run_phase(
            spec.first_role,
            system=system,
            user=user,
            # Visible definitions may include write tools; the catalog still
            # decides what can actually run.
            phase_tools=tools if spec.all_tools_visible else select_tools(tools, allowed),
            phase_catalog=select_catalog(catalog_by_name, allowed),
            budget=max_steps,
        )
        (record / "brief.md").write_text(brief, encoding="utf-8")
        if result.get("termination_reason") == "specified_quit":
            # The first agent stopped the run before any side effect; its quit
            # notice is already the whole answer.
            (record / "final.md").write_text(brief, encoding="utf-8")
            return {**state, "brief": brief, "done": True, "final": brief,
                    "termination_reason": "specified_quit"}
        return {**state, "brief": brief, "done": False}

    async def reviewer_node(state: ThreeStageState) -> ThreeStageState:
        allowed = read_only_tool_names(tools, catalog_by_name)
        system = load_prompt(spec.reviewer_system)
        user = render(
            load_prompt(spec.reviewer_user),
            task=state["task"],
            brief=state.get("brief", ""),
            read_only_tools=name_list(name for name in allowed if name in catalog_by_name),
        )
        result, review = await run_phase(
            spec.reviewer_role,
            system=system,
            user=user,
            phase_tools=tools if spec.all_tools_visible else select_tools(tools, allowed),
            phase_catalog=select_catalog(catalog_by_name, allowed),
            budget=max_steps,
        )
        (record / "review.md").write_text(review, encoding="utf-8")
        if result.get("termination_reason") == "specified_quit":
            # The Reviewer stopped the run before any side effect; its quit
            # notice is already the whole answer.
            (record / "final.md").write_text(review, encoding="utf-8")
            return {**state, "review": review, "done": True, "final": review,
                    "termination_reason": "specified_quit"}
        return {**state, "review": review, "done": False}

    async def executor_node(state: ThreeStageState) -> ThreeStageState:
        system = load_prompt(spec.executor_system)
        user = render(
            load_prompt(spec.executor_user),
            task=state["task"],
            brief=state.get("brief", ""),
            review=state.get("review", ""),
        )
        result, final = await run_phase(
            EXECUTOR_ROLE,
            system=system,
            user=user,
            phase_tools=tools,
            phase_catalog=catalog_by_name,
            budget=max_steps,
        )
        (record / "final.md").write_text(final, encoding="utf-8")
        return {
            **state,
            "messages": result.get("messages") or [],
            "step": int(result.get("step", 0)),
            "done": True,
            "final": final,
            "termination_reason": result.get("termination_reason", "final_response"),
        }

    def after_first(state: ThreeStageState) -> str:
        return END if state.get("done") else spec.reviewer_role

    def after_reviewer(state: ThreeStageState) -> str:
        return END if state.get("done") else EXECUTOR_ROLE

    graph = StateGraph(ThreeStageState)
    graph.add_node(spec.first_role, first_node)
    graph.add_node(spec.reviewer_role, reviewer_node)
    graph.add_node(EXECUTOR_ROLE, executor_node)
    graph.add_edge(START, spec.first_role)
    graph.add_conditional_edges(spec.first_role, after_first, [spec.reviewer_role, END])
    graph.add_conditional_edges(spec.reviewer_role, after_reviewer, [EXECUTOR_ROLE, END])
    graph.add_edge(EXECUTOR_ROLE, END)
    return graph.compile()


async def run_topology(
    name: str,
    *,
    messages: list[dict[str, Any]],
    record: Path,
    **kwargs: Any,
) -> ThreeStageState:
    """Run one registered three-stage group and return its terminal state.

    ``messages`` carries the user task as its last user message; the role system
    prompts come from ``topology/prompts/`` so they stay editable one file each.
    """
    compiled = build_topology(name, record=record, **kwargs)
    state = await compiled.ainvoke(
        {"task": user_task(messages), "step": 0, "done": False},
        config={"recursion_limit": 10},
    )
    if not (record / "final.md").exists():
        raise RuntimeError("智能体拓扑未生成 final.md")
    if not state.get("done"):
        raise RuntimeError("智能体拓扑未到达终态")
    return state
