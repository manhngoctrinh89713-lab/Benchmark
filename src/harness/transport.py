"""Shared model transport for every LangGraph harness topology.

The harness owns topology and state; this module owns the one place that talks
to an OpenAI-compatible ``chat/completions`` endpoint.  Keeping transport here
means the ReAct agent, audit judges and the AgentGuard reviewer all use the same
retry, recording and vendor-field semantics.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

DEFAULT_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "glm": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
}
API_KEYS = {"deepseek": "DEEPSEEK_API_KEY", "qwen": "QWEN_API_KEY", "glm": "GLM_API_KEY"}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def describe_error(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(describe_error(child) for child in error.exceptions)
    return f"{type(error).__name__}: {error}"


def vendor(model: str) -> str:
    name = model.casefold()
    if name.startswith("glm"):
        return "glm"
    if name.startswith("qwen"):
        return "qwen"
    return "deepseek"


def model_endpoint(model: str, override: str | None = None) -> str:
    return override or DEFAULT_ENDPOINTS[vendor(model)]


def api_key(name: str | None = None, model: str = "deepseek-flash") -> str:
    name = name or API_KEYS[vendor(model)]
    key = os.environ.get(name)
    if not key and sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry:
            try:
                key = winreg.QueryValueEx(registry, name)[0]
            except FileNotFoundError:
                pass
    if not key:
        raise ValueError("请在用户环境变量中设置 " + name)
    return key


def thinking_payload(model: str) -> dict[str, Any]:
    """Return the vendor-specific thinking switch for a model.

    GLM always reasons (its API rejects ``thinking.type=disabled`` with 1210),
    so it gets the lowest supported effort instead.  Qwen and DeepSeek keep
    their non-thinking modes.
    """
    if model.casefold().startswith("glm"):
        return {"reasoning_effort": "low"}
    if model.casefold().startswith("qwen"):
        return {"enable_thinking": False}
    return {"thinking": {"type": "disabled"}}


def thinking_enabled(model: str) -> bool:
    return model.casefold().startswith("glm")


def thinking_mode(model: str) -> str:
    return "reasoning_effort=low" if model.casefold().startswith("glm") else "disabled"


async def request_model(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    key: str,
    record: Path | None = None,
    step: int | None = None,
    meta: dict[str, Any] | None = None,
    retries: int = 0,
    endpoint: str = DEFAULT_ENDPOINTS["deepseek"],
) -> httpx.Response:
    """Retry only HTTP transport failures, never a model-issued tool call."""
    for attempt in range(retries + 1):
        if meta is not None:
            meta["api_attempts"] = meta.get("api_attempts", 0) + 1
        try:
            return await client.post(
                endpoint,
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
        except httpx.TransportError as error:
            if record is not None:
                event = {
                    "step": step,
                    "attempt": attempt + 1,
                    "error": describe_error(error),
                    "retrying": attempt < retries,
                }
                with (record / "transport_errors.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            if attempt == retries:
                raise
            print(f"模型连接中断，重试当前请求（{attempt + 1}/{retries}）。", flush=True)
            await asyncio.sleep(min(2 ** attempt, 4))
    raise RuntimeError("unreachable")
