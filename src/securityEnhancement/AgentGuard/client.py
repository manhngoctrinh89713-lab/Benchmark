"""Async client that the benchmark uses before every real MCP tool call.

Any failure — missing server, timeout, HTTP error, malformed response — is
fail-open: the tool call is allowed and the fail-open is recorded on the server
side when the server is reachable, or simply reflected in the returned response.
The client never raises for transport problems and never terminates a run.
"""
from __future__ import annotations

from typing import Any

import httpx

from . import config, trajectory
from .metadata import classify
from .models import DEFAULT_PRINCIPAL, GuardResponse, ToolMetadata

FAIL_OPEN_REASON = "AgentGuard unavailable; fail-open"


def _fail_open(metadata: ToolMetadata, reason: str) -> GuardResponse:
    return GuardResponse(
        decision="allow",
        reason=reason,
        fail_open=True,
        source="fail_open",
        capabilities=list(metadata.capabilities),
        risk_level=metadata.risk_level,
        side_effect=metadata.side_effect,
        metadata={
            "classifier_version": metadata.classifier_version,
            "classifier_fallback": metadata.fallback,
            "classifier_basis": metadata.basis,
        },
    )


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - never fail because of a bad reason field
        return ""


async def check_tool_call(
    *,
    group: str,
    tool_name: str,
    arguments: dict[str, Any],
    input_schema: dict[str, Any],
    description: str = "",
) -> GuardResponse:
    """Ask the local Guard server whether this public tool call may proceed."""
    metadata = classify(group, tool_name, description, input_schema)
    payload = {
        "tool": {
            "group": group,
            "name": tool_name,
            "description": description or "",
            "input_schema": input_schema or {},
        },
        "arguments": arguments if isinstance(arguments, dict) else {},
        "principal": DEFAULT_PRINCIPAL.model_dump(),
        "context": config.worker_context(),
        "recent_events": trajectory.recent_events(),
    }
    url = config.base_url() + "/v1/guard/decide"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_s(), trust_env=False) as client:
            response = await client.post(url, json=payload)
    except httpx.TimeoutException:
        return _fail_open(metadata, "AgentGuard timeout; fail-open")
    except Exception as error:  # noqa: BLE001 - fail-open contract
        return _fail_open(metadata, f"{FAIL_OPEN_REASON} ({type(error).__name__})")

    if response.status_code != 200:
        return _fail_open(metadata, f"{FAIL_OPEN_REASON} (HTTP {response.status_code})")
    try:
        data = response.json()
    except ValueError:
        return _fail_open(metadata, f"{FAIL_OPEN_REASON} (invalid JSON)")
    if not isinstance(data, dict):
        return _fail_open(metadata, f"{FAIL_OPEN_REASON} (invalid response)")
    decision = data.get("decision")
    if decision not in {"allow", "deny"}:
        return _fail_open(metadata, f"{FAIL_OPEN_REASON} (invalid decision)")

    server_metadata = data.get("metadata")
    if not isinstance(server_metadata, dict):
        server_metadata = {}
    merged_metadata = {
        "classifier_version": metadata.classifier_version,
        "classifier_fallback": metadata.fallback,
        "classifier_basis": metadata.basis,
        **server_metadata,
    }
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = list(metadata.capabilities)
    latency = data.get("latency_ms")
    request_id = data.get("request_id")
    return GuardResponse(
        decision=decision,
        reason=_as_text(data.get("reason")),
        fail_open=bool(data.get("fail_open", False)),
        source=_as_text(data.get("source")) or "server",
        rule_id=_as_text(data.get("rule_id")) or None,
        capabilities=[str(item) for item in capabilities],
        risk_level=_as_text(data.get("risk_level")) or metadata.risk_level,
        side_effect=bool(data.get("side_effect", metadata.side_effect)),
        metadata=merged_metadata,
        request_id=request_id if isinstance(request_id, str) else None,
        latency_ms=float(latency) if isinstance(latency, (int, float)) and not isinstance(latency, bool) else None,
    )
