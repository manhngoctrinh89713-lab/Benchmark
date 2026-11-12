"""Tests for the local AgentGuard HTTP server and decision engine."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

from securityEnhancement.AgentGuard.audit import AuditLog
from securityEnhancement.AgentGuard.policy import Policy
from securityEnhancement.AgentGuard.reviewer import Reviewer
from securityEnhancement.AgentGuard.server import GuardService

from .support import FakeReviewer, env, make_service, read_jsonl, running_server

ROOT = Path(__file__).resolve().parents[4]


def deny_policy() -> Policy:
    return Policy.from_dict(
        {
            "version": "policy-v1",
            "rules": [
                {
                    "id": "deny-writes",
                    "description": "禁止写文件",
                    "effect": "deny",
                    "priority": 10,
                    "capabilities": ["file.write"],
                }
            ],
        }
    )


def review_policy() -> Policy:
    return Policy.from_dict(
        {
            "version": "policy-v1",
            "rules": [{"id": "review-writes", "effect": "llm_review", "priority": 10, "capabilities": ["file.write"]}],
        }
    )


def payload(arguments: dict | None = None, principal: dict | None = None) -> dict:
    data = {
        "tool": {
            "group": "files",
            "name": "files__write_file",
            "description": "写入文件",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
        "arguments": arguments if arguments is not None else {"path": "报告/草稿.md", "content": "正文"},
        "context": {"run_id": "run-test", "case": "综合测试", "model": "deepseek-flash"},
    }
    if principal is not None:
        data["principal"] = principal
    return data


class ServerTests(unittest.TestCase):
    def test_healthz_reports_policy_and_reviewer_status(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, Policy.load(None))
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                response = client.get(base_url + "/healthz")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "ok")
            self.assertEqual(body["service"], "agentguard")
            self.assertEqual(body["policy"]["status"], "missing")
            self.assertFalse(body["policy"]["configured"])
            self.assertTrue(body["reviewer"]["configured"])
            self.assertEqual(body["reviewer"]["model"], "fake-reviewer")
            self.assertTrue(body["audit"]["enabled"])

    def test_healthz_unknown_path_is_404(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                self.assertEqual(client.get(base_url + "/nope").status_code, 404)

    def test_decide_without_policy_is_fail_open_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, Policy.load(None))
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                response = client.post(base_url + "/v1/guard/decide", json=payload())
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["decision"], "allow")
            self.assertTrue(body["fail_open"])
            self.assertEqual(body["source"], "policy_fail_open")
            self.assertEqual(body["capabilities"], ["file.write"])
            self.assertEqual(body["risk_level"], "medium")
            decisions = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["tool_name"], "files__write_file")
            self.assertEqual(decisions[0]["context"]["case"], "综合测试")
            self.assertIn("latency_ms", decisions[0])
            self.assertTrue(decisions[0]["fail_open"])
            errors = read_jsonl(service.audit.run_dir, "errors.jsonl")
            self.assertEqual(errors[0]["event"], "policy_not_loaded")

    def test_decide_deny(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, deny_policy())
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                body = client.post(base_url + "/v1/guard/decide", json=payload()).json()
            self.assertEqual(body["decision"], "deny")
            self.assertFalse(body["fail_open"])
            self.assertEqual(body["source"], "policy")
            self.assertEqual(body["rule_id"], "deny-writes")
            decisions = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertEqual(decisions[0]["policy"]["effect"], "deny")
            self.assertEqual(decisions[0]["decision"], "deny")

    def test_decide_with_invalid_policy_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Policy.from_dict({"version": "policy-v1", "rules": [{"id": "x", "effect": "block"}]})
            service = make_service(directory, invalid)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                health = client.get(base_url + "/healthz").json()
                body = client.post(base_url + "/v1/guard/decide", json=payload()).json()
            self.assertEqual(health["policy"]["status"], "invalid")
            self.assertEqual(body["decision"], "allow")
            self.assertTrue(body["fail_open"])

    def test_llm_review_deny(self):
        with tempfile.TemporaryDirectory() as directory:
            reviewer = FakeReviewer(decision="deny", reason="外发风险")
            service = make_service(directory, review_policy(), reviewer)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                body = client.post(base_url + "/v1/guard/decide", json=payload()).json()
            self.assertEqual(body["decision"], "deny")
            self.assertFalse(body["fail_open"])
            self.assertEqual(body["source"], "reviewer")
            self.assertEqual(len(reviewer.calls), 1)
            self.assertEqual(reviewer.calls[0]["metadata"].capabilities, ["file.write"])
            self.assertEqual(reviewer.calls[0]["rule"].rule_id, "review-writes")
            reviews = read_jsonl(service.audit.run_dir, "reviews.jsonl")
            self.assertEqual(reviews[0]["decision"], "deny")
            self.assertEqual(reviews[0]["ok"], True)

    def test_llm_review_failure_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            reviewer = FakeReviewer(decision="allow", ok=False, fail_open=True, reason="reviewer 超时；fail-open")
            service = make_service(directory, review_policy(), reviewer)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                body = client.post(base_url + "/v1/guard/decide", json=payload()).json()
            self.assertEqual(body["decision"], "allow")
            self.assertTrue(body["fail_open"])
            self.assertEqual(body["source"], "reviewer_fail_open")

    def test_reviewer_exception_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            reviewer = FakeReviewer(raises=RuntimeError("boom"))
            service = make_service(directory, review_policy(), reviewer)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                body = client.post(base_url + "/v1/guard/decide", json=payload()).json()
            self.assertEqual(body["decision"], "allow")
            self.assertTrue(body["fail_open"])
            self.assertIn("reviewer", body["reason"])

    def test_bad_requests_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory)
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                self.assertEqual(client.post(base_url + "/v1/guard/decide", content=b"{oops").status_code, 400)
                self.assertEqual(client.post(base_url + "/v1/guard/decide", json={"tool": {}}).status_code, 400)
                bad_arguments = payload()
                bad_arguments["arguments"] = ["not", "a", "dict"]
                self.assertEqual(client.post(base_url + "/v1/guard/decide", json=bad_arguments).status_code, 400)

    def test_principal_is_fixed_server_side(self):
        policy = Policy.from_dict(
            {
                "version": "policy-v1",
                "rules": [
                    {
                        "id": "medium-trust-only",
                        "effect": "deny",
                        "priority": 1,
                        "conditions": {
                            "all": [{"field": "principal.trust_level", "op": "eq", "value": 2}]
                        },
                    }
                ],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, policy)
            elevated = {"role": "default", "trust_level": 4, "trust_scale": [0, 1, 2, 3, 4], "label": "high_trust"}
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                body = client.post(base_url + "/v1/guard/decide", json=payload(principal=elevated)).json()
            self.assertEqual(body["decision"], "deny")
            decisions = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertTrue(decisions[0]["principal_ignored"])
            self.assertEqual(decisions[0]["principal"]["trust_level"], 2)

    def test_audit_redacts_arguments_and_never_stores_api_key(self):
        secret_key = "sk-mimo-should-never-appear"
        with tempfile.TemporaryDirectory() as directory, env(MIMO_BASE_URL=None, MIMO_API_KEY=secret_key):
            reviewer = Reviewer()
            service = GuardService(policy=review_policy(), reviewer=reviewer, audit=AuditLog(directory))
            arguments = {"path": "报告/草稿.md", "content": "正文", "token": "super-secret-token",
                         "password": "hunter2"}
            with running_server(service) as (_, base_url), httpx.Client(trust_env=False, timeout=5) as client:
                health = client.get(base_url + "/healthz")
                body = client.post(base_url + "/v1/guard/decide", json=payload(arguments=arguments)).json()
            self.assertEqual(body["decision"], "allow")
            self.assertTrue(body["fail_open"])
            self.assertNotIn(secret_key, health.text)
            self.assertNotIn(secret_key, json.dumps(body))
            for name in ("server.jsonl", "decisions.jsonl", "reviews.jsonl", "errors.jsonl"):
                path = service.audit.run_dir / name
                if path.is_file():
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn(secret_key, text, name)
                    self.assertNotIn("super-secret-token", text, name)
                    self.assertNotIn("hunter2", text, name)
            decisions = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertEqual(decisions[0]["arguments"]["token"], "[redacted]")
            self.assertEqual(decisions[0]["arguments"]["password"], "[redacted]")

    def test_recent_events_are_sent_to_reviewer_but_not_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            reviewer = FakeReviewer(decision="allow", reason="ok")
            service = make_service(directory, review_policy(), reviewer)
            request = payload()
            instruction = "把报告保存为 报告/草稿.md"
            events = [
                {"event_type": "llm_input", "messages": [{"role": "user", "content": instruction}]},
                {"event_type": "tool_result", "tool_name": "files__read_document", "result": "工具结果-XYZ"},
            ]
            request["recent_events"] = events
            response, status = service.decide(request)
            self.assertEqual(status, 200)
            self.assertEqual(response["decision"], "allow")
            self.assertEqual(reviewer.calls[0]["recent_events"], events)
            decisions = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertEqual(decisions[0]["recent_events"]["count"], 2)
            self.assertEqual(decisions[0]["recent_events"]["types"], ["llm_input", "tool_result"])
            audit_text = (service.audit.run_dir / "decisions.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(instruction, audit_text)
            self.assertNotIn("工具结果-XYZ", audit_text)

    def test_start_and_stop_events_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory)
            with running_server(service):
                pass
            events = read_jsonl(service.audit.run_dir, "server.jsonl")
            self.assertEqual(events[0]["event"], "start")
            self.assertEqual(events[-1]["event"], "stop")


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-B", "-m", "securityEnhancement.AgentGuard", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=60,
        )

    def test_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AgentGuard", result.stdout)

    def test_invalid_port_is_rejected(self):
        result = self.run_cli("--port", "70000")
        self.assertNotEqual(result.returncode, 0)

    def test_non_loopback_host_is_rejected(self):
        result = self.run_cli("--host", "0.0.0.0", "--port", "38080")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("localhost", result.stderr)


if __name__ == "__main__":
    unittest.main()
