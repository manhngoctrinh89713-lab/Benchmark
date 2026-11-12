"""Environment driven configuration for the local AgentGuard experiment.

Every value has a safe default so that a missing environment variable never
blocks the benchmark.  Secrets (``MIMO_API_KEY``) are only read here and are
never written to disk by this package.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

SERVICE_NAME = "agentguard"
SERVICE_VERSION = "0.1.0"
CLASSIFIER_VERSION = "agentguard-metadata-v1"
POLICY_VERSION = "policy-v1"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 38080
DEFAULT_BASE_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
# Must exceed the worst synchronous ``llm_review`` latency.  The old 70s
# default was below four observed reviews (90.7–152.8s) in the 2026-11-09
# 10:11 batch, so the client failed open and ran the tool before the server
# could return ``deny``.  180s covers that batch with headroom over
# MIMO_TIMEOUT_S=60; the full audit log also contains one 203.5s review from
# a later (two-method) batch, which would still need a higher override.
DEFAULT_TIMEOUT_S = 180.0
DEFAULT_AUDIT_DIR = PROJECT_ROOT / "运行记录" / "AgentGuard"
DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.json")
DEFAULT_MIMO_MODEL = "mimo-v2.6-pro"
DEFAULT_MIMO_TIMEOUT_S = 60.0
DEFAULT_THINKING_MODE = "thinking"
MAX_USER_INSTRUCTION_CHARS = 4000
DEFAULT_REVIEW_TRACE_MAX_STEPS = 5

# The single, fixed principal used for every model, case and tool call.
DEFAULT_PRINCIPAL_DATA = {
    "role": "default",
    "trust_level": 2,
    "trust_scale": [0, 1, 2, 3, 4],
    "label": "medium_trust",
}


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def enabled() -> bool:
    """Return whether the benchmark explicitly opted into AgentGuard enforcement."""
    return (_env('AGENTGUARD_ENABLED') or '').lower() in {'1', 'true', 'yes', 'on'}


def base_url() -> str:
    """Base URL of the local Guard server (client side)."""
    return (_env("AGENTGUARD_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def timeout_s() -> float:
    """Timeout for one decision request issued by the benchmark."""
    return _env_float("AGENTGUARD_TIMEOUT_S", DEFAULT_TIMEOUT_S)


def policy_path() -> Path:
    """Active policy file; defaults to the policy bundled with this package."""
    raw = _env("AGENTGUARD_POLICY_PATH")
    return Path(raw).expanduser() if raw else DEFAULT_POLICY_PATH


def audit_dir() -> Path:
    raw = _env("AGENTGUARD_AUDIT_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_AUDIT_DIR


def mimo_base_url() -> str | None:
    return _env("MIMO_BASE_URL")


def mimo_api_key() -> str | None:
    return _env("MIMO_API_KEY")


def mimo_model() -> str:
    return _env("MIMO_MODEL") or DEFAULT_MIMO_MODEL


def mimo_timeout_s() -> float:
    return _env_float("MIMO_TIMEOUT_S", DEFAULT_MIMO_TIMEOUT_S)


def thinking_mode() -> str:
    """Single switch selecting the vendor field used to enable thinking.

    Supported values: ``thinking`` (default), ``enable_thinking``,
    ``reasoning_effort`` and ``none``.  Only one field is ever sent.
    """
    return (_env("MIMO_THINKING_MODE") or DEFAULT_THINKING_MODE).strip().lower()


def user_instruction() -> str | None:
    """Original user instruction for the current run, if the runner supplied it."""
    instruction = _env("AGENTGUARD_USER_INSTRUCTION")
    return instruction[:MAX_USER_INSTRUCTION_CHARS] if instruction else None


def event_feed_path() -> Path | None:
    """JSONL event feed written by the benchmark runner (optional)."""
    raw = _env("AGENTGUARD_EVENT_FEED")
    return Path(raw).expanduser() if raw else None


def review_trace_max_steps() -> int:
    """Number of recent events included in the reviewer prompt."""
    raw = _env("AGENTGUARD_REVIEW_TRACE_MAX_STEPS")
    try:
        value = int(raw) if raw is not None else DEFAULT_REVIEW_TRACE_MAX_STEPS
    except (TypeError, ValueError):
        value = DEFAULT_REVIEW_TRACE_MAX_STEPS
    return min(max(value, 1), 50)


def worker_context() -> dict:
    """Optional run metadata pushed into the MCP worker by the runner."""
    return {
        key: value
        for key, value in {
            "run_id": _env("AGENTGUARD_RUN_ID"),
            "case": _env("AGENTGUARD_CASE"),
            "model": _env("AGENTGUARD_MODEL"),
        }.items()
        if value
    }

