"""Tests for the fail-open async client used by the benchmark."""
from __future__ import annotations

import asyncio
import tempfile
import unittest

from securityEnhancement.AgentGuard.audit import AuditLog
from securityEnhancement.AgentGuard.client import check_tool_call
from securityEnhancement.AgentGuard.policy import Policy
from securityEnhancement.AgentGuard.server import GuardService

from .support import FakeReviewer, env, free_port, make_service, running_server

SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
    "required": ["path", "content"],
}


def check() -> object:
    return asyncio.run(
        check_tool_call(
            group="files",
            tool_name="files__write_file",
            arguments={"path": "报告/草稿.md", "content": "正文"},
            input_schema=SCHEMA,
            description="写入文件",
        )
    )


def deny_policy() -> Policy:
    return Policy.from_dict(
        {
            "version": "policy-v1",
            "rules": [
                {"id": "deny-writes", "effect": "deny", "priority": 10, "capabilities": ["file.write"]}
            ],
        }
    )


def allow_policy() -> Policy:
    return Policy.from_dict(
        {
            "version": "policy-v1",
            "rules": [{"id": "allow-writes", "effect": "allow", "priority": 10, "capabilities": ["file.write"]}],
        }
    )


class BadDecisionService(GuardService):
    def decide(self, payload):  # noqa: ANN001 - test double
        return {"decision": "maybe"}, 200


class ErrorService(GuardService):
    def decide(self, payload):  # noqa: ANN001 - test double
        return {"error": "boom"}, 500


class ClientFailOpenTests(unittest.TestCase):
    def test_default_timeout_covers_worst_observed_review(self):
        from securityEnhancement.AgentGuard import config

        # 70s was below four 90.7–152.8s reviews in the 2026-11-09 batch.
        self.assertGreaterEqual(config.DEFAULT_TIMEOUT_S, 180.0)
        self.assertGreater(config.DEFAULT_TIMEOUT_S, config.DEFAULT_MIMO_TIMEOUT_S)

    def test_server_not_started_is_fail_open(self):
        with tempfile.TemporaryDirectory(), env(
            AGENTGUARD_BASE_URL=f"http://127.0.0.1:{free_port()}", AGENTGUARD_TIMEOUT_S=0.2
        ):
            response = check()
            self.assertEqual(response.decision, "allow")
            self.assertTrue(response.fail_open)
            self.assertEqual(response.source, "fail_open")
            self.assertIn("fail-open", response.reason)
            self.assertTrue(response.reason.startswith("AgentGuard"))
            self.assertEqual(response.capabilities, ["file.write"])

    def test_server_deny_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, deny_policy())
            with running_server(service) as (_, base_url), env(AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2):
                response = check()
            self.assertEqual(response.decision, "deny")
            self.assertFalse(response.fail_open)
            self.assertEqual(response.rule_id, "deny-writes")
            self.assertEqual(response.source, "policy")

    def test_server_allow_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, allow_policy())
            with running_server(service) as (_, base_url), env(AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2):
                response = check()
            self.assertEqual(response.decision, "allow")
            self.assertFalse(response.fail_open)
            self.assertEqual(response.source, "policy")

    def test_missing_policy_is_fail_open_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            service = make_service(directory, Policy.load(None))
            with running_server(service) as (_, base_url), env(AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2):
                response = check()
            self.assertEqual(response.decision, "allow")
            self.assertTrue(response.fail_open)
            self.assertEqual(response.source, "policy_fail_open")

    def test_invalid_decision_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BadDecisionService(policy=Policy.load(None), reviewer=FakeReviewer(), audit=AuditLog(directory))
            with running_server(service) as (_, base_url), env(AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2):
                response = check()
            self.assertEqual(response.decision, "allow")
            self.assertTrue(response.fail_open)
            self.assertEqual(response.source, "fail_open")

    def test_http_error_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ErrorService(policy=Policy.load(None), reviewer=FakeReviewer(), audit=AuditLog(directory))
            with running_server(service) as (_, base_url), env(AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2):
                response = check()
            self.assertEqual(response.decision, "allow")
            self.assertTrue(response.fail_open)
            self.assertIn("HTTP 500", response.reason)


if __name__ == "__main__":
    unittest.main()
