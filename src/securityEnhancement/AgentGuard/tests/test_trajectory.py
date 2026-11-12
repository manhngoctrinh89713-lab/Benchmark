"""Tests for the recent-event projection used by the reviewer prompt."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from securityEnhancement.AgentGuard import config, trajectory

from .support import env


class ProjectionTests(unittest.TestCase):
    def test_llm_input_keeps_user_instruction_and_truncates_other_messages(self):
        messages = [
            {"role": "system", "content": "s" * 1000},
            {"role": "user", "content": "u" * (config.MAX_USER_INSTRUCTION_CHARS + 100)},
            {"role": "assistant", "content": "a" * 1000,
             "tool_calls": [{"function": {"name": "files__read_document",
                                          "arguments": "{\"path\": \"a.txt\"}"}}]},
        ]
        event = trajectory.llm_input_event(messages)
        self.assertEqual(event["event_type"], "llm_input")
        self.assertEqual(len(event["messages"]), 3)
        self.assertEqual(len(event["messages"][0]["content"]), trajectory.EVENT_CONTENT_MAX_CHARS)
        self.assertEqual(len(event["messages"][1]["content"]), config.MAX_USER_INSTRUCTION_CHARS)
        self.assertEqual(len(event["messages"][2]["content"]), trajectory.EVENT_CONTENT_MAX_CHARS)
        self.assertEqual(event["messages"][2]["tool_calls"][0]["name"], "files__read_document")

    def test_llm_input_contains_the_full_conversation(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
        ] + [{"role": "assistant", "content": f"a{index}"} for index in range(12)]
        event = trajectory.llm_input_event(messages)
        self.assertEqual(len(event["messages"]), len(messages))
        self.assertEqual(event["messages"][0]["role"], "system")
        self.assertEqual(event["messages"][1]["role"], "user")
        self.assertEqual(event["messages"][1]["content"], "task")

    def test_llm_output_projection(self):
        event = trajectory.llm_output_event({
            "role": "assistant",
            "content": "x" * 1000,
            "tool_calls": [{"function": {"name": "files__write_file", "arguments": "{\"path\": \"a.txt\"}"}}],
        })
        self.assertEqual(event["event_type"], "llm_output")
        self.assertEqual(len(event["content"]), trajectory.EVENT_CONTENT_MAX_CHARS)
        self.assertEqual(event["tool_calls"][0]["name"], "files__write_file")

    def test_tool_invoke_event_includes_capabilities_and_redaction(self):
        event = trajectory.tool_invoke_event(
            "files__write_file",
            {"path": "a.txt", "content": "x", "token": "super-secret"},
            description="写入文件",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        self.assertEqual(event["event_type"], "tool_invoke")
        self.assertEqual(event["capabilities"], ["file.write"])
        self.assertTrue(event["side_effect"])
        self.assertEqual(event["arguments"]["token"], "[redacted]")
        self.assertNotIn("super-secret", json.dumps(event))

    def test_tool_result_event_extracts_text_and_error(self):
        event = trajectory.tool_result_event(
            "files__read_document",
            {"isError": False, "content": [{"type": "text", "text": "hello " + "x" * 1000}]},
        )
        self.assertEqual(event["event_type"], "tool_result")
        self.assertEqual(len(event["result"]), trajectory.EVENT_CONTENT_MAX_CHARS)
        self.assertNotIn("is_error", event)

        failed = trajectory.tool_result_event("files__write_file", {"isError": True, "content": []})
        self.assertTrue(failed["is_error"])


class FeedTests(unittest.TestCase):
    def test_append_and_load_last_events(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "events.jsonl"
            self.assertTrue(trajectory.append_llm_input(feed, [{"role": "user", "content": "任务"}]))
            self.assertTrue(trajectory.append_llm_output(feed, {"role": "assistant", "content": "ok"}))
            self.assertTrue(trajectory.append_tool_events(
                feed, "files__read_document", {"path": "a.txt"},
                {"content": [{"type": "text", "text": "正文"}]},
                description="读取文件",
            ))
            events = trajectory.load_events(feed)
            self.assertEqual([event["event_type"] for event in events],
                             ["llm_input", "llm_output", "tool_invoke", "tool_result"])
            with env(AGENTGUARD_EVENT_FEED=str(feed), AGENTGUARD_REVIEW_TRACE_MAX_STEPS="2"):
                recent = trajectory.recent_events()
            self.assertEqual([event["event_type"] for event in recent], ["tool_invoke", "tool_result"])
            self.assertEqual(recent[0]["capabilities"], ["file.read"])
            self.assertEqual(recent[1]["result"], "正文")

    def test_append_preserves_long_instruction_and_full_history(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "events.jsonl"
            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "u" * config.MAX_USER_INSTRUCTION_CHARS},
            ] + [{"role": "assistant", "content": f"a{index}"} for index in range(60)]
            self.assertTrue(trajectory.append_llm_input(feed, messages))
            events = trajectory.load_events(feed)
            self.assertEqual(len(events), 1)
            self.assertEqual(len(events[0]["messages"]), 62)
            self.assertEqual(len(events[0]["messages"][1]["content"]), config.MAX_USER_INSTRUCTION_CHARS)
            with env(AGENTGUARD_EVENT_FEED=str(feed), AGENTGUARD_REVIEW_TRACE_MAX_STEPS="1"):
                recent = trajectory.recent_events()
            self.assertEqual(len(recent[0]["messages"]), 62)

    def test_malformed_trailing_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "events.jsonl"
            feed.write_text('{"event_type": "llm_input", "messages": []}\n{"event_type": ', encoding="utf-8")
            events = trajectory.load_events(feed)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "llm_input")

    def test_fallback_to_user_instruction_without_feed(self):
        with env(AGENTGUARD_EVENT_FEED=None,
                 AGENTGUARD_USER_INSTRUCTION="把报告保存为 报告/草稿.md"):
            recent = trajectory.recent_events()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["event_type"], "llm_input")
        self.assertEqual(recent[0]["messages"][0]["content"], "把报告保存为 报告/草稿.md")

    def test_no_feed_and_no_instruction_is_empty(self):
        with env(AGENTGUARD_EVENT_FEED=None, AGENTGUARD_USER_INSTRUCTION=None):
            self.assertEqual(trajectory.recent_events(), [])

    def test_append_event_does_not_raise_on_bad_path(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(trajectory.append_event(directory, {"event_type": "llm_input"}))

    def test_events_are_limited_to_configured_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "events.jsonl"
            for index in range(8):
                trajectory.append_event(feed, {"event_type": "tool_result", "tool_name": f"t{index}"})
            with env(AGENTGUARD_EVENT_FEED=str(feed), AGENTGUARD_REVIEW_TRACE_MAX_STEPS="3"):
                recent = trajectory.recent_events()
            self.assertEqual([event["tool_name"] for event in recent], ["t5", "t6", "t7"])


class ConfigTests(unittest.TestCase):
    def test_review_trace_steps_defaults_and_clamps(self):
        with env(AGENTGUARD_REVIEW_TRACE_MAX_STEPS=None):
            self.assertEqual(config.review_trace_max_steps(), config.DEFAULT_REVIEW_TRACE_MAX_STEPS)
        with env(AGENTGUARD_REVIEW_TRACE_MAX_STEPS="0"):
            self.assertEqual(config.review_trace_max_steps(), 1)
        with env(AGENTGUARD_REVIEW_TRACE_MAX_STEPS="100"):
            self.assertEqual(config.review_trace_max_steps(), 50)
        with env(AGENTGUARD_REVIEW_TRACE_MAX_STEPS="7"):
            self.assertEqual(config.review_trace_max_steps(), 7)


if __name__ == "__main__":
    unittest.main()
