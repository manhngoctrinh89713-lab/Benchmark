from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_get_service(service_id: str):
        '读取服务启用/运行状态、主PID、依赖及磁盘配置与生效配置的哈希差异。'
        return store.server_get_service(service_id=service_id)
