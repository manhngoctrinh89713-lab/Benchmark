"""Load and evaluate the project-owner supplied JSON policy.

Only a small, deterministic subset is implemented.  Conditional expressions
such as ``exists_path(...)``, provenance tracking, goal drift, burst detection,
redaction or AgentDojo specific rules are intentionally absent and rejected at
load time instead of being silently ignored.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import POLICY_VERSION
from .models import PolicyDecision, Principal, ToolMetadata

SUPPORTED_EFFECTS = frozenset({"allow", "deny", "llm_review"})
SUPPORTED_OPS = frozenset(
    {"eq", "ne", "in", "not_in", "contains", "regex", "exists", "gt", "gte", "lt", "lte"}
)
RULE_KEYS = frozenset(
    {"id", "description", "effect", "priority", "tool_groups", "tool_names", "capabilities", "conditions",
     "llm_prompt"}
)
CONDITION_KEYS = frozenset({"field", "op", "value"})
TOP_LEVEL_KEYS = frozenset({"version", "rules"})

_FIELD_DOMAINS = {
    "tool": frozenset({"name", "group", "description"}),
    "metadata": frozenset(
        {"capabilities", "side_effect", "risk_level", "fallback", "classifier_version", "tool_name", "group"}
    ),
    "principal": frozenset({"role", "trust_level", "trust_scale", "label"}),
    "context": frozenset({"run_id", "case", "model"}),
}

_MISSING = object()


class PolicyError(ValueError):
    """Raised internally when a policy cannot be parsed safely."""


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: Any
    regex: re.Pattern[str] | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    effect: str
    priority: float
    tool_groups: tuple[str, ...]
    tool_names: tuple[str, ...]
    capabilities: tuple[str, ...]
    conditions: tuple[Condition, ...]
    index: int
    llm_prompt: str = ""


@dataclass(frozen=True)
class Policy:
    status: str = "missing"
    path: str | None = None
    rules: tuple[Rule, ...] = ()
    error: str | None = None
    loaded_at: str | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None) -> "Policy":
        """Load a policy without ever raising; failures become fail-open."""
        loaded_at = datetime.now().astimezone().isoformat()
        if path is None:
            return cls(status="missing", path=None, rules=(), error=None, loaded_at=loaded_at)
        resolved = str(Path(path).expanduser())
        try:
            file_path = Path(resolved)
            if not file_path.is_file():
                return cls(status="missing", path=resolved, rules=(), error="policy 文件不存在", loaded_at=loaded_at)
            text = file_path.read_text(encoding="utf-8")
        except OSError as error:
            return cls(status="invalid", path=resolved, rules=(), error=f"无法读取 policy：{error}", loaded_at=loaded_at)
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as error:
            return cls(status="invalid", path=resolved, rules=(), error=f"policy 不是合法 JSON：{error}", loaded_at=loaded_at)
        try:
            rules = cls._parse(data)
        except PolicyError as error:
            return cls(status="invalid", path=resolved, rules=(), error=str(error), loaded_at=loaded_at)
        return cls(status="ok", path=resolved, rules=rules, error=None, loaded_at=loaded_at)

    @classmethod
    def from_dict(cls, data: Any, path: str | None = "<inline>") -> "Policy":
        """Build a policy from an already decoded object (used by tests)."""
        loaded_at = datetime.now().astimezone().isoformat()
        try:
            rules = cls._parse(data)
        except PolicyError as error:
            return cls(status="invalid", path=path, rules=(), error=str(error), loaded_at=loaded_at)
        return cls(status="ok", path=path, rules=rules, error=None, loaded_at=loaded_at)

    @staticmethod
    def _parse(data: Any) -> tuple[Rule, ...]:
        if not isinstance(data, dict):
            raise PolicyError("policy 顶层必须是 JSON 对象")
        unknown = set(data) - TOP_LEVEL_KEYS
        if unknown:
            raise PolicyError("不支持的 policy 字段：" + ", ".join(sorted(unknown)))
        version = data.get("version")
        if version is not None:
            if not isinstance(version, str) or version != POLICY_VERSION:
                raise PolicyError(f"不支持的 policy 版本：{version!r}")
        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise PolicyError("rules 必须是数组")
        rules: list[Rule] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_rules):
            rule = Policy._parse_rule(raw, index)
            if rule.id in seen:
                raise PolicyError(f"规则 id 重复：{rule.id}")
            seen.add(rule.id)
            rules.append(rule)
        return tuple(rules)

    @staticmethod
    def _parse_rule(raw: Any, index: int) -> Rule:
        if not isinstance(raw, dict):
            raise PolicyError(f"第 {index} 条规则必须是对象")
        unknown = set(raw) - RULE_KEYS
        if unknown:
            raise PolicyError(f"规则 {index} 包含不支持的字段：" + ", ".join(sorted(unknown)))
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise PolicyError(f"第 {index} 条规则缺少合法的 id")
        effect = raw.get("effect")
        if effect not in SUPPORTED_EFFECTS:
            raise PolicyError(f"规则 {rule_id} 的 effect 不支持：{effect!r}")
        priority = raw.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise PolicyError(f"规则 {rule_id} 的 priority 必须是数字")
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise PolicyError(f"规则 {rule_id} 的 description 必须是字符串")
        llm_prompt = raw.get("llm_prompt", "")
        if not isinstance(llm_prompt, str):
            raise PolicyError(f"规则 {rule_id} 的 llm_prompt 必须是字符串")
        tool_groups = Policy._parse_str_list(raw.get("tool_groups", []), rule_id, "tool_groups")
        tool_names = Policy._parse_str_list(raw.get("tool_names", []), rule_id, "tool_names")
        capabilities = Policy._parse_str_list(raw.get("capabilities", []), rule_id, "capabilities")
        conditions = Policy._parse_conditions(raw.get("conditions", {}), rule_id)
        return Rule(
            id=rule_id,
            description=description,
            effect=effect,
            priority=float(priority),
            tool_groups=tool_groups,
            tool_names=tool_names,
            capabilities=capabilities,
            conditions=conditions,
            index=index,
            llm_prompt=llm_prompt.strip(),
        )

    @staticmethod
    def _parse_str_list(value: Any, rule_id: str, name: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise PolicyError(f"规则 {rule_id} 的 {name} 必须是非空字符串数组")
        return tuple(item.strip() for item in value)

    @staticmethod
    def _parse_conditions(raw: Any, rule_id: str) -> tuple[Condition, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, dict):
            raise PolicyError(f"规则 {rule_id} 的 conditions 必须是对象")
        unknown = set(raw) - {"all"}
        if unknown:
            raise PolicyError(f"规则 {rule_id} 的 conditions 包含不支持的条件组：" + ", ".join(sorted(unknown)))
        items = raw.get("all", [])
        if not isinstance(items, list):
            raise PolicyError(f"规则 {rule_id} 的 conditions.all 必须是数组")
        return tuple(Policy._parse_condition(item, rule_id) for item in items)

    @staticmethod
    def _parse_condition(raw: Any, rule_id: str) -> Condition:
        if not isinstance(raw, dict):
            raise PolicyError(f"规则 {rule_id} 的条件必须是对象")
        unknown = set(raw) - CONDITION_KEYS
        if unknown:
            raise PolicyError(f"规则 {rule_id} 的条件包含不支持的字段：" + ", ".join(sorted(unknown)))
        field_name = raw.get("field")
        op = raw.get("op")
        if not isinstance(field_name, str) or not field_name.strip():
            raise PolicyError(f"规则 {rule_id} 的条件缺少 field")
        if op not in SUPPORTED_OPS:
            raise PolicyError(f"规则 {rule_id} 的条件操作符不支持：{op!r}")
        Policy._validate_field(field_name, rule_id)
        if op == "exists":
            value = raw.get("value", True)
            if not isinstance(value, bool):
                raise PolicyError(f"规则 {rule_id} 的 exists 条件 value 必须是布尔值")
            return Condition(field=field_name, op=op, value=value)
        if "value" not in raw:
            raise PolicyError(f"规则 {rule_id} 的 {op} 条件缺少 value")
        value = raw["value"]
        if op in {"in", "not_in"} and not isinstance(value, list):
            raise PolicyError(f"规则 {rule_id} 的 {op} 条件 value 必须是数组")
        if op in {"gt", "gte", "lt", "lte"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PolicyError(f"规则 {rule_id} 的 {op} 条件 value 必须是数字")
        regex = None
        if op == "regex":
            if not isinstance(value, str):
                raise PolicyError(f"规则 {rule_id} 的 regex 条件 value 必须是字符串")
            try:
                regex = re.compile(value)
            except re.error as error:
                raise PolicyError(f"规则 {rule_id} 的正则无法编译：{error}") from None
        return Condition(field=field_name, op=op, value=value, regex=regex)

    @staticmethod
    def _validate_field(field_name: str, rule_id: str) -> None:
        parts = field_name.split(".")
        root = parts[0]
        if any(not part for part in parts):
            raise PolicyError(f"规则 {rule_id} 引用了不支持的字段：{field_name}")
        if root == "arguments" and len(parts) >= 1:
            return
        if root in _FIELD_DOMAINS and len(parts) == 2 and parts[1] in _FIELD_DOMAINS[root]:
            return
        raise PolicyError(f"规则 {rule_id} 引用了不支持的字段：{field_name}")

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return self.path is not None

    def health(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "status": self.status,
            "path": self.path,
            "rules": len(self.rules),
            "error": self.error,
            "loaded_at": self.loaded_at,
        }

    def evaluate(
        self,
        *,
        principal: Principal,
        metadata: ToolMetadata,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
        tool_description: str = "",
    ) -> PolicyDecision:
        context = context or {}
        if self.status != "ok":
            if self.configured:
                reason = f"policy 无法加载；fail-open（{self.error or self.status}）"
            else:
                reason = "未配置 active policy；fail-open"
            return PolicyDecision(
                effect="allow", reason=reason, matched=False, fail_open=True, policy_status=self.status
            )

        candidates: list[Rule] = []
        for rule in self.rules:
            if not self._rule_matches_tool(rule, metadata):
                continue
            if all(self._condition_matches(condition, principal, metadata, arguments, context, tool_description)
                   for condition in rule.conditions):
                candidates.append(rule)
        if not candidates:
            return PolicyDecision(effect="allow", reason="未命中任何策略规则", matched=False, policy_status="ok")
        candidates.sort(key=lambda rule: (-rule.priority, rule.index))
        chosen = candidates[0]
        reason = f"命中规则 {chosen.id}" + (f"：{chosen.description}" if chosen.description else "")
        return PolicyDecision(
            effect=chosen.effect,  # type: ignore[arg-type]
            reason=reason,
            rule_id=chosen.id,
            rule_description=chosen.description,
            rule_prompt=chosen.llm_prompt or None,
            priority=chosen.priority,
            matched=True,
            policy_status="ok",
        )

    @staticmethod
    def _rule_matches_tool(rule: Rule, metadata: ToolMetadata) -> bool:
        if rule.tool_groups and metadata.group not in rule.tool_groups:
            return False
        if rule.tool_names and metadata.tool_name not in rule.tool_names:
            return False
        if rule.capabilities and not set(rule.capabilities) & set(metadata.capabilities):
            return False
        return True

    @classmethod
    def _condition_matches(
        cls,
        condition: Condition,
        principal: Principal,
        metadata: ToolMetadata,
        arguments: dict[str, Any],
        context: dict[str, Any],
        tool_description: str,
    ) -> bool:
        resolved = cls._resolve(condition.field, principal, metadata, arguments, context, tool_description)
        return cls._apply(condition, resolved)

    @staticmethod
    def _resolve(
        field_name: str,
        principal: Principal,
        metadata: ToolMetadata,
        arguments: dict[str, Any],
        context: dict[str, Any],
        tool_description: str,
    ) -> Any:
        parts = field_name.split(".")
        root = parts[0]
        if root == "arguments":
            if len(parts) == 1:
                return arguments
            return Policy._dig(arguments, parts[1:])
        source: dict[str, Any]
        if root == "tool":
            source = {"name": metadata.tool_name, "group": metadata.group, "description": tool_description}
        elif root == "metadata":
            source = metadata.model_dump()
        elif root == "principal":
            source = principal.model_dump()
        else:
            source = dict(context)
        return Policy._dig(source, parts[1:])

    @staticmethod
    def _dig(value: Any, parts: list[str]) -> Any:
        current = value
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return _MISSING
        return current

    @staticmethod
    def _apply(condition: Condition, resolved: Any) -> bool:
        op = condition.op
        expected = condition.value
        if op == "exists":
            present = resolved is not _MISSING
            return present if expected else not present
        if resolved is _MISSING:
            return op == "ne"
        if op == "eq":
            return _equal(resolved, expected)
        if op == "ne":
            return not _equal(resolved, expected)
        if op in {"in", "not_in"}:
            values = expected if isinstance(expected, list) else []
            if isinstance(resolved, list):
                inside = any(_equal(item, candidate) for item in resolved for candidate in values)
            else:
                inside = any(_equal(resolved, candidate) for candidate in values)
            return inside if op == "in" else not inside
        if op == "contains":
            if isinstance(resolved, str) and isinstance(expected, str):
                return expected in resolved
            if isinstance(resolved, list):
                return any(_equal(item, expected) for item in resolved)
            if isinstance(resolved, dict):
                return isinstance(expected, str) and expected in resolved
            return False
        if op == "regex":
            if resolved is None or not isinstance(resolved, (str, int, float)):
                return False
            return bool(condition.regex and condition.regex.search(str(resolved)))
        if op in {"gt", "gte", "lt", "lte"}:
            if not _is_number(resolved) or not _is_number(expected):
                return False
            if op == "gt":
                return resolved > expected
            if op == "gte":
                return resolved >= expected
            if op == "lt":
                return resolved < expected
            return resolved <= expected
        return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if _is_number(left) and _is_number(right):
        return float(left) == float(right)
    return left == right
