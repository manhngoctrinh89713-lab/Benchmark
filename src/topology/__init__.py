"""Benchmark topologies ("组"): two-agent and three-agent workflows.

Registered groups:

* ``planner_executor``               Planner → Executor
* ``investigator_executor``          Investigator → Executor
* ``reviewer_executor``              Reviewer → Executor
* ``investigator_reviewer_executor`` Investigator → Reviewer → Executor

Every read-only stage may call only the read-only subset derived from the
AgentGuard metadata classification.  Read-only stages receive every tool
definition in their request, while their user message lists the read-only names
they may call.  The Executor keeps every enabled tool.  Prompts live under
``prompts/<group>/``: one system prompt and one user template per phase.  Each
group keeps its own Executor prompt.
"""
from __future__ import annotations

from .common import PROMPT_DIR, load_prompt, read_only_tool_names
from .two_stage import (
    EXECUTOR_ROLE,
    TOPOLOGY_SPECS as TWO_STAGE_SPECS,
    TOPOLOGIES as TWO_STAGE_TOPOLOGIES,
    TopologySpec,
    TwoStageState,
    build_topology as build_two_stage_topology,
    run_topology as run_two_stage_topology,
)
from .three_stage import (
    THREE_STAGE_SPECS,
    THREE_STAGE_TOPOLOGIES,
    ThreeStageSpec,
    ThreeStageState,
    build_topology as build_three_stage_topology,
    run_topology as run_three_stage_topology,
)

TOPOLOGY_SPECS = {**TWO_STAGE_SPECS, **THREE_STAGE_SPECS}
TOPOLOGIES = (*TWO_STAGE_TOPOLOGIES, *THREE_STAGE_TOPOLOGIES)


def spec_for(name: str):
    spec = TOPOLOGY_SPECS.get(name)
    if spec is None:
        raise ValueError("未实现的智能体拓扑：" + str(name))
    return spec


def build_topology(name: str, **kwargs):
    if name in TWO_STAGE_TOPOLOGIES:
        return build_two_stage_topology(name, **kwargs)
    if name in THREE_STAGE_TOPOLOGIES:
        return build_three_stage_topology(name, **kwargs)
    raise ValueError("未实现的智能体拓扑：" + str(name))


async def run_topology(name: str, **kwargs):
    if name in TWO_STAGE_TOPOLOGIES:
        return await run_two_stage_topology(name, **kwargs)
    if name in THREE_STAGE_TOPOLOGIES:
        return await run_three_stage_topology(name, **kwargs)
    raise ValueError("未实现的智能体拓扑：" + str(name))


__all__ = [
    "EXECUTOR_ROLE",
    "PROMPT_DIR",
    "THREE_STAGE_SPECS",
    "THREE_STAGE_TOPOLOGIES",
    "TOPOLOGIES",
    "TOPOLOGY_SPECS",
    "ThreeStageSpec",
    "ThreeStageState",
    "TopologySpec",
    "TwoStageState",
    "build_topology",
    "load_prompt",
    "read_only_tool_names",
    "run_topology",
    "spec_for",
]
