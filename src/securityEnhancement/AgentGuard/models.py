"""Data models shared by the Guard server, client and tests."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import DEFAULT_PRINCIPAL_DATA

RiskLevel = Literal["low", "medium", "high"]
PolicyEffect = Literal["allow", "deny", "llm_review"]
FinalDecision = Literal["allow", "deny"]


class Principal(BaseModel):
    """The single medium-trust identity used by every model and case."""

    role: str = "default"
    trust_level: int = 2
    trust_scale: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    label: str = "medium_trust"


DEFAULT_PRINCIPAL = Principal(**DEFAULT_PRINCIPAL_DATA)


class ToolMetadata(BaseModel):
    """Deterministic security metadata generated from the public tool contract."""

    group: str
    tool_name: str
    capabilities: list[str] = Field(default_factory=list)
    side_effect: bool = False
    risk_level: RiskLevel = "low"
    classifier_version: str = ""
    fallback: bool = False
    basis: str = ""


class ToolCallInfo(BaseModel):
    """The public tool call as seen by the benchmark (no host paths)."""

    group: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class GuardRequest(BaseModel):
    """POST /v1/guard/decide request body."""

    model_config = ConfigDict(extra="ignore")

    tool: ToolCallInfo
    arguments: dict[str, Any] = Field(default_factory=dict)
    principal: Principal = Field(default_factory=lambda: DEFAULT_PRINCIPAL.model_copy(deep=True))
    context: dict[str, Any] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    """Result of evaluating the loaded JSON policy."""

    effect: PolicyEffect = "allow"
    reason: str = ""
    rule_id: str | None = None
    rule_description: str | None = None
    rule_prompt: str | None = None
    priority: float | None = None
    matched: bool = False
    fail_open: bool = False
    policy_status: str = "missing"


class ReviewDecision(BaseModel):
    """Result of one LLM reviewer call."""

    decision: FinalDecision = "allow"
    reason: str = ""
    fail_open: bool = True
    ok: bool = False
    model: str = ""
    error: str | None = None


class GuardResponse(BaseModel):
    """Final decision returned to the benchmark."""

    decision: FinalDecision = "allow"
    reason: str = ""
    fail_open: bool = False
    source: str = "policy"
    rule_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    risk_level: str | None = None
    side_effect: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    latency_ms: float | None = None
