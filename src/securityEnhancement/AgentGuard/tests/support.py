"""Shared helpers for the AgentGuard test suite."""
from __future__ import annotations

import contextlib
import os
import socket
import threading
from pathlib import Path
from typing import Any

from securityEnhancement.AgentGuard.audit import AuditLog
from securityEnhancement.AgentGuard.models import ReviewDecision
from securityEnhancement.AgentGuard.policy import Policy
from securityEnhancement.AgentGuard.server import GuardService, create_server


class FakeReviewer:
    """Deterministic stand-in for the Mimo reviewer."""

    configured = True
    model = "fake-reviewer"
    thinking_mode = "none"

    def __init__(
        self,
        decision: str = "allow",
        reason: str = "fake review",
        ok: bool = True,
        fail_open: bool = False,
        error: str | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.ok = ok
        self.fail_open = fail_open
        self.error = error
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        return {"configured": True, "model": self.model, "thinking_mode": self.thinking_mode, "timeout_s": 1.0}

    def review(self, **kwargs: Any) -> ReviewDecision:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return ReviewDecision(
            decision=self.decision,  # type: ignore[arg-type]
            reason=self.reason,
            ok=self.ok,
            fail_open=self.fail_open,
            model=self.model,
            error=self.error,
        )


def make_service(tmp: str | Path, policy: Policy | None = None, reviewer: Any | None = None) -> GuardService:
    return GuardService(
        policy=policy if policy is not None else Policy.load(None),
        reviewer=reviewer if reviewer is not None else FakeReviewer(),
        audit=AuditLog(tmp),
    )


@contextlib.contextmanager
def running_server(service: GuardService):
    server = create_server("127.0.0.1", 0, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        service.stop()
        thread.join(timeout=5)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def env(**values: Any):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def read_jsonl(directory: Path, name: str) -> list[dict[str, Any]]:
    import json

    path = directory / name
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
