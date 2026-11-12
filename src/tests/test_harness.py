"""Regression tests for the unified LangGraph harness (single topology only)."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx
from mcp.types import CallToolResult, TextContent

from harness import (
    AGENT_TOPOLOGY,
    JUDGE_TOPOLOGY,
    TOPOLOGIES,
    harness_metadata,
    run_agent,
    run_judge,
)
from harness.judge import run_judge_sync


def model_response(message, finish_reason):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://example.test/chat/completions"),
        json={"choices": [{"message": message, "finish_reason": finish_reason}]},
    )


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.calls.append((name, arguments))
        return CallToolResult(content=[TextContent(type="text", text="ok")])


class HarnessMetadataTests(unittest.TestCase):
    def test_metadata_names_langgraph_and_known_topologies(self):
        meta = harness_metadata()
        self.assertEqual(meta["name"], "langgraph")
        self.assertEqual(meta["topology"], AGENT_TOPOLOGY)
        self.assertEqual(TOPOLOGIES, (AGENT_TOPOLOGY, JUDGE_TOPOLOGY))
        self.assertEqual(AGENT_TOPOLOGY, "single_react")
        self.assertIsInstance(meta["version"], str)

    def test_unknown_topology_is_rejected(self):
        with self.assertRaises(ValueError):
            harness_metadata("multi_agent")

    def test_runner_can_stamp_two_agent_topologies(self):
        meta = harness_metadata("planner_executor",
                                extra_topologies=("planner_executor", "investigator_executor"))
        self.assertEqual(meta["topology"], "planner_executor")
        self.assertEqual(meta["name"], "langgraph")


class AgentGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.record = Path(self.temp.name) / "record"
        self.record.mkdir()
        self.run_root = Path(self.temp.name) / "run"
        self.run_root.mkdir()
        self.meta = {"tool_calls": 0, "model_calls": 0, "normal_model_calls": 0}
        self.events = self.record / "agentguard_events.jsonl"
        self.session = FakeSession()
        self.catalog = {"files__write_file": SimpleNamespace(description="", inputSchema={})}

    def tearDown(self):
        self.temp.cleanup()

    def run_graph(self, responses, **overrides):
        queue = list(responses)

        async def fake_request(client, payload, key, record, step, meta, retries=0, endpoint=""):
            return queue.pop(0)

        arguments = dict(
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            tools=[], model="deepseek-flash", endpoint="https://example.test",
            key="test", client=None, record=self.record, run_root=self.run_root,
            meta=self.meta, session=self.session, catalog_by_name=self.catalog,
            guard_events_path=self.events, max_steps=5, max_tool_calls=5,
            api_retries=0, specified_quit_enabled=False, model_request=fake_request,
        )
        arguments.update(overrides)
        return asyncio.run(run_agent(**arguments))

    def test_tool_turn_is_recorded_then_final_answer_ends(self):
        state = self.run_graph([
            model_response({"role": "assistant", "content": "",
                            "tool_calls": [tool_call("c1", "files__write_file", {"path": "a.txt"})]},
                           "tool_calls"),
            model_response({"role": "assistant", "content": "done"}, "stop"),
        ])
        self.assertTrue(state["done"])
        self.assertEqual((self.record / "final.md").read_text(encoding="utf-8"), "done")
        self.assertEqual(self.session.calls, [("files__write_file", {"path": "a.txt"})])
        self.assertEqual(self.meta["model_calls"], 2)
        self.assertEqual(self.meta["tool_calls"], 1)
        self.assertEqual(self.meta["termination_reason"], "final_response")
        self.assertTrue((self.record / "tool-001.json").exists())
        messages = json.loads((self.record / "messages.json").read_text(encoding="utf-8"))
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        self.assertEqual(tool_messages[-1]["tool_call_id"], "c1")
        self.assertTrue((self.record / "model-001-request.json").exists())

    def test_unknown_tool_is_reported_without_calling_mcp(self):
        state = self.run_graph([
            model_response({"role": "assistant", "content": "",
                            "tool_calls": [tool_call("c1", "missing__tool", {})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "end"}, "stop"),
        ])
        self.assertTrue(state["done"])
        self.assertEqual(self.session.calls, [])
        record = json.loads((self.record / "tool-001.json").read_text(encoding="utf-8"))
        self.assertTrue(record["result"]["isError"])

    def test_max_tool_calls_stops_the_graph(self):
        with self.assertRaisesRegex(RuntimeError, "最大工具调用次数"):
            self.run_graph([
                model_response({"role": "assistant", "content": "",
                                "tool_calls": [tool_call("c1", "files__write_file", {"path": "a.txt"})]},
                               "tool_calls"),
            ], max_tool_calls=0)
        self.assertEqual(self.meta["termination_reason"], "max_tool_calls")

    def test_max_steps_stops_the_graph(self):
        with self.assertRaisesRegex(RuntimeError, "最大模型调用轮数"):
            self.run_graph([
                model_response({"role": "assistant", "content": "",
                                "tool_calls": [tool_call("c1", "files__write_file", {"path": "a.txt"})]},
                               "tool_calls"),
                model_response({"role": "assistant", "content": "",
                                "tool_calls": [tool_call("c2", "files__write_file", {"path": "b.txt"})]},
                               "tool_calls"),
            ], max_steps=1)
        self.assertEqual(self.meta["termination_reason"], "max_steps")

    def test_specified_quit_terminates_before_any_tool_runs(self):
        state = self.run_graph([
            model_response({"role": "assistant", "content": "",
                            "tool_calls": [tool_call("q1", "quit", {"reason": "会泄露数据"})]},
                           "tool_calls"),
        ], specified_quit_enabled=True)
        self.assertTrue(state["done"])
        self.assertEqual(state["termination_reason"], "specified_quit")
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.meta["status"], "completed")
        self.assertTrue(self.meta["specified_quit"]["triggered"])
        self.assertTrue((self.record / "final.md").read_text(encoding="utf-8").startswith("QUIT: 会泄露数据"))


class JudgeGraphTests(unittest.TestCase):
    def test_async_judge_sends_one_request(self):
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(200, json={"ok": True})

        async def call():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await run_judge(
                    client, "https://judge.test/v1/chat/completions",
                    {"model": "judge", "messages": [{"role": "user", "content": "hi"}]},
                    {"api-key": "test"},
                )

        response = asyncio.run(call())
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(captured[0].headers["api-key"], "test")

    def test_sync_judge_adapter_uses_the_same_graph(self):
        def handler(request):
            return httpx.Response(200, json={"choices": []})

        response = run_judge_sync(
            "https://judge.test/v1/chat/completions",
            {"model": "judge"},
            {"Authorization": "Bearer test"},
            timeout=5,
            transport=httpx.MockTransport(handler),
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
