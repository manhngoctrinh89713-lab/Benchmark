"""Single-shot model topology used by audit judges and the AgentGuard reviewer.

These callers do not need an agent loop, so their topology is one model node:
build the request, send it once through the shared transport, hand the raw
response back to the caller's own validation/caching/retry policy.  Keeping the
call inside a compiled LangGraph makes every benchmark, audit and security
review model request go through the same harness boundary.
"""
from __future__ import annotations

import asyncio
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

JUDGE_TOPOLOGY = "single_shot"


class JudgeState(TypedDict, total=False):
    client: Any
    endpoint: str
    headers: dict[str, str]
    payload: dict[str, Any]
    response: Any


async def _request(state: JudgeState) -> JudgeState:
    response = await state["client"].post(
        state["endpoint"],
        headers=state.get("headers") or {},
        json=state["payload"],
    )
    return {**state, "response": response}


def build_judge_graph():
    graph = StateGraph(JudgeState)
    graph.add_node("model", _request)
    graph.add_edge(START, "model")
    graph.add_edge("model", END)
    return graph.compile()


_compiled = None


def compiled_judge_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_judge_graph()
    return _compiled


async def run_judge(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Send one model request through the judge graph."""
    state = await compiled_judge_graph().ainvoke({
        "client": client,
        "endpoint": endpoint,
        "headers": headers or {},
        "payload": payload,
    })
    return state["response"]


def run_judge_sync(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    *,
    timeout: float = 600,
    transport: httpx.AsyncBaseTransport | None = None,
    trust_env: bool = True,
) -> httpx.Response:
    """Synchronous adapter for callers that are not async (AgentGuard reviewer).

    Must be called from a thread without a running asyncio loop; the reviewer's
    fail-open wrapper treats a violation as a normal reviewer failure.
    """

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout, transport=transport, trust_env=trust_env) as client:
            return await run_judge(client, endpoint, payload, headers)

    return asyncio.run(call())
