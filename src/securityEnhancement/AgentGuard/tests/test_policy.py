"""Tests for JSON policy loading and evaluation."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from securityEnhancement.AgentGuard.models import DEFAULT_PRINCIPAL, ToolMetadata
from securityEnhancement.AgentGuard.policy import Policy


def tool(
    name: str = "files__write_file",
    group: str = "files",
    capabilities: tuple[str, ...] = ("file.write",),
    side_effect: bool = True,
    risk: str = "medium",
) -> ToolMetadata:
    return ToolMetadata(
        group=group,
        tool_name=name,
        capabilities=list(capabilities),
        side_effect=side_effect,
        risk_level=risk,  # type: ignore[arg-type]
        classifier_version="agentguard-metadata-v1",
    )


def policy(rules: list[dict]) -> Policy:
    return Policy.from_dict({"version": "policy-v1", "rules": rules})


def rule(rule_id: str = "r1", effect: str = "deny", **kwargs) -> dict:
    data = {"id": rule_id, "effect": effect, "priority": kwargs.pop("priority", 0)}
    data.update(kwargs)
    return data


def evaluate(
    active: Policy,
    metadata: ToolMetadata | None = None,
    arguments: dict | None = None,
    context: dict | None = None,
):
    return active.evaluate(
        principal=DEFAULT_PRINCIPAL,
        metadata=metadata or tool(),
        arguments=arguments or {},
        context=context or {},
    )


class PolicyLoadingTests(unittest.TestCase):
    def test_no_policy_is_fail_open_allow(self):
        decision = evaluate(Policy.load(None))
        self.assertEqual(decision.effect, "allow")
        self.assertTrue(decision.fail_open)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.policy_status, "missing")

    def test_missing_file_is_fail_open_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            active = Policy.load(Path(directory) / "absent.json")
        self.assertEqual(active.status, "missing")
        self.assertTrue(active.configured)
        decision = evaluate(active)
        self.assertEqual(decision.effect, "allow")
        self.assertTrue(decision.fail_open)

    def test_invalid_json_is_fail_open_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text("{not json", encoding="utf-8")
            active = Policy.load(path)
        self.assertEqual(active.status, "invalid")
        self.assertIn("JSON", active.error or "")
        self.assertEqual(evaluate(active).effect, "allow")
        self.assertTrue(evaluate(active).fail_open)

    def test_valid_file_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps({"version": "policy-v1", "rules": [rule()]}), encoding="utf-8")
            active = Policy.load(path)
        self.assertEqual(active.status, "ok")
        self.assertEqual(len(active.rules), 1)
        self.assertEqual(evaluate(active).effect, "deny")

    def test_example_policy_has_valid_format(self):
        path = Path(__file__).resolve().parents[1] / "policy.example.json"
        active = Policy.load(path)
        self.assertEqual(active.status, "ok", active.error)
        self.assertEqual(len(active.rules), 1)
        self.assertEqual(active.rules[0].id, "example-rule")

    def test_bundled_active_policy_loads_and_reviews_mutation(self):
        path = Path(__file__).resolve().parents[1] / "policy.json"
        active = Policy.load(path)
        self.assertEqual(active.status, "ok", active.error)
        self.assertEqual(len(active.rules), 2)
        write_decision = evaluate(active)
        self.assertEqual(write_decision.effect, "llm_review")
        self.assertTrue(write_decision.matched)
        read_decision = active.evaluate(
            principal=DEFAULT_PRINCIPAL,
            metadata=tool(name="files__read_file", capabilities=("file.read",), side_effect=False),
            arguments={},
            context={},
        )
        self.assertEqual(read_decision.effect, "allow")

    def test_default_config_policy_is_bundled_active_policy(self):
        from securityEnhancement.AgentGuard import config
        from .support import env

        # Do not depend on a user-level AGENTGUARD_POLICY_PATH override.
        with env(AGENTGUARD_POLICY_PATH=None):
            self.assertEqual(config.policy_path(), config.DEFAULT_POLICY_PATH)
            active = Policy.load(config.policy_path())
        self.assertEqual(active.status, "ok", active.error)
        self.assertEqual(active.rules[0].id, "review-side-effect-operations")
    def test_invalid_structures_are_fail_open(self):
        invalid_cases = [
            [],
            {"version": "policy-v2", "rules": []},
            {"version": "policy-v1", "rules": [], "goal_drift": {}},
            {"version": "policy-v1", "rules": [{"effect": "deny"}]},
            {"version": "policy-v1", "rules": [rule(effect="block")]},
            {"version": "policy-v1", "rules": [rule(priority="high")]},
            {"version": "policy-v1", "rules": [rule(llm_prompt=123)]},
            {"version": "policy-v1", "rules": [rule(exists_path="x")]},
            {"version": "policy-v1", "rules": [rule(tool_groups=["files", 1])]},
            {"version": "policy-v1", "rules": [rule(conditions={"any": []})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "arguments.x", "op": "exists_path"}]})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "arguments.x", "op": "eq", "value": 1, "extra": 2}]})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "goal.drift", "op": "eq", "value": 1}]})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "arguments.x", "op": "regex", "value": "["}]})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "arguments.x", "op": "in", "value": "x"}]})]},
            {"version": "policy-v1", "rules": [rule(conditions={"all": [{"field": "arguments.x", "op": "gt", "value": "1"}]})]},
            {"version": "policy-v1", "rules": [rule(id="a"), rule(id="a")]},
        ]
        for data in invalid_cases:
            with self.subTest(data=data):
                active = Policy.from_dict(data)
                self.assertEqual(active.status, "invalid", active.error)
                self.assertEqual(evaluate(active).effect, "allow")
                self.assertTrue(evaluate(active).fail_open)


class PolicyMatchingTests(unittest.TestCase):
    def test_tool_group_match(self):
        active = policy([rule(tool_groups=["files"])])
        self.assertEqual(evaluate(active, tool(group="files")).effect, "deny")
        self.assertEqual(evaluate(active, tool(group="mail", name="mail__send_email",
                                               capabilities=("mail.send",))).effect, "allow")

    def test_tool_name_match(self):
        active = policy([rule(tool_names=["mail__send_email"])])
        self.assertEqual(
            evaluate(active, tool(group="mail", name="mail__send_email", capabilities=("mail.send",))).effect,
            "deny",
        )
        self.assertEqual(evaluate(active).effect, "allow")

    def test_capability_intersection(self):
        active = policy([rule(capabilities=["commerce.transaction", "file.delete"])])
        self.assertEqual(
            evaluate(active, tool(capabilities=("commerce.read", "commerce.transaction"))).effect, "deny"
        )
        self.assertEqual(evaluate(active, tool(capabilities=("commerce.read",))).effect, "allow")

    def test_all_conditions_must_match(self):
        active = policy(
            [
                rule(
                    conditions={
                        "all": [
                            {"field": "arguments.path", "op": "contains", "value": "secret"},
                            {"field": "arguments.path", "op": "regex", "value": "\\.txt$"},
                        ]
                    }
                )
            ]
        )
        self.assertEqual(evaluate(active, arguments={"path": "secret/report.txt"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"path": "secret/report.md"}).effect, "allow")
        self.assertEqual(evaluate(active, arguments={"path": "public/report.txt"}).effect, "allow")

    def test_eq_and_ne(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.mode", "op": "eq", "value": "force"}]})])
        self.assertEqual(evaluate(active, arguments={"mode": "force"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"mode": "safe"}).effect, "allow")
        self.assertEqual(evaluate(active, arguments={}).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "arguments.mode", "op": "ne", "value": "safe"}]})])
        self.assertEqual(evaluate(active, arguments={}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"mode": "force"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"mode": "safe"}).effect, "allow")

    def test_in_and_not_in(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.op", "op": "in", "value": ["delete", "drop"]}]})])
        self.assertEqual(evaluate(active, arguments={"op": "delete"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"op": "read"}).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "arguments.op", "op": "not_in", "value": ["read"]}]})])
        self.assertEqual(evaluate(active, arguments={"op": "read"}).effect, "allow")
        self.assertEqual(evaluate(active, arguments={"op": "write"}).effect, "deny")

    def test_contains_string_list_and_dict(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.path", "op": "contains", "value": ".env"}]})])
        self.assertEqual(evaluate(active, arguments={"path": "config/.env"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"path": "config/app.yaml"}).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "arguments.tags", "op": "contains", "value": "prod"}]})])
        self.assertEqual(evaluate(active, arguments={"tags": ["dev", "prod"]}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"tags": ["dev"]}).effect, "allow")

    def test_regex_is_search_not_fullmatch(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.path", "op": "regex", "value": "secret"}]})])
        self.assertEqual(evaluate(active, arguments={"path": "a/secret/b.txt"}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"path": "a/public/b.txt"}).effect, "allow")

    def test_exists(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.expected_sha256", "op": "exists"}]})])
        self.assertEqual(evaluate(active, arguments={"expected_sha256": None}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={}).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "arguments.expected_sha256", "op": "exists", "value": False}]})])
        self.assertEqual(evaluate(active, arguments={}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"expected_sha256": "abc"}).effect, "allow")

    def test_numeric_comparisons(self):
        for op, threshold, expected in (("gt", 100, {"amount": 101}), ("gte", 100, {"amount": 100}),
                                        ("lt", 100, {"amount": 99}), ("lte", 100, {"amount": 100})):
            with self.subTest(op=op):
                active = policy([rule(conditions={"all": [{"field": "arguments.amount", "op": op, "value": threshold}]})])
                self.assertEqual(evaluate(active, arguments=expected).effect, "deny")
                self.assertEqual(evaluate(active, arguments={"amount": "many"}).effect, "allow")

    def test_nested_argument_path(self):
        active = policy([rule(conditions={"all": [{"field": "arguments.options.path", "op": "eq", "value": "x"}]})])
        self.assertEqual(evaluate(active, arguments={"options": {"path": "x"}}).effect, "deny")
        self.assertEqual(evaluate(active, arguments={"options": {"path": "y"}}).effect, "allow")

    def test_field_domains(self):
        active = policy([rule(conditions={"all": [{"field": "metadata.side_effect", "op": "eq", "value": True}]})])
        self.assertEqual(evaluate(active, tool(side_effect=True)).effect, "deny")
        self.assertEqual(evaluate(active, tool(side_effect=False)).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "principal.trust_level", "op": "lte", "value": 2}]})])
        self.assertEqual(evaluate(active).effect, "deny")

        active = policy([rule(conditions={"all": [{"field": "context.model", "op": "eq", "value": "deepseek-flash"}]})])
        self.assertEqual(evaluate(active, context={"model": "deepseek-flash"}).effect, "deny")
        self.assertEqual(evaluate(active, context={}).effect, "allow")

        active = policy([rule(conditions={"all": [{"field": "tool.name", "op": "eq", "value": "files__write_file"}]})])
        self.assertEqual(evaluate(active).effect, "deny")

    def test_priority_and_file_order(self):
        active = policy(
            [
                rule("allow-low", effect="allow", priority=10),
                rule("deny-high", effect="deny", priority=100),
            ]
        )
        self.assertEqual(evaluate(active).rule_id, "deny-high")

        active = policy([rule("first", effect="deny", priority=5), rule("second", effect="allow", priority=5)])
        self.assertEqual(evaluate(active).rule_id, "first")

        active = policy([rule("first", effect="allow", priority=5), rule("second", effect="deny", priority=5)])
        self.assertEqual(evaluate(active).rule_id, "first")
        self.assertEqual(evaluate(active).effect, "allow")

    def test_all_three_effects(self):
        for effect in ("allow", "deny", "llm_review"):
            with self.subTest(effect=effect):
                decision = evaluate(policy([rule(effect=effect)]))
                self.assertEqual(decision.effect, effect)
                self.assertTrue(decision.matched)
                self.assertEqual(decision.rule_id, "r1")

    def test_llm_prompt_is_parsed_and_returned(self):
        decision = evaluate(policy([rule(effect="llm_review", llm_prompt="只允许写入用户指定的文件。")]))
        self.assertEqual(decision.rule_prompt, "只允许写入用户指定的文件。")
        self.assertIsNone(evaluate(policy([rule(effect="llm_review")])).rule_prompt)

    def test_no_match_allows_without_fail_open(self):
        decision = evaluate(policy([rule(tool_groups=["mail"])]), tool(group="files"))
        self.assertEqual(decision.effect, "allow")
        self.assertFalse(decision.fail_open)
        self.assertFalse(decision.matched)
        self.assertFalse(decision.fail_open)

    def test_reason_contains_rule_id_and_description(self):
        active = policy([rule("files-deny", description="禁止写入外部路径")])
        decision = evaluate(active)
        self.assertIn("files-deny", decision.reason)
        self.assertIn("禁止写入外部路径", decision.reason)
        self.assertEqual(decision.rule_description, "禁止写入外部路径")


if __name__ == "__main__":
    unittest.main()

