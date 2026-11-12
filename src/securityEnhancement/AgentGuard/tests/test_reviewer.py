"""Tests for the fixed Mimo reviewer (upstream-style prompt, fail-open)."""
from __future__ import annotations

import json
import unittest
from typing import Callable

import httpx

from securityEnhancement.AgentGuard.config import MAX_USER_INSTRUCTION_CHARS
from securityEnhancement.AgentGuard.metadata import classify
from securityEnhancement.AgentGuard.models import DEFAULT_PRINCIPAL, PolicyDecision
from securityEnhancement.AgentGuard.reviewer import DEFAULT_INSTRUCTION, Reviewer

from .support import env

API_KEY = "sk-test-secret-value"
BLOCKS = ("Rule", "Current Call", "Relevant Context", "Recent Events")


def chat_response(content: str | None) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def make_reviewer(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    thinking_mode: str | None = "none",
    **kwargs,
) -> tuple[Reviewer, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    reviewer = Reviewer(
        base_url="https://mimo.test/v1",
        api_key=kwargs.pop("api_key", API_KEY),
        model=kwargs.pop("model", None),
        timeout_s=kwargs.pop("timeout_s", 5.0),
        thinking_mode=thinking_mode,
        transport=httpx.MockTransport(wrapped),
        **kwargs,
    )
    return reviewer, captured


def review(
    reviewer: Reviewer,
    arguments: dict | None = None,
    context: dict | None = None,
    rule: PolicyDecision | None = None,
    recent_events: list[dict] | None = None,
):
    return reviewer.review(
        principal=DEFAULT_PRINCIPAL,
        metadata=classify("files", "files__write_file"),
        arguments=arguments if arguments is not None else {"path": "报告/草稿.md", "content": "正文"},
        rule=rule or PolicyDecision(
            effect="llm_review", reason="rule", rule_id="review-writes",
            rule_description="写文件需要复核",
        ),
        context=context if context is not None else {
            "run_id": "run-1", "case": "综合测试", "model": "deepseek-flash",
        },
        recent_events=recent_events,
    )


def prompt_of(captured: list[httpx.Request]) -> str:
    payload = json.loads(captured[0].content)
    assert len(payload["messages"]) == 1, payload["messages"]
    assert payload["messages"][0]["role"] == "user"
    return payload["messages"][0]["content"]


def block(prompt: str, label: str):
    marker = f"\n{label}: " if f"\n{label}: " in prompt else f"{label}: "
    start = prompt.index(marker) + len(marker)
    rest = prompt[start:]
    endings = []
    for other in BLOCKS:
        if other == label:
            continue
        candidate = f"\n{other}: "
        if candidate in rest:
            endings.append(rest.index(candidate))
    end = min(endings) if endings else len(rest)
    return json.loads(rest[:end].strip())


class ReviewerParsingTests(unittest.TestCase):
    def test_allow_decision(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "只写工作区"}'))
        result = review(reviewer)
        self.assertTrue(result.ok)
        self.assertFalse(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.reason, "只写工作区")
        self.assertEqual(result.model, "mimo-v2.6-pro")
        self.assertEqual(len(captured), 1)

    def test_deny_decision(self):
        reviewer, _ = make_reviewer(lambda request: chat_response('{"decision": "deny", "reason": "外发"}'))
        result = review(reviewer)
        self.assertTrue(result.ok)
        self.assertEqual(result.decision, "deny")
        self.assertFalse(result.fail_open)

    def test_fenced_json_is_accepted(self):
        body = '```json\n{"decision": "deny", "reason": "拒绝"}\n```'
        reviewer, _ = make_reviewer(lambda request: chat_response(body))
        self.assertEqual(review(reviewer).decision, "deny")

    def test_json_inside_text_is_accepted(self):
        body = '结论如下：{"decision": "allow", "reason": "可以"} 完毕'
        reviewer, _ = make_reviewer(lambda request: chat_response(body))
        self.assertEqual(review(reviewer).decision, "allow")

    def test_invalid_json_is_fail_open(self):
        reviewer, _ = make_reviewer(lambda request: chat_response("not json at all"))
        result = review(reviewer)
        self.assertFalse(result.ok)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.error, "invalid_output")

    def test_textual_deny_is_deny(self):
        reviewer, _ = make_reviewer(
            lambda request: chat_response("I will deny this call because it exfiltrates data.")
        )
        result = review(reviewer)
        self.assertTrue(result.ok)
        self.assertFalse(result.fail_open)
        self.assertEqual(result.decision, "deny")
        self.assertIn("deny this call", result.reason)

    def test_textual_deny_is_case_insensitive(self):
        reviewer, _ = make_reviewer(lambda request: chat_response("DENY: outside the user's mandate"))
        result = review(reviewer)
        self.assertTrue(result.ok)
        self.assertEqual(result.decision, "deny")
        self.assertFalse(result.fail_open)

    def test_invalid_decision_is_fail_open(self):
        reviewer, _ = make_reviewer(lambda request: chat_response('{"decision": "maybe", "reason": "?"}'))
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.error, "invalid_decision")

    def test_human_check_is_not_accepted(self):
        reviewer, _ = make_reviewer(lambda request: chat_response('{"decision": "human_check", "reason": "?"}'))
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.error, "invalid_decision")

    def test_missing_content_is_fail_open(self):
        reviewer, _ = make_reviewer(lambda request: chat_response(None))
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.error, "missing_content")

    def test_http_error_is_fail_open(self):
        reviewer, _ = make_reviewer(lambda request: httpx.Response(500, text="boom"))
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertIn("HTTP 500", result.reason)

    def test_timeout_is_fail_open(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        reviewer, _ = make_reviewer(handler)
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertEqual(result.decision, "allow")
        self.assertIn("超时", result.reason)

    def test_unconfigured_reviewer_is_fail_open_without_request(self):
        reviewer = Reviewer(
            base_url="", api_key="", model="mimo-v2.6-pro",
            transport=httpx.MockTransport(lambda request: self.fail("should not be called")),
        )
        result = review(reviewer)
        self.assertTrue(result.fail_open)
        self.assertFalse(result.ok)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.error, "not_configured")


