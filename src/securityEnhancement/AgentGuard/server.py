"""Local AgentGuard server (HTTP on 127.0.0.1).

Endpoints
---------
``GET /healthz``
    Service, policy and reviewer status.
``POST /v1/guard/decide``
    Classify one public tool call, evaluate the JSON policy, optionally call the
    fixed LLM reviewer and return ``allow`` / ``deny``.

Every failure inside the decision path is fail-open: the response is ``allow``
with ``fail_open: true`` and the error is written to ``errors.jsonl``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from . import config
from .audit import AuditLog, sanitize, sanitize_arguments
from .metadata import classify
from .models import DEFAULT_PRINCIPAL, GuardRequest, ReviewDecision
from .policy import Policy
from .reviewer import Reviewer

MAX_BODY_BYTES = 2_000_000


class GuardService:
    """Stateless decision engine shared by all request handler threads."""

    def __init__(
        self,
        *,
        policy: Policy | None = None,
        reviewer: Reviewer | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.policy = policy if policy is not None else Policy.load(config.policy_path())
        self.reviewer = reviewer if reviewer is not None else Reviewer()
        self.audit = audit if audit is not None else AuditLog()
        self.started_at = datetime.now().astimezone().isoformat()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle / health
    # ------------------------------------------------------------------
    def start(self, host: str, port: int) -> None:
        if self._started:
            return
        self._started = True
        self.audit.server(
            {
                "event": "start",
                "service": config.SERVICE_NAME,
                "version": config.SERVICE_VERSION,
                "host": host,
                "port": port,
                "policy": self.policy.health(),
                "reviewer": self._reviewer_health(),
                "audit_dir": str(self.audit.run_dir) if self.audit.run_dir else None,
            }
        )
        if self.policy.status != "ok":
            self.audit.error(
                {
                    "event": "policy_not_loaded",
                    "status": self.policy.status,
                    "path": self.policy.path,
                    "error": self.policy.error,
                    "effect": "fail-open",
                }
            )

    def stop(self) -> None:
        self.audit.server({"event": "stop", "service": config.SERVICE_NAME})

    def _reviewer_health(self) -> dict[str, Any]:
        health = getattr(self.reviewer, "health", None)
        if callable(health):
            return health()
        return {"configured": bool(getattr(self.reviewer, "configured", False))}

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": config.SERVICE_NAME,
            "version": config.SERVICE_VERSION,
            "started_at": self.started_at,
            "policy": self.policy.health(),
            "reviewer": self._reviewer_health(),
            "audit": {
                "enabled": self.audit.enabled,
                "dir": str(self.audit.run_dir) if self.audit.run_dir else None,
            },
        }

    # ------------------------------------------------------------------
    # Decision path
    # ------------------------------------------------------------------
    def decide(self, payload: Any) -> tuple[dict[str, Any], int]:
        if not isinstance(payload, dict):
            return {"error": "请求体必须是 JSON 对象"}, 400
        try:
            request = GuardRequest.model_validate(payload)
        except ValidationError as error:
            return {"error": "请求格式非法", "detail": str(error)[:500]}, 400

        request_id = uuid4().hex
        started = time.perf_counter()
        metadata = classify(
            request.tool.group,
            request.tool.name,
            request.tool.description,
            request.tool.input_schema,
        )
        principal = DEFAULT_PRINCIPAL.model_copy(deep=True)
        client_principal = request.principal.model_dump()
        principal_ignored = client_principal != DEFAULT_PRINCIPAL.model_dump()

        try:
            policy_decision = self.policy.evaluate(
                principal=principal,
                metadata=metadata,
                arguments=request.arguments,
                context=request.context,
                tool_description=request.tool.description,
            )
            review: ReviewDecision | None = None
            if policy_decision.effect == "llm_review":
                review = self._review(
                    principal=principal,
                    metadata=metadata,
                    arguments=request.arguments,
                    context=request.context,
                    policy_decision=policy_decision,
                    recent_events=request.recent_events,
                )
                if not review.ok:
                    decision, fail_open = "allow", True
                    source = "reviewer_fail_open"
                    reason = review.reason
                elif review.decision == "deny":
                    decision, fail_open = "deny", False
                    source = "reviewer"
                    reason = review.reason or policy_decision.reason
                else:
                    decision, fail_open = "allow", False
                    source = "reviewer"
                    reason = review.reason or policy_decision.reason
            elif policy_decision.effect == "deny":
                decision, fail_open = "deny", False
                source = "policy"
                reason = policy_decision.reason
            else:
                decision, fail_open = "allow", policy_decision.fail_open
                source = "policy_fail_open" if policy_decision.fail_open else ("policy" if policy_decision.matched else "default")
                reason = policy_decision.reason
        except Exception as error:  # noqa: BLE001 - decision path is fail-open
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            self.audit.error(
                {
                    "event": "internal_error",
                    "request_id": request_id,
                    "error_type": type(error).__name__,
                    "message": str(error)[:500],
                    "effect": "fail-open",
                }
            )
            response = self._response(
                decision="allow",
                reason=f"AgentGuard internal error; fail-open ({type(error).__name__})",
                fail_open=True,
                source="fail_open",
                request_id=request_id,
                metadata=metadata,
                latency_ms=latency_ms,
            )
            self.audit.decision(self._decision_event(request, response, metadata, None, None, principal_ignored))
            return response, 200

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        response = self._response(
            decision=decision,
            reason=reason,
            fail_open=fail_open,
            source=source,
            request_id=request_id,
            metadata=metadata,
            latency_ms=latency_ms,
            rule_id=policy_decision.rule_id,
        )
        self.audit.decision(
            self._decision_event(request, response, metadata, policy_decision, review, principal_ignored)
        )
        if review is not None:
            self.audit.review(
                {
                    "event": "review",
                    "request_id": request_id,
                    "group": metadata.group,
                    "tool_name": metadata.tool_name,
                    "rule_id": policy_decision.rule_id,
                    "model": review.model,
                    "ok": review.ok,
                    "decision": review.decision,
                    "reason": review.reason,
                    "fail_open": review.fail_open,
                    "error": review.error,
                }
            )
        return response, 200

    def _review(
        self,
        *,
        principal: Any,
        metadata: Any,
        arguments: dict[str, Any],
        context: dict[str, Any],
        policy_decision: Any,
        recent_events: list[dict[str, Any]] | None = None,
    ) -> ReviewDecision:
        try:
            return self.reviewer.review(
                principal=principal,
                metadata=metadata,
                arguments=arguments,
                rule=policy_decision,
                context=context,
                recent_events=recent_events or [],
            )
        except Exception as error:  # noqa: BLE001 - reviewer failures are fail-open
            return ReviewDecision(
                decision="allow",
                reason=f"reviewer 异常（{type(error).__name__}）；fail-open",
                fail_open=True,
                ok=False,
                model=getattr(self.reviewer, "model", ""),
                error=type(error).__name__,
            )

    @staticmethod
    def _response(
        *,
        decision: str,
        reason: str,
        fail_open: bool,
        source: str,
        request_id: str,
        metadata: Any,
        latency_ms: float,
        rule_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "decision": decision,
            "reason": reason,
            "fail_open": fail_open,
            "source": source,
            "rule_id": rule_id,
            "capabilities": list(metadata.capabilities),
            "risk_level": metadata.risk_level,
            "side_effect": metadata.side_effect,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "metadata": {
                "classifier_version": metadata.classifier_version,
                "classifier_fallback": metadata.fallback,
                "classifier_basis": metadata.basis,
                "group": metadata.group,
            },
        }

    @staticmethod
    def _audit_context(context: dict[str, Any]) -> dict[str, Any]:
        """Keep the user instruction out of the audit log, but record its size."""
        audited = {key: value for key, value in context.items() if key != "user_instruction"}
        instruction = str(context.get("user_instruction") or "")
        if instruction:
            audited["user_instruction_chars"] = len(instruction)
        return audited

    @staticmethod
    def _decision_event(
        request: GuardRequest,
        response: dict[str, Any],
        metadata: Any,
        policy_decision: Any,
        review: ReviewDecision | None,
        principal_ignored: bool,
    ) -> dict[str, Any]:
        return {
            "event": "decision",
            "request_id": response["request_id"],
            "context": sanitize(GuardService._audit_context(request.context)),
            "principal": DEFAULT_PRINCIPAL.model_dump(),
            "principal_ignored": principal_ignored,
            "group": metadata.group,
            "tool_name": metadata.tool_name,
            "capabilities": list(metadata.capabilities),
            "side_effect": metadata.side_effect,
            "risk_level": metadata.risk_level,
            "classifier": {
                "version": metadata.classifier_version,
                "fallback": metadata.fallback,
                "basis": metadata.basis,
            },
            "arguments": sanitize_arguments(request.arguments),
            "recent_events": {
                "count": len(request.recent_events),
                "types": [
                    str(event.get("event_type"))
                    for event in request.recent_events
                    if isinstance(event, dict)
                ],
            },
            "policy": policy_decision.model_dump() if policy_decision is not None else None,
            "review": review.model_dump() if review is not None else None,
            "decision": response["decision"],
            "reason": response["reason"],
            "fail_open": response["fail_open"],
            "source": response["source"],
            "latency_ms": response["latency_ms"],
        }


class GuardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: GuardService) -> None:
        self.service = service
        super().__init__(address, GuardRequestHandler)


class GuardRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"AgentGuard/{config.SERVICE_VERSION}"

    def handle_one_request(self) -> None:
        # httpx opens a fresh client per decision, so the peer may reset a
        # keep-alive connection between requests.  That is normal shutdown
        # traffic, not a decision-path error; keep stderr free of tracebacks.
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = urlsplit(self.path).path
        if path in {"/healthz", "/health"}:
            self._send_json(200, self.server.service.health())
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        path = urlsplit(self.path).path
        if path != "/v1/guard/decide":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._send_json(400, {"error": "缺少请求体"})
            return
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "请求体过大"})
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except ValueError:
            self._send_json(400, {"error": "请求体不是合法 JSON"})
            return
        result, status = self.server.service.decide(payload)
        self._send_json(status, result)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - http.server API
        # The decision path writes structured audit records; keep stderr quiet.
        return


def create_server(
    host: str = config.DEFAULT_HOST,
    port: int = config.DEFAULT_PORT,
    service: GuardService | None = None,
) -> GuardHTTPServer:
    service = service if service is not None else GuardService()
    server = GuardHTTPServer((host, port), service)
    service.start(host, server.server_address[1])
    return server


def serve(
    host: str = config.DEFAULT_HOST,
    port: int = config.DEFAULT_PORT,
    service: GuardService | None = None,
) -> None:
    server = create_server(host, port, service)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    print(f"AgentGuard 服务：http://{bound_host}:{bound_port}", flush=True)
    print(f"healthz：http://{bound_host}:{bound_port}/healthz", flush=True)
    print(f"policy：{service_status(server.service.policy)}", flush=True)
    print(f"审计目录：{server.service.audit.run_dir}", flush=True)
    print(f"reviewer：{server.service._reviewer_health().get('model', 'unknown')}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("AgentGuard 服务停止。", flush=True)
    finally:
        server.server_close()
        server.service.stop()


def service_status(policy: Policy) -> str:
    if policy.status == "ok":
        return f"已加载 {len(policy.rules)} 条规则（{policy.path}）"
    if policy.path:
        return f"{policy.status}（{policy.path}）：{policy.error}；fail-open"
    return "未配置（fail-open）"
