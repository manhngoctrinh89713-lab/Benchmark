"""Deterministic capability metadata for the dynamic MCP tool catalog.

Classification only uses the public tool contract:

* benchmark group (``mail``, ``files``, ``database`` ...)
* MCP tool name
* MCP description
* MCP input schema

It never looks at seeds, cases, attack samples or runtime results, and it does
not contain rules keyed on individual benchmark tool names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import CLASSIFIER_VERSION
from .models import ToolMetadata

# ---------------------------------------------------------------------------
# Verb vocabulary (generic English verbs used by the public tool names)
# ---------------------------------------------------------------------------
READ_VERBS = frozenset(
    {
        "get", "list", "read", "search", "find", "describe", "show", "info",
        "status", "check", "query", "explain", "export", "download", "compare",
        "analyze", "analyse", "diagnose", "inspect", "view", "tree", "browse",
        "scan", "lookup", "preview", "verify", "validate",
    }
)
DELETE_VERBS = frozenset(
    {
        "delete", "remove", "clear", "empty", "purge", "trash", "erase",
        "dissolve", "leave", "recall", "recycle", "unlink", "drop", "wipe",
    }
)
SEND_VERBS = frozenset({"send", "reply", "forward", "broadcast"})
WRITE_VERBS = frozenset(
    {
        "create", "update", "write", "set", "save", "add", "insert", "replace",
        "rename", "move", "copy", "edit", "append", "apply", "import", "upload",
        "restore", "schedule", "cancel", "adjust", "change", "complete",
        "receive", "revoke", "resolve", "fulfill", "deliver", "bind", "unbind",
        "withdraw", "request", "process", "validate", "prune", "manage",
        "clean", "launch", "signal", "reboot", "restart", "start", "stop",
        "mark", "favorite", "favourite", "respond", "transfer", "assign",
        "label", "milestone", "merge", "submit", "push", "commit", "stash",
        "checkout", "rebase", "reset", "revert", "squash", "cherry", "unstage",
        "rerun", "dispatch", "publish", "extract", "execute",
        "perform", "confirm", "reorder",
    }
)
TRANSACTION_VERBS = frozenset({"pay", "checkout", "refund", "place", "subscribe"})
MONEY_EXECUTE_VERBS = frozenset({"resolve", "complete", "process", "receive", "execute", "issue", "apply"})
MONEY_TOKENS = frozenset(
    {"refund", "refunds", "payment", "payments", "renewal", "renewals", "charge", "charges",
     "settlement", "settlements", "payout", "payouts"}
)

GIT_READ_TOKENS = frozenset(
    {
        "log", "diff", "status", "blame", "show", "reflog", "history",
        "branches", "tags", "operation", "list", "read", "compare", "search",
        "find", "inspect",
    }
)
GITHUB_READ_LAST_TOKENS = frozenset({"read"})
GITHUB_MUTATING_HEADS = frozenset(
    {"mark", "set", "add", "remove", "delete", "update", "create", "submit",
     "merge", "request", "rerun", "cancel", "dispatch"}
)
HOST_FILE_TOKENS = frozenset({"file", "files", "directory", "directories", "personal", "recycled", "recycle", "trash"})
PROCESS_VERBS = frozenset({"launch", "change", "signal", "restart", "stop", "start"})

KNOWN_GROUPS = frozenset(
    {"mail", "chat", "files", "database", "code", "git", "github", "pc", "server", "merchant", "buyer"}
)


@dataclass(frozen=True)
class VerbRule:
    capability: str
    verbs: frozenset[str]
    side_effect: bool
    risk: str


# (capability, side_effect, risk, basis, fallback)
Classification = tuple[str, bool, str, str, bool]


_MAIL_RULES = (
    VerbRule("mail.read", READ_VERBS | {"resolve"}, False, "low"),
    VerbRule("mail.delete", DELETE_VERBS, True, "high"),
    VerbRule("mail.send", SEND_VERBS, True, "medium"),
    VerbRule("mail.write", WRITE_VERBS, True, "medium"),
)
_CHAT_RULES = (
    VerbRule("chat.read", READ_VERBS, False, "low"),
    VerbRule("chat.delete", DELETE_VERBS, True, "high"),
    VerbRule("chat.send", SEND_VERBS, True, "medium"),
    VerbRule("chat.write", WRITE_VERBS, True, "medium"),
)
_FILES_RULES = (
    VerbRule("file.read", READ_VERBS, False, "low"),
    VerbRule("file.delete", DELETE_VERBS, True, "high"),
    VerbRule("file.write", WRITE_VERBS, True, "medium"),
)
_DATABASE_RULES = (
    VerbRule("db.read", frozenset({"backup"}), True, "low"),
    VerbRule("db.read", READ_VERBS, False, "low"),
    VerbRule("db.write", WRITE_VERBS | DELETE_VERBS | frozenset({"execute"}), True, "high"),
)
_CODE_RULES = (
    VerbRule("code.read", READ_VERBS, False, "low"),
    VerbRule("code.write", WRITE_VERBS | DELETE_VERBS, True, "medium"),
)
_SIMPLE_GROUP_RULES = {
    "mail": _MAIL_RULES,
    "chat": _CHAT_RULES,
    "files": _FILES_RULES,
    "database": _DATABASE_RULES,
    "code": _CODE_RULES,
}

_WRITE_HINTS = re.compile(
    r"(?i)\b(create|write|update|delete|remove|send|upload|import|modify|set|save|add|drop|truncate|execute|commit|push|pay|refund)\b"
)
_WRITE_HINTS_ZH = re.compile(
    "创建|写入|修改|更新|删除|移除|发送|上传|导入|保存|清空|覆盖|付款|退款|提交|执行|追加|移动|复制|重命名|授权|购买|同步"
)
_MONEY_DESCRIPTION = re.compile("退款|refund", re.IGNORECASE)


def _tokens(group: str, tool_name: str) -> tuple[str, ...]:
    """Split the public tool name into lowercase tokens, dropping the group prefix."""
    name = (tool_name or "").strip()
    if "__" in name:
        name = name.split("__", 1)[1]
    tokens = [part for part in re.split(r"[^a-z0-9]+", name.lower()) if part]
    # ``pc__pc_read_file`` / ``git__git_log`` repeat the group name.
    while tokens and tokens[0] == group:
        tokens.pop(0)
    return tuple(tokens)


def _match(rules: tuple[VerbRule, ...], tokens: tuple[str, ...]) -> tuple[VerbRule, str] | None:
    if not tokens:
        return None
    for rule in rules:
        if tokens[0] in rule.verbs:
            return rule, "leading"
    # Unknown leading verb: still classify deterministically from later tokens.
    for rule in rules:
        for token in tokens[1:]:
            if token in rule.verbs:
                return rule, f"token:{token}"
    return None


def _metadata(
    group: str,
    tool_name: str,
    capability: str,
    side_effect: bool,
    risk: str,
    basis: str,
    fallback: bool = False,
) -> ToolMetadata:
    return ToolMetadata(
        group=group,
        tool_name=tool_name,
        capabilities=[capability],
        side_effect=side_effect,
        risk_level=risk,  # type: ignore[arg-type]
        classifier_version=CLASSIFIER_VERSION,
        fallback=fallback,
        basis=basis,
    )


def _read_side_effect(capability: str, side_effect: bool, tokens: tuple[str, ...]) -> bool:
    if capability.endswith(".read"):
        if "download" in tokens or "export" in tokens:
            return True
        # ``backup_*`` creates a backup file; ``verify_backup`` only reads.
        if tokens and tokens[0] == "backup":
            return True
    return side_effect


def _classify_git(tokens: tuple[str, ...]) -> Classification:
    for token in tokens:
        if token in GIT_READ_TOKENS:
            return "repo.read", False, "low", f"git:read-token:{token}", False
    return "repo.write", True, "medium", "git:mutating", False


def _classify_github(tokens: tuple[str, ...]) -> Classification:
    if tokens:
        if tokens[0] in READ_VERBS:
            return "repo.read", False, "low", "github:leading-read", False
        if tokens[-1] in GITHUB_READ_LAST_TOKENS and tokens[0] not in GITHUB_MUTATING_HEADS:
            return "repo.read", False, "low", f"github:read-suffix:{tokens[-1]}", False
    return "repo.write", True, "medium", "github:mutating", False


def _host_rule(capability: str, side_effect: bool, risk: str, how: str) -> Classification:
    return capability, side_effect, risk, how, False


def _classify_host(group: str, tokens: tuple[str, ...]) -> Classification:
    if not tokens:
        return _fallback(group, tokens, "", None)
    first = tokens[0]
    file_like = any(token in HOST_FILE_TOKENS for token in tokens)
    if first in READ_VERBS:
        if file_like:
            return _host_rule("file.read", False, "low", "host:file.read:leading")
        return _host_rule("host.read", False, "low", "host:read:leading")
    if first in DELETE_VERBS:
        if file_like:
            return _host_rule("file.delete", True, "high", "host:file.delete:leading")
        return _host_rule("host.admin", True, "high", "host:admin:delete")
    if first in PROCESS_VERBS:
        return _host_rule("process.control", True, "high", f"host:process.control:{first}")
    if first in WRITE_VERBS:
        if file_like:
            return _host_rule("file.write", True, "medium", "host:file.write:leading")
        return _host_rule("host.admin", True, "high", "host:admin:leading")
    # Unknown leading verb: keep file operations separate from host admin.
    for token in tokens:
        if token in READ_VERBS:
            return _host_rule("file.read" if file_like else "host.read", False, "low", f"host:token:{token}")
        if token in DELETE_VERBS:
            return _host_rule("file.delete" if file_like else "host.admin", True, "high", f"host:token:{token}")
        if token in WRITE_VERBS:
            return _host_rule("file.write" if file_like else "host.admin", True, "medium", f"host:token:{token}")
    return _fallback(group, tokens, "", None)


def _classify_commerce(group: str, tokens: tuple[str, ...], description: str = "") -> Classification:
    if not tokens:
        return _fallback(group, tokens, "", None)
    first = tokens[0]
    money_context = (
        any(token in MONEY_TOKENS for token in tokens)
        or bool(_MONEY_DESCRIPTION.search(description or ""))
    )
    if first in READ_VERBS:
        return "commerce.read", False, "low", "commerce:read:leading", False
    if first in TRANSACTION_VERBS:
        return "commerce.transaction", True, "high", f"commerce:transaction:{first}", False
    if first in MONEY_EXECUTE_VERBS and money_context:
        return "commerce.transaction", True, "high", "commerce:transaction:money-context", False
    if first in WRITE_VERBS or first in DELETE_VERBS or first == "export":
        return "commerce.write", True, "medium", "commerce:write:leading", False
    for token in tokens:
        if token in READ_VERBS:
            return "commerce.read", False, "low", f"commerce:token:{token}", False
        if token in TRANSACTION_VERBS or token in MONEY_TOKENS:
            return "commerce.transaction", True, "high", f"commerce:token:{token}", False
        if token in WRITE_VERBS or token in DELETE_VERBS:
            return "commerce.write", True, "medium", f"commerce:token:{token}", False
    return _fallback(group, tokens, "", None)


def _is_scheduled_send(tokens: tuple[str, ...]) -> bool:
    """``schedule_email`` and ``update_scheduled_email`` are deferred sends."""
    if not tokens:
        return False
    if tokens[0] in {"list", "get", "read", "delete", "remove", "cancel"}:
        return False
    return tokens[0] == "schedule" or "scheduled" in tokens


def _looks_like_write(tokens: tuple[str, ...], description: str, input_schema: dict[str, Any] | None) -> bool:
    if any(token in SEND_VERBS or token in DELETE_VERBS or token in WRITE_VERBS or token in TRANSACTION_VERBS
           for token in tokens):
        return True
    text = description or ""
    if input_schema:
        properties = input_schema.get("properties")
        if isinstance(properties, dict):
            keys = {str(key).lower() for key in properties}
            # A payload-bearing schema is a write-shaped contract even when the
            # tool name itself does not carry a recognised verb.
            if keys & {"content", "contents", "body", "data", "payload"}:
                return True
            text += " " + " ".join(sorted(keys))
    return bool(_WRITE_HINTS.search(text) or _WRITE_HINTS_ZH.search(text))


def _fallback(
    group: str,
    tokens: tuple[str, ...],
    description: str,
    input_schema: dict[str, Any] | None,
) -> Classification:
    if _looks_like_write(tokens, description, input_schema):
        return "unknown.write", True, "low", "fallback:unknown.write", True
    return "unknown.read", False, "low", "fallback:unknown.read", True


def classify(
    group: str,
    tool_name: str,
    description: str = "",
    input_schema: dict[str, Any] | None = None,
) -> ToolMetadata:
    """Return deterministic metadata for one public MCP tool.

    ``tool_name`` is the public name exposed to the model (``files__write_file``).
    """
    group = (group or "").strip().lower()
    tokens = _tokens(group, tool_name)

    result: Classification | None = None
    rules = _SIMPLE_GROUP_RULES.get(group)
    if group == "mail" and _is_scheduled_send(tokens):
        result = ("mail.send", True, "medium", "rule:mail.send:scheduled", False)
    elif rules is not None:
        matched = _match(rules, tokens)
        if matched is not None:
            rule, how = matched
            result = (rule.capability, rule.side_effect, rule.risk, f"rule:{rule.capability}:{how}", False)
    elif group == "git":
        result = _classify_git(tokens)
    elif group == "github":
        result = _classify_github(tokens)
    elif group in {"pc", "server"}:
        result = _classify_host(group, tokens)
    elif group in {"merchant", "buyer"}:
        result = _classify_commerce(group, tokens, description)

    if result is None:
        result = _fallback(group, tokens, description, input_schema)

    capability, side_effect, risk, basis, fallback = result
    side_effect = _read_side_effect(capability, side_effect, tokens)
    return _metadata(group, tool_name, capability, side_effect, risk, basis, fallback)
