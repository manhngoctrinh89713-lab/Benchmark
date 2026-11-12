import argparse
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from harness import runner
from securityEnhancement.QuittingAgents import (
    QUIT_TOOL_NAME,
    build_specified_quit_prompt,
    find_quit_call,
    parse_quit_call,
    parse_text_quit,
    quit_tool_definition,
)
from securityEnhancement.QuittingAgents.summary import summarize_runs


class SpecifiedQuitHelperTests(unittest.TestCase):
    def test_prompt_contains_upstream_conditions_and_safe_probe_exception(self):
        prompt = build_specified_quit_prompt()
        self.assertIn("You MUST quit in any of the following situations", prompt)
        self.assertIn("other actions you could take that are clearly safe", prompt)
        self.assertIn("call only the `quit` tool", prompt)

    def test_quit_tool_schema_is_terminal_and_requires_reason(self):
        definition = quit_tool_definition()["function"]
        self.assertEqual(definition["name"], QUIT_TOOL_NAME)
        self.assertEqual(definition["parameters"]["required"], ["reason"])
        self.assertIn("Terminate the task", definition["description"])

    def test_find_quit_call_detects_quit_anywhere_in_batch(self):
        calls = [
            {"id": "read", "type": "function", "function": {
                "name": "files__directory_tree", "arguments": "{}"}},
            {"id": "quit", "type": "function", "function": {
                "name": QUIT_TOOL_NAME, "arguments": json.dumps({
                    "reason": "缺少存放目录",
                    "question": "请指定归档目录",
                    "missing_information": ["归档路径"],
                }, ensure_ascii=False)}},
        ]
        self.assertEqual(find_quit_call(calls)["id"], "quit")
        parsed = parse_quit_call(find_quit_call(calls))
        self.assertEqual(parsed["reason"], "缺少存放目录")
        self.assertEqual(parsed["question"], "请指定归档目录")
        self.assertEqual(parsed["missing_information"], ["归档路径"])
        self.assertFalse(parsed["reason_missing"])

    def test_text_protocol_fallback_requires_prefix(self):
        parsed = parse_text_quit("  QUIT: 无法确认收货批次，请补充信息")
        self.assertEqual(parsed["source"], "text")
        self.assertEqual(parsed["reason"], "无法确认收货批次，请补充信息")
        self.assertIsNone(parse_text_quit("我会考虑 QUIT: 但不退出"))

    def test_summary_counts_quit_and_clarification(self):
        runs = [
            {"run_id": "1", "method": "specified_quit", "status": "completed",
             "category": "RU", "instruction_type": "test",
             "specified_quit": {"triggered": True, "source": "tool", "question": "哪个版本？",
                                "missing_information": [], "tool_calls_before": 2}},
            {"run_id": "2", "method": "specified_quit", "status": "completed",
             "category": "RU", "instruction_type": "standard",
             "specified_quit": {"triggered": False}},
            {"run_id": "3", "method": "specified_quit", "status": "failed",
             "category": "RU", "instruction_type": "test",
             "specified_quit": {"triggered": False}},
        ]
        summary = summarize_runs(runs)
        self.assertEqual(summary["valid_runs"], 2)
        self.assertEqual(summary["invalid_runs"], 1)
        self.assertEqual(summary["quit"], 1)
        self.assertEqual(summary["clarification_quit"], 1)
        self.assertEqual(summary["quit_rate_pct"], 50.0)


class SpecifiedQuitRunnerTests(unittest.TestCase):
    def test_mixed_batch_with_quit_executes_no_tools(self):
        run_id = "test-quit-" + uuid4().hex
        args = argparse.Namespace(
            model="deepseek-flash", endpoint=None, case="种子44", groups=None, user=None,
            variant="ri_test", max_tool_calls=50, max_steps=3, no_proxy=True,
            api_retries=0, dry_run=False, reset_only=False, batch_id=None, run_id=run_id,
            specified_quit=True,
        )
        calls = [
            {"id": "read", "type": "function", "function": {
                "name": "files__directory_tree", "arguments": "{}"}},
            {"id": "quit", "type": "function", "function": {
                "name": QUIT_TOOL_NAME, "arguments": json.dumps({
                    "reason": "缺少安全的归档目标",
                    "question": "请确认允许使用的归档目录",
                    "missing_information": ["安全的归档目录"],
                }, ensure_ascii=False)}},
        ]
        response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test"),
            json={"choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": "", "tool_calls": calls,
            }}]},
        )
        with patch.object(runner, "api_key", return_value="test"), patch.object(
            runner, "request_model", new=AsyncMock(return_value=response)
        ) as request_model:
            asyncio.run(runner.execute_locked(args))

        record = runner.ROOT / "运行记录" / run_id
        meta = json.loads((record / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["method"], "specified_quit")
        self.assertEqual(meta["status"], "completed")
        self.assertEqual(meta["termination_reason"], "specified_quit")
        self.assertEqual(meta["tool_calls"], 0)
        self.assertTrue(meta["specified_quit"]["triggered"])
        self.assertTrue(meta["specified_quit"]["mixed_with_other_calls"])
        self.assertEqual(meta["specified_quit"]["ignored_tool_calls"], ["files__directory_tree"])
        self.assertFalse((record / "tool-001.json").exists())
        self.assertTrue((record / "specified-quit.json").exists())
        self.assertTrue((record / "final.md").read_text(encoding="utf-8").startswith("QUIT:"))
        payload = request_model.await_args.args[1]
        self.assertIn("Specified Quit Instructions", payload["messages"][0]["content"])
        self.assertIn(QUIT_TOOL_NAME, [item["function"]["name"] for item in payload["tools"]])


if __name__ == "__main__":
    unittest.main()
