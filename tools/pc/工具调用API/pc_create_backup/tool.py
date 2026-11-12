from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def pc_create_backup(paths: list[str], label: str, idempotency_key: str):
        '将登记个人文件备份为真实ZIP及校验清单；支持幂等重试。'
        return store.pc_create_backup(paths=paths, label=label, idempotency_key=idempotency_key)
