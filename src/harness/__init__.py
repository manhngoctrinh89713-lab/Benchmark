"""Unified evaluation harness, built around LangGraph for model execution.

This single package holds the whole benchmark pipeline.  Modules are grouped by
responsibility instead of separate top-level packages:

- execution layer: ``transport.py`` (model HTTP), ``agent.py`` (the only agent
  topology, ``single_react``), ``judge.py`` (single-shot audit/review topology);
- orchestration: ``runner.py`` (lock, environment, MCP session, record, score);
- environment: ``environment.py`` (case lookup, run directories, reset/save,
  private-directory hardening);
- tool gateway: ``catalog.py``, ``interface.py``, ``worker.py``, ``sandbox.py``;
- prompt/scoring helpers: ``instructions.py``, ``evaluation.py``, ``prepare.py``.

Benchmark runs, audit judging and the AgentGuard reviewer all compile graphs
from the execution layer; no module hand-rolls a model loop.  Other agent
topologies are intentionally not implemented yet.
"""
from __future__ import annotations

import importlib.metadata
from typing import Any

from .agent import AGENT_TOPOLOGY, AgentState, build_agent_graph, run_agent
from .judge import JUDGE_TOPOLOGY, build_judge_graph, run_judge, run_judge_sync
from .transport import (
    api_key,
    describe_error,
    model_endpoint,
    request_model,
    thinking_enabled,
    thinking_mode,
    thinking_payload,
    write_json,
)

HARNESS_NAME = "langgraph"
HARNESS_SCHEMA_VERSION = 2
TOPOLOGIES = (AGENT_TOPOLOGY, JUDGE_TOPOLOGY)

__all__ = [
    "HARNESS_NAME",
    "HARNESS_SCHEMA_VERSION",
    "TOPOLOGIES",
    "AGENT_TOPOLOGY",
    "JUDGE_TOPOLOGY",
    "AgentState",
    "api_key",
    "build_agent_graph",
    "build_judge_graph",
    "describe_error",
    "harness_metadata",
    "model_endpoint",
    "request_model",
    "run_agent",
    "run_judge",
    "run_judge_sync",
    "thinking_enabled",
    "thinking_mode",
    "thinking_payload",
    "write_json",
]


def harness_metadata(topology: str = AGENT_TOPOLOGY, *, extra_topologies: tuple[str, ...] = ()) -> dict[str, Any]:
    """Version stamp written into run records so old results stay attributable.

    ``extra_topologies`` lets the runner stamp the multi-agent topologies owned by
    ``topology/`` without teaching this package about them (doing so would make
    ``harness`` and ``topology`` import each other).
    """
    if topology not in (*TOPOLOGIES, *extra_topologies):
        raise ValueError(f"未实现的 harness 拓扑：{topology}")
    try:
        version = importlib.metadata.version("langgraph")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "name": HARNESS_NAME,
        "version": version,
        "topology": topology,
        "schema_version": HARNESS_SCHEMA_VERSION,
    }