class ReviewerPromptTests(unittest.TestCase):
    def test_prompt_has_upstream_structure_without_human_check(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        review(reviewer)
        prompt = prompt_of(captured)
        self.assertTrue(prompt.startswith("You are the AgentGuard LLM rule reviewer.\n"))
        self.assertIn(DEFAULT_INSTRUCTION, prompt)
        self.assertIn("Use the current tool call as the primary evidence.", prompt)
        self.assertIn("Use recent events only when they clarify the meaning or provenance of the current call.", prompt)
        self.assertIn("Ignore AgentGuard transport, framework, and alignment metadata.", prompt)
        self.assertIn('Respond with compact JSON: {"decision":"allow|deny","reason":"..."}', prompt)
        self.assertNotIn("human_check", prompt)
        positions = [prompt.index(f"{label}: ") for label in BLOCKS]
        self.assertEqual(positions, sorted(positions))

    def test_rule_block_uses_rule_id_and_description(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        review(reviewer)
        rule = block(prompt_of(captured), "Rule")
        self.assertEqual(rule["rule_id"], "review-writes")
        self.assertEqual(rule["rule_reason"], "写文件需要复核")
        self.assertEqual(rule["review_kind"], "llm_check")

    def test_rule_llm_prompt_overrides_default_instruction(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        rule = PolicyDecision(
            effect="llm_review", rule_id="review-writes", rule_description="写文件需要复核",
            rule_prompt="只允许写入用户明确指定的文件。",
        )
        review(reviewer, rule=rule)
        prompt = prompt_of(captured)
        self.assertIn("只允许写入用户明确指定的文件。", prompt)
        self.assertNotIn(DEFAULT_INSTRUCTION, prompt)

    def test_current_call_and_relevant_context(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        review(reviewer, {"path": "a.txt", "token": "super-secret-token"})
        prompt = prompt_of(captured)
        current = block(prompt, "Current Call")
        self.assertEqual(current["event_type"], "tool_invoke")
        self.assertEqual(current["tool_name"], "files__write_file")
        self.assertEqual(current["capabilities"], ["file.write"])
        self.assertEqual(current["arguments"]["token"], "[redacted]")
        self.assertNotIn("super-secret-token", prompt)
        context = block(prompt, "Relevant Context")
        self.assertEqual(context["session_id"], "run-1")
        self.assertEqual(context["principal"]["trust_level"], 2)
        self.assertEqual(context["metadata"]["case"], "综合测试")
        self.assertEqual(context["metadata"]["model"], "deepseek-flash")

    def test_current_call_arguments_are_not_truncated(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        arguments = {f"key_{index}": index for index in range(24)}
        arguments["content"] = "x" * 2000
        review(reviewer, arguments)
        current = block(prompt_of(captured), "Current Call")
        self.assertEqual(len(current["arguments"]), 25)
        self.assertEqual(len(current["arguments"]["content"]), 2000)

    def test_recent_events_include_user_instruction_and_tool_history(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        instruction = "把报告保存为 报告/草稿.md，不要改其他文件"
        events = [
            {"event_type": "llm_input", "messages": [{"role": "user", "content": instruction}]},
            {"event_type": "tool_invoke", "tool_name": "files__read_document",
             "arguments": {"path": "a.txt"}, "capabilities": ["file.read"]},
            {"event_type": "tool_result", "tool_name": "files__read_document", "result": "正文"},
        ]
        review(reviewer, recent_events=events)
        prompt = prompt_of(captured)
        recent = block(prompt, "Recent Events")
        self.assertEqual(recent, events)
        self.assertNotIn("user_instruction", prompt)

    def test_recent_events_are_limited(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        events = [{"event_type": "tool_invoke", "tool_name": f"tool_{index}"} for index in range(10)]
        with env(AGENTGUARD_REVIEW_TRACE_MAX_STEPS="2"):
            review(reviewer, recent_events=events)
        recent = block(prompt_of(captured), "Recent Events")
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["tool_name"], "tool_8")

    def test_recent_events_preserve_full_message_history(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u" * 4000},
        ] + [{"role": "assistant", "content": f"a{index}"} for index in range(60)]
        review(reviewer, recent_events=[{"event_type": "llm_input", "messages": messages}])
        recent = block(prompt_of(captured), "Recent Events")
        self.assertEqual(len(recent[0]["messages"]), 62)
        self.assertEqual(len(recent[0]["messages"][1]["content"]), 4000)

    def test_context_user_instruction_is_not_a_separate_prompt_field(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        review(reviewer, context={
            "run_id": "run-1", "case": "综合测试", "model": "deepseek-flash",
            "user_instruction": "不应单独出现在 prompt 里",
        })
        prompt = prompt_of(captured)
        self.assertNotIn("不应单独出现在 prompt 里", prompt)
        self.assertNotIn("user_instruction", prompt)

    def test_api_key_not_in_body_or_result(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        result = review(reviewer)
        self.assertEqual(captured[0].headers["authorization"], f"Bearer {API_KEY}")
        self.assertNotIn(API_KEY, captured[0].content.decode("utf-8"))
        dumped = result.model_dump_json()
        self.assertNotIn(API_KEY, dumped)

    def test_endpoint_handling(self):
        with_chat = Reviewer(base_url="https://mimo.test/v1/chat/completions", api_key="k")
        without_chat = Reviewer(base_url="https://mimo.test/v1/", api_key="k")
        self.assertEqual(with_chat.endpoint, "https://mimo.test/v1/chat/completions")
        self.assertEqual(without_chat.endpoint, "https://mimo.test/v1/chat/completions")

    def test_temperature_and_other_sampling_fields_are_not_overridden(self):
        reviewer, captured = make_reviewer(lambda request: chat_response('{"decision": "allow", "reason": "ok"}'))
        review(reviewer)
        payload = json.loads(captured[0].content)
        for key in ("temperature", "top_p", "max_tokens", "stream"):
            self.assertNotIn(key, payload)

    def test_default_model_and_thinking_field(self):
        with env(MIMO_MODEL=None, MIMO_THINKING_MODE=None):
            reviewer, captured = make_reviewer(
                lambda request: chat_response('{"decision": "allow", "reason": "ok"}'),
                thinking_mode=None,
            )
        self.assertEqual(reviewer.model, "mimo-v2.6-pro")
        self.assertEqual(reviewer.thinking_mode, "thinking")
        review(reviewer)
        payload = json.loads(captured[0].content)
        self.assertEqual(payload["model"], "mimo-v2.6-pro")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertNotIn("enable_thinking", payload)
        self.assertNotIn("reasoning_effort", payload)

    def test_thinking_mode_is_a_single_field(self):
        expectations = {
            "thinking": "thinking",
            "enable_thinking": "enable_thinking",
            "reasoning_effort": "reasoning_effort",
            "none": None,
        }
        for mode, expected in expectations.items():
            with self.subTest(mode=mode):
                reviewer, captured = make_reviewer(
                    lambda request: chat_response('{"decision": "allow", "reason": "ok"}'),
                    thinking_mode=mode,
                )
                review(reviewer)
                payload = json.loads(captured[0].content)
                for key in ("thinking", "enable_thinking", "reasoning_effort"):
                    if key == expected:
                        self.assertIn(key, payload)
                    else:
                        self.assertNotIn(key, payload)

    def test_unknown_thinking_mode_falls_back_to_default(self):
        reviewer, _ = make_reviewer(
            lambda request: chat_response('{"decision": "allow", "reason": "ok"}'),
            thinking_mode="quantum",
        )
        self.assertEqual(reviewer.thinking_mode, "thinking")


class WorkerContextTests(unittest.TestCase):
    def test_user_instruction_is_forwarded_and_truncated(self):
        from securityEnhancement.AgentGuard import config

        with env(AGENTGUARD_USER_INSTRUCTION="把报告保存为 报告/草稿.md"):
            self.assertEqual(config.user_instruction(), "把报告保存为 报告/草稿.md")
            self.assertNotIn("user_instruction", config.worker_context())
        with env(AGENTGUARD_USER_INSTRUCTION="x" * (MAX_USER_INSTRUCTION_CHARS + 100)):
            self.assertEqual(len(config.user_instruction()), MAX_USER_INSTRUCTION_CHARS)


if __name__ == "__main__":
    unittest.main()
