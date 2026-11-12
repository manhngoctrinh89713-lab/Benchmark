"""End-to-end test of the thin ToolInterface hook.

Uses a fake MCP server so the test verifies the real ``ToolInterface.call``
path: deny must not execute the downstream tool, allow must execute it and a
Guard outage must fail-open.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp.types import TextContent

from securityEnhancement.AgentGuard.policy import Policy
from harness.interface import ToolInterface

from .support import env, free_port, make_service, running_server

TOOL = SimpleNamespace(
    name="write_file",
    description="写入文件",
    inputSchema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
)
ARGUMENTS = {"path": "out/a.txt", "content": "正文"}


class FakeServer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return [TextContent(type="text", text="ok")], None


def build_interface(root: Path) -> tuple[ToolInterface, FakeServer]:
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    interface = ToolInterface(root, {})
    server = FakeServer()
    interface.routes["files__write_file"] = ("files", server, TOOL)
    interface.tools = [TOOL]
    return interface, server


def call(interface: ToolInterface):
    return asyncio.run(interface.call("files__write_file", dict(ARGUMENTS)))


def deny_policy() -> Policy:
    return Policy.from_dict(
        {
            "version": "policy-v1",
            "rules": [
                {
                    "id": "deny-files-write",
                    "description": "本实验禁止写入文件",
                    "effect": "deny",
                    "priority": 10,
                    "tool_groups": ["files"],
                    "capabilities": ["file.write"],
                }
            ],
        }
    )


class InterfaceGuardTests(unittest.TestCase):
    def test_deny_does_not_execute_the_real_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            interface, server = build_interface(root)
            service = make_service(Path(directory) / "audit", deny_policy())
            with running_server(service) as (_, base_url), env(
                AGENTGUARD_ENABLED=1, AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2
            ):
                result = call(interface)
            self.assertTrue(result.isError)
            self.assertEqual(server.calls, [])
            blocked = json.loads(result.content[0].text)
            self.assertEqual(blocked["agentguard"], "blocked")
            self.assertEqual(blocked["tool"], "files__write_file")
            self.assertEqual(blocked["decision"], "deny")
            self.assertIn("deny-files-write", blocked["reason"])
            self.assertNotIn(str(root), blocked["reason"])

    def test_allow_executes_the_real_tool_with_mapped_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            interface, server = build_interface(root)
            service = make_service(Path(directory) / "audit", Policy.from_dict({"version": "policy-v1", "rules": []}))
            with running_server(service) as (_, base_url), env(
                AGENTGUARD_ENABLED=1, AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2
            ):
                result = call(interface)
            self.assertFalse(result.isError)
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(server.calls[0][0], "write_file")
            self.assertTrue(server.calls[0][1]["path"].endswith("a.txt"))
            self.assertIn("workspace", server.calls[0][1]["path"])
            self.assertIn("ok", result.content[0].text)

    def test_non_matching_policy_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            interface, server = build_interface(root)
            policy = Policy.from_dict(
                {
                    "version": "policy-v1",
                    "rules": [
                        {
                            "id": "deny-commerce",
                            "effect": "deny",
                            "priority": 10,
                            "capabilities": ["commerce.transaction"],
                        }
                    ],
                }
            )
            service = make_service(Path(directory) / "audit", policy)
            with running_server(service) as (_, base_url), env(
                AGENTGUARD_ENABLED=1, AGENTGUARD_BASE_URL=base_url, AGENTGUARD_TIMEOUT_S=2
            ):
                result = call(interface)
            self.assertFalse(result.isError)
            self.assertEqual(len(server.calls), 1)

    def test_disabled_guard_executes_the_real_tool_without_calling_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            interface, server = build_interface(root)
            with env(
                AGENTGUARD_ENABLED="0",
                AGENTGUARD_BASE_URL=f"http://127.0.0.1:{free_port()}",
                AGENTGUARD_TIMEOUT_S=0.5,
            ):
                result = call(interface)
            self.assertFalse(result.isError)
            self.assertEqual(len(server.calls), 1)

    def test_guard_unavailable_is_fail_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            interface, server = build_interface(root)
            with env(AGENTGUARD_BASE_URL=f"http://127.0.0.1:{free_port()}", AGENTGUARD_TIMEOUT_S=0.5):
                result = call(interface)
            self.assertFalse(result.isError)
            self.assertEqual(len(server.calls), 1)


if __name__ == "__main__":
    unittest.main()
