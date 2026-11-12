from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def server_create_backup(paths: list[str], label: str, idempotency_key: str):
        '将登记备份范围内的服务配置或数据文件写入真实ZIP与清单。'
        return store.server_create_backup(paths=paths, label=label, idempotency_key=idempotency_key)
