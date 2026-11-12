"""Regression tests for the multi-stage agent topologies in ``src/topology``."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx
from mcp.types import CallToolResult, TextContent

from topology import (
    EXECUTOR_ROLE,
    TOPOLOGIES,
    build_topology,
    load_prompt,
    read_only_tool_names,
    run_topology,
    spec_for,
)

CATALOG_NAMES = [
    "files__read_file",
    "files__list_directory",
    "files__write_file",
    "mail__send_email",
    "mail__mark_read",
    "database__backup_db",
    "database__query",
]


def model_response(message, finish_reason="stop"):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://example.test/chat/completions"),
        json={"choices": [{"message": message, "finish_reason": finish_reason}]},
    )


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def tool_definition(name):
    return {"type": "function",
            "function": {"name": name, "description": "", "parameters": {"type": "object", "properties": {}}}}


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.calls.append((name, arguments))
        return CallToolResult(content=[TextContent(type="text", text="ok")])


class TwoStageTopologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.record = self.root / "record"
        self.record.mkdir()
        self.run_root = self.root / "run"
        self.run_root.mkdir()
        self.meta = {"tool_calls": 0, "model_calls": 0, "normal_model_calls": 0, "status": "running"}
        self.events = self.record / "agentguard_events.jsonl"
        self.session = FakeSession()
        self.tools = [tool_definition(name) for name in CATALOG_NAMES]
        self.catalog = {name: SimpleNamespace(description="", inputSchema={}) for name in CATALOG_NAMES}

    def tearDown(self):
        self.temp.cleanup()

    def run_group(self, name, responses, **overrides):
        queue = list(responses)

        async def fake_request(client, payload, key, record, step, meta, retries=0, endpoint=""):
            return queue.pop(0)

        arguments = dict(
            messages=[{"role": "system", "content": "s"},
                      {"role": "user", "content": "把报表文件整理好"}],
            record=self.record, model="deepseek-flash", endpoint="https://example.test", key="test",
            client=None, run_root=self.run_root, meta=self.meta, session=self.session,
            tools=self.tools, catalog_by_name=self.catalog, guard_events_path=self.events,
            max_steps=9, max_tool_calls=5, api_retries=0, specified_quit_enabled=False,
            model_request=fake_request,
        )
        arguments.update(overrides)
        return asyncio.run(run_topology(name, **arguments))

    def read_json(self, *parts):
        return json.loads(self.record.joinpath(*parts).read_text(encoding="utf-8"))

    def test_registered_groups_have_editable_prompts(self):
        self.assertEqual(TOPOLOGIES, ("planner_executor", "investigator_executor",
                         "reviewer_executor", "investigator_reviewer_executor"))
        for name in TOPOLOGIES:
            spec = spec_for(name)
            for prompt in (spec.first_system, spec.first_user,
                           spec.executor_system, spec.executor_user):
                self.assertTrue(load_prompt(prompt).strip(), prompt)
            self.assertNotEqual(spec.first_role, EXECUTOR_ROLE)
            for attr in ("reviewer_system", "reviewer_user"):
                if hasattr(spec, attr):
                    self.assertTrue(load_prompt(getattr(spec, attr)).strip(), attr)
        # 两个工作流不共用执行者提示词。
        planner_executor = load_prompt(spec_for("planner_executor").executor_system)
        investigator_executor = load_prompt(spec_for("investigator_executor").executor_system)
        self.assertNotEqual(planner_executor, investigator_executor)

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(ValueError):
            spec_for("executor_reviewer")
        with self.assertRaises(ValueError):
            build_topology("executor_reviewer", model="m", endpoint="e", key="k", client=None,
                           record=self.record, run_root=self.run_root, meta=self.meta,
                           session=self.session, tools=[], catalog_by_name={},
                           guard_events_path=self.events, max_steps=1, max_tool_calls=1,
                           api_retries=0, specified_quit_enabled=False)

    def test_read_only_subset_uses_agentguard_classification(self):
        quit_tool = tool_definition("quit")
        allowed = read_only_tool_names(self.tools + [quit_tool], self.catalog)
        self.assertEqual(allowed, {
            "files__read_file", "files__list_directory", "database__query", "quit",
        })
        # 名字看起来像读取、但会改变状态的工具也必须排除。
        self.assertNotIn("mail__mark_read", allowed)
        self.assertNotIn("database__backup_db", allowed)

    def test_planner_is_read_only_and_executor_gets_every_tool(self):
        state = self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("c1", "files__read_file", {"path": "报表.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "目标：整理报表\n步骤：1. 写入汇总"}),
            model_response({"role": "assistant", "content": "整理完成"}),
        ])
        self.assertTrue(state["done"])
        self.assertEqual(self.session.calls, [("files__read_file", {"path": "报表.txt"})])

        # Planner 看得到全部工具定义，但只能调用只读工具。
        planner_tools = {tool["function"]["name"] for tool in self.read_json("planner", "tools.json")}
        self.assertEqual(planner_tools, set(CATALOG_NAMES))
        executor_tools = {tool["function"]["name"] for tool in self.read_json("executor", "tools.json")}
        self.assertEqual(executor_tools, set(CATALOG_NAMES))

        self.assertEqual((self.record / "planner" / "system.md").read_text(encoding="utf-8"),
                         load_prompt("planner_executor/planner"))
        planner_user = (self.record / "planner" / "user.md").read_text(encoding="utf-8")
        self.assertTrue(planner_user.startswith("用户任务"))
        for name in ("files__read_file", "files__list_directory", "database__query"):
            self.assertIn(name, planner_user)
        for name in ("files__write_file", "mail__send_email", "mail__mark_read",
                     "database__backup_db"):
            self.assertNotIn(name, planner_user)
        planner_request = self.read_json("planner", "model-001-request.json")
        self.assertEqual({tool["function"]["name"] for tool in planner_request["tools"]},
                         set(CATALOG_NAMES))
        phases = self.read_json("phases.json")
        self.assertEqual(set(phases[0]["callable"]),
                         {"files__read_file", "files__list_directory", "database__query"})
        self.assertEqual(set(phases[1]["callable"]), set(CATALOG_NAMES))
        self.assertEqual((self.record / "brief.md").read_text(encoding="utf-8"),
                         "目标：整理报表\n步骤：1. 写入汇总")
        self.assertEqual((self.record / "final.md").read_text(encoding="utf-8"), "整理完成")

        executor_request = self.read_json("executor", "model-001-request.json")
        handoff = executor_request["messages"][1]["content"]
        self.assertIn("上游产出：执行计划", handoff)
        self.assertLess(handoff.index("上游产出：执行计划"), handoff.index("目标：整理报表"))
        self.assertLess(handoff.index("目标：整理报表"), handoff.index("用户任务"))
        self.assertIn("把报表文件整理好", handoff)
        self.assertEqual(executor_request["tools"][0]["function"]["name"], CATALOG_NAMES[0])

        self.assertEqual(self.meta["topology"], "planner_executor")
        self.assertEqual([phase["role"] for phase in self.read_json("phases.json")],
                         ["planner", "executor"])
        self.assertEqual(self.meta["status"], "completed")
        self.assertEqual(self.meta["termination_reason"], "final_response")

    def test_planner_user_prompt_lists_only_read_only_tools(self):
        self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "计划"}),
            model_response({"role": "assistant", "content": "完成"}),
        ])
        user = (self.record / "planner" / "user.md").read_text(encoding="utf-8")
        self.assertIn("只读工具", user)
        for name in ("files__read_file", "files__list_directory", "database__query"):
            self.assertIn(name, user)
        for name in ("files__write_file", "mail__send_email", "mail__mark_read",
                     "database__backup_db"):
            self.assertNotIn(name, user)

    def test_planner_write_tool_never_reaches_mcp(self):
        state = self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("c1", "files__write_file", {"path": "a.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "计划：只读"}),
            model_response({"role": "assistant", "content": "完成"}),
        ])
        self.assertTrue(state["done"])
        self.assertEqual(self.session.calls, [])
        blocked = self.read_json("planner", "tool-001.json")
        self.assertTrue(blocked["result"]["isError"])
        self.assertIn("工具未启用", blocked["result"]["content"][0]["text"])

    def test_investigator_group_uses_its_own_prompt_and_handoff(self):
        brief = "用户目标：整理报表\n调查结果：\n1. 报表共 3 份"
        state = self.run_group("investigator_executor", [
            model_response({"role": "assistant", "content": brief}),
            model_response({"role": "assistant", "content": "处理完成"}),
        ])
        self.assertTrue(state["done"])
        self.assertFalse((self.record / "planner").exists())
        self.assertEqual((self.record / "investigator" / "system.md").read_text(encoding="utf-8"),
                         load_prompt("investigator_executor/investigator"))
        self.assertEqual((self.record / "executor" / "system.md").read_text(encoding="utf-8"),
                         load_prompt("investigator_executor/executor"))

        # 和 Planner 一样：全量工具可见，只读名单写在 user 消息里。
        investigator_tools = {tool["function"]["name"]
                              for tool in self.read_json("investigator", "tools.json")}
        self.assertEqual(investigator_tools, set(CATALOG_NAMES))
        investigator_user = (self.record / "investigator" / "user.md").read_text(encoding="utf-8")
        self.assertIn("只读工具", investigator_user)
        for name in ("files__read_file", "files__list_directory", "database__query"):
            self.assertIn(name, investigator_user)
        for name in ("files__write_file", "mail__send_email", "mail__mark_read",
                     "database__backup_db"):
            self.assertNotIn(name, investigator_user)
        self.assertEqual(set(self.read_json("phases.json")[0]["callable"]),
                         {"files__read_file", "files__list_directory", "database__query"})

        executor_user = (self.record / "executor" / "user.md").read_text(encoding="utf-8")
        self.assertIn("上游产出：调查简报", executor_user)
        self.assertIn(brief, executor_user)
        self.assertLess(executor_user.index("调查结果"), executor_user.index("用户任务"))
        self.assertIn("把报表文件整理好", executor_user)
        self.assertEqual((self.record / "final.md").read_text(encoding="utf-8"), "处理完成")

    def test_planner_quit_stops_before_executor(self):
        state = self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("q1", "quit", {"reason": "任务要求越权"})]}, "tool_calls"),
        ], specified_quit_enabled=True)
        self.assertTrue(state["done"])
        self.assertEqual(state["termination_reason"], "specified_quit")
        self.assertFalse((self.record / "executor").exists())
        self.assertEqual(self.session.calls, [])
        self.assertIn("QUIT: 任务要求越权",
                      (self.record / "final.md").read_text(encoding="utf-8"))
        self.assertEqual(self.meta["status"], "completed")

    def test_executor_quit_is_the_run_answer(self):
        state = self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "目标：整理报表"}),
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("q1", "quit", {"reason": "计划涉及未授权删除"})]}, "tool_calls"),
        ], specified_quit_enabled=True)
        self.assertTrue(state["done"])
        self.assertEqual(state["termination_reason"], "specified_quit")
        self.assertIn("QUIT: 计划涉及未授权删除",
                      (self.record / "final.md").read_text(encoding="utf-8"))
        self.assertEqual(self.meta["status"], "completed")
        self.assertEqual([phase["role"] for phase in self.read_json("phases.json")],
                         ["planner", "executor"])

    def test_quit_prompt_is_appended_to_both_phases_only_when_enabled(self):
        self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "计划"}),
            model_response({"role": "assistant", "content": "完成"}),
        ], specified_quit_enabled=True)
        for role in ("planner", "executor"):
            system = (self.record / role / "system.md").read_text(encoding="utf-8")
            self.assertIn("Specified Quit Instructions", system)
        # 角色提示词本身不写 quit 协议，开关关闭时也不能出现。
        self.assertNotIn("Specified Quit Instructions", load_prompt("planner_executor/planner"))

    def test_guard_event_feed_covers_both_phases(self):
        self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("c1", "files__read_file", {"path": "报表.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "计划"}),
            model_response({"role": "assistant", "content": "完成"}),
        ])
        events = [json.loads(line) for line in
                  self.events.read_text(encoding="utf-8").splitlines() if line.strip()]
        kinds = [event["event_type"] for event in events]
        self.assertEqual(kinds.count("llm_input"), 3)
        self.assertEqual(kinds.count("llm_output"), 3)
        self.assertIn("tool_invoke", kinds)
        self.assertIn("tool_result", kinds)

    def test_limits_are_independent_per_agent_in_two_stage_topology(self):
        state = self.run_group("planner_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("p1", "files__read_file", {"path": "a.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "计划"}),
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("e1", "files__write_file", {"path": "b.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "完成"}),
        ], max_steps=2, max_tool_calls=1)
        self.assertTrue(state["done"])
        phases = self.read_json("phases.json")
        self.assertEqual([phase["model_calls"] for phase in phases], [2, 2])
        self.assertEqual([phase["tool_calls"] for phase in phases], [1, 1])
        self.assertEqual([phase["model_call_limit"] for phase in phases], [2, 2])
        self.assertEqual([phase["tool_call_limit"] for phase in phases], [1, 1])
        # 汇总计数仍用于报告，可以超过单个 Agent 的上限。
        self.assertEqual(self.meta["normal_model_calls"], 4)
        self.assertEqual(self.meta["tool_calls"], 2)

    def test_tool_limit_is_still_enforced_within_one_agent(self):
        with self.assertRaisesRegex(RuntimeError, "最大工具调用次数"):
            self.run_group("planner_executor", [
                model_response({"role": "assistant", "content": "", "tool_calls": [
                    tool_call("p1", "files__read_file", {"path": "a.txt"})]}, "tool_calls"),
                model_response({"role": "assistant", "content": "", "tool_calls": [
                    tool_call("p2", "files__list_directory", {"path": "."})]}, "tool_calls"),
            ], max_steps=3, max_tool_calls=1)
        self.assertEqual(self.meta["termination_reason"], "max_tool_calls")


    def test_reviewer_executor_runs_two_phases(self):
        state = self.run_group("reviewer_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("r1", "files__read_file", {"path": "报表.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "执行时注意点：\n1. 写入前再次确认目标文件"}),
            model_response({"role": "assistant", "content": "整理完成"}),
        ])
        self.assertTrue(state["done"])
        self.assertEqual(self.meta["topology"], "reviewer_executor")
        self.assertEqual(self.session.calls, [("files__read_file", {"path": "报表.txt"})])
        self.assertEqual([phase["role"] for phase in self.read_json("phases.json")],
                         ["reviewer", "executor"])

        # Reviewer 只能调用只读工具，Executor 拿全集。
        phases = self.read_json("phases.json")
        read_only = {"files__read_file", "files__list_directory", "database__query"}
        self.assertEqual(set(phases[0]["callable"]), read_only)
        self.assertEqual(set(phases[1]["callable"]), set(CATALOG_NAMES))

        review = "执行时注意点：\n1. 写入前再次确认目标文件"
        self.assertEqual((self.record / "brief.md").read_text(encoding="utf-8"), review)
        reviewer_user = (self.record / "reviewer" / "user.md").read_text(encoding="utf-8")
        self.assertIn("只读工具", reviewer_user)
        self.assertIn("files__read_file", reviewer_user)
        executor_user = (self.record / "executor" / "user.md").read_text(encoding="utf-8")
        self.assertIn("Reviewer 执行时注意点", executor_user)
        self.assertIn(review, executor_user)
        self.assertIn("把报表文件整理好", executor_user)
        self.assertEqual((self.record / "final.md").read_text(encoding="utf-8"), "整理完成")
        self.assertEqual(self.meta["status"], "completed")
        self.assertEqual(self.meta["termination_reason"], "final_response")

    def test_limits_are_independent_for_each_agent_in_three_stage_topology(self):
        state = self.run_group("investigator_reviewer_executor", [
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("i1", "files__read_file", {"path": "a.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "调查简报"}),
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("r1", "files__read_file", {"path": "a.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "审查后的简报"}),
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("e1", "files__write_file", {"path": "b.txt"})]}, "tool_calls"),
            model_response({"role": "assistant", "content": "完成"}),
        ], max_steps=2, max_tool_calls=1)
        self.assertTrue(state["done"])
        phases = self.read_json("phases.json")
        self.assertEqual([phase["model_calls"] for phase in phases], [2, 2, 2])
        self.assertEqual([phase["tool_calls"] for phase in phases], [1, 1, 1])
        self.assertEqual([phase["model_call_limit"] for phase in phases], [2, 2, 2])
        self.assertEqual([phase["tool_call_limit"] for phase in phases], [1, 1, 1])
        self.assertEqual(self.meta["normal_model_calls"], 6)
        self.assertEqual(self.meta["tool_calls"], 3)

    def test_investigator_reviewer_executor_runs_three_phases(self):
        state = self.run_group("investigator_reviewer_executor", [
            model_response({"role": "assistant", "content": "用户目标：整理报表\n调查结果：\n1. 报表文件存在，共 3 份"}),
            model_response({"role": "assistant", "content": "执行时注意点：\n1. 确认目标文件存在后再写入"}),
            model_response({"role": "assistant", "content": "整理完成"}),
        ])
        self.assertTrue(state["done"])
        self.assertEqual(self.meta["topology"], "investigator_reviewer_executor")
        self.assertEqual([phase["role"] for phase in self.read_json("phases.json")],
                         ["investigator", "reviewer", "executor"])
        self.assertEqual((self.record / "brief.md").read_text(encoding="utf-8"),
                         "用户目标：整理报表\n调查结果：\n1. 报表文件存在，共 3 份")
        self.assertEqual((self.record / "review.md").read_text(encoding="utf-8"),
                         "执行时注意点：\n1. 确认目标文件存在后再写入")
        self.assertEqual((self.record / "final.md").read_text(encoding="utf-8"), "整理完成")

        # 前两个阶段只能调用只读工具，Executor 拿全集。
        phases = self.read_json("phases.json")
        read_only = {"files__read_file", "files__list_directory", "database__query"}
        self.assertEqual(set(phases[0]["callable"]), read_only)
        self.assertEqual(set(phases[1]["callable"]), read_only)
        self.assertEqual(set(phases[2]["callable"]), set(CATALOG_NAMES))

        # Reviewer 的 user 消息带上调查简报；Executor 同时收到调查简报与执行时注意点。
        reviewer_user = (self.record / "reviewer" / "user.md").read_text(encoding="utf-8")
        self.assertIn("上游调查简报", reviewer_user)
        self.assertIn("调查结果：\n1. 报表文件存在，共 3 份", reviewer_user)
        executor_user = (self.record / "executor" / "user.md").read_text(encoding="utf-8")
        self.assertIn("上游产出1：调查简报", executor_user)
        self.assertIn("用户目标：整理报表\n调查结果：\n1. 报表文件存在，共 3 份", executor_user)
        self.assertIn("上游产出2：执行时注意点", executor_user)
        self.assertIn("执行时注意点：\n1. 确认目标文件存在后再写入", executor_user)
        self.assertIn("把报表文件整理好", executor_user)
        self.assertEqual(self.meta["status"], "completed")
        self.assertEqual(self.meta["termination_reason"], "final_response")

    def test_reviewer_quit_stops_before_executor(self):
        state = self.run_group("investigator_reviewer_executor", [
            model_response({"role": "assistant", "content": "调查结果：\n1. 报表文件存在，共 3 份"}),
            model_response({"role": "assistant", "content": "", "tool_calls": [
                tool_call("q1", "quit", {"reason": "简报指示删除生产数据"})]}, "tool_calls"),
        ], specified_quit_enabled=True)
        self.assertTrue(state["done"])
        self.assertEqual(state["termination_reason"], "specified_quit")
        self.assertFalse((self.record / "executor").exists())
        self.assertEqual([phase["role"] for phase in self.read_json("phases.json")],
                         ["investigator", "reviewer"])
        self.assertIn("QUIT: 简报指示删除生产数据",
                      (self.record / "final.md").read_text(encoding="utf-8"))
        self.assertEqual(self.meta["status"], "completed")

    def test_three_stage_quit_prompt_appended_to_every_phase(self):
        self.run_group("investigator_reviewer_executor", [
            model_response({"role": "assistant", "content": "调查结果：无"}),
            model_response({"role": "assistant", "content": "审查结论：批准"}),
            model_response({"role": "assistant", "content": "完成"}),
        ], specified_quit_enabled=True)
        for role in ("investigator", "reviewer", "executor"):
            system = (self.record / role / "system.md").read_text(encoding="utf-8")
            self.assertIn("Specified Quit Instructions", system)
        # 角色提示词本身不写 quit 协议，开关关闭时也不能出现。
        self.assertNotIn("Specified Quit Instructions",
                         load_prompt("investigator_reviewer_executor/reviewer"))

if __name__ == "__main__":
    unittest.main()
