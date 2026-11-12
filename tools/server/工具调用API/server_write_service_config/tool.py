from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_write_service_config(service_id: str, content: str, expected_sha256: str):
        '按原文件哈希保存待生效配置；允许先保存错误配置，校验及reload/restart另行调用。'
        return store.server_write_service_config(service_id=service_id, content=content, expected_sha256=expected_sha256)
