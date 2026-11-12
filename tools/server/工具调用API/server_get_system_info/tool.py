from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_get_system_info():
        '读取模拟Linux系统、资源、磁盘及失败服务概况。'
        return store.server_get_system_info()
