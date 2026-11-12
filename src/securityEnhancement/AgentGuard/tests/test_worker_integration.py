"""Real stdio worker integration test for the deny / allow / continue path.

This uses the actual ``harness.worker`` MCP process and a fake model-facing
caller, so it verifies that a deny does not reach the real tool while the run
keeps working afterwards.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from securityEnhancement.AgentGuard import trajectory
from securityEnhancement.AgentGuard.policy import Policy

from .support import FakeReviewer, make_service, read_jsonl, running_server

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "初始环境" / "综合测试"
SRC = ROOT / "src"

POLICY = {
    "version": "policy-v1",
    "rules": [
        {
            "id": "worker-deny-file-write",
            "description": "集成测试：拒绝文件写入",
            "effect": "deny",
            "priority": 50,
            "tool_groups": ["files"],
            "capabilities": ["file.write"],
        }
    ],
}

REVIEW_POLICY = {
    "version": "policy-v1",
    "rules": [
        {
            "id": "worker-review-file-write",
            "description": "集成测试：写入需要复核",
            "effect": "llm_review",
            "priority": 50,
            "tool_groups": ["files"],
            "capabilities": ["file.write"],
            "llm_prompt": "只允许写入用户明确指定的文件。",
        }
    ],
}

_ENV_KEYS = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "USERPROFILE"}


def child_environment(base_url: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() in _ENV_KEYS}
    environment.update(
        PYTHONPATH=str(SRC),
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        AGENTGUARD_ENABLED="1",
        AGENTGUARD_BASE_URL=base_url,
        AGENTGUARD_TIMEOUT_S="10",
        AGENTGUARD_RUN_ID="worker-integration",
        AGENTGUARD_CASE="综合测试",
    )
    environment.update(extra or {})
    return environment


async def drive_worker(run_root: Path, base_url: str, extra_env: dict[str, str] | None = None):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-m", "harness.worker", "--run-root", str(run_root), "--groups", "files"],
        cwd=str(ROOT),
        env=child_environment(base_url, extra_env),
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            before = await session.call_tool("files__list_directory", {"path": "."})
            denied = await session.call_tool("files__write_file", {"path": "guard-check.txt", "content": "x"})
            after = await session.call_tool("files__list_directory", {"path": "."})
    return before, denied, after


class WorkerIntegrationTests(unittest.TestCase):
    def test_deny_blocks_the_real_tool_and_the_run_continues(self):
        if not SOURCE.is_dir():
            self.skipTest("初始环境/综合测试 not available")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            run_root = temp / "run"
            shutil.copytree(SOURCE, run_root)
            service = make_service(temp / "audit", Policy.from_dict(POLICY))
            with running_server(service) as (_, base_url):
                before, denied, after = asyncio.run(drive_worker(run_root, base_url))

            self.assertFalse(before.isError)
            self.assertTrue(denied.isError)
            blocked = json.loads(denied.content[0].text)
            self.assertEqual(blocked["agentguard"], "blocked")
            self.assertEqual(blocked["tool"], "files__write_file")
            self.assertEqual(blocked["decision"], "deny")
            self.assertIn("worker-deny-file-write", blocked["reason"])
            self.assertNotIn(str(run_root), blocked["reason"])
            self.assertFalse(after.isError)
            self.assertFalse((run_root / "workspace" / "guard-check.txt").exists())

            records = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            self.assertEqual(len(records), 3)
            self.assertEqual([record["decision"] for record in records], ["allow", "deny", "allow"])
            self.assertEqual(records[1]["policy"]["rule_id"], "worker-deny-file-write")
            self.assertEqual(records[0]["context"]["run_id"], "worker-integration")
            self.assertEqual(records[1]["context"]["case"], "综合测试")

    def test_reviewer_gets_recent_events_from_the_runner_feed(self):
        if not SOURCE.is_dir():
            self.skipTest("初始环境/综合测试 not available")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            run_root = temp / "run"
            shutil.copytree(SOURCE, run_root)
            feed = temp / "agentguard_events.jsonl"
            instruction = "把报告保存为 guard-check.txt"
            trajectory.append_event(feed, trajectory.llm_input_event([
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": instruction},
            ]))
            trajectory.append_event(feed, trajectory.tool_result_event(
                "files__read_document", {"content": [{"type": "text", "text": "源内容"}]},
            ))
            reviewer = FakeReviewer(decision="allow", reason="within instruction")
            service = make_service(temp / "audit", Policy.from_dict(REVIEW_POLICY), reviewer)
            with running_server(service) as (_, base_url):
                before, result, after = asyncio.run(drive_worker(
                    run_root, base_url,
                    {
                        "AGENTGUARD_EVENT_FEED": str(feed),
                        "AGENTGUARD_USER_INSTRUCTION": instruction,
                        "AGENTGUARD_REVIEW_TRACE_MAX_STEPS": "5",
                    },
                ))

            self.assertFalse(before.isError)
            self.assertFalse(result.isError)
            self.assertFalse(after.isError)
            self.assertEqual(len(reviewer.calls), 1)
            call = reviewer.calls[0]
            self.assertEqual(call["rule"].rule_prompt, "只允许写入用户明确指定的文件。")
            self.assertEqual(
                [event["event_type"] for event in call["recent_events"]],
                ["llm_input", "tool_result"],
            )
            self.assertEqual(call["recent_events"][0]["messages"][-1]["content"], instruction)
            records = read_jsonl(service.audit.run_dir, "decisions.jsonl")
            write_record = next(record for record in records if record["tool_name"] == "files__write_file")
            self.assertEqual(write_record["recent_events"], {"count": 2, "types": ["llm_input", "tool_result"]})
            audit_text = (service.audit.run_dir / "decisions.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(instruction, audit_text)


if __name__ == "__main__":
    unittest.main()
