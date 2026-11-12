"""Structured, finite arguments shared by the MCP tools."""
from typing import Literal
from typing_extensions import Required, TypedDict
from pydantic import ConfigDict


class Condition(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")
    field: Literal["subject", "body", "from", "to", "cc", "bcc", "timestamp", "is_read",
                   "starred", "mailbox", "categories", "has_attachment", "attachment_name",
                   "size", "thread_id", "importance"]
    op: Literal["eq", "contains", "in", "lt", "lte", "gt", "gte", "exists"]
    value: str | int | bool | list[str | int | bool]


class DraftChanges(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    recipients: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    html: bool
    reply_to: list[str]
    from_address: str
    send_mode: Literal["send_as", "send_on_behalf"]


class RuleAction(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    type: Required[Literal["move", "mark_read", "star", "add_category", "trash", "forward"]]
    mailbox: str
    category_id: str
    recipients: list[str]
    value: bool
