from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_get_system_info():
        '读取场景Windows电脑的系统信息、内存、进程和磁盘概况。'
        return store.pc_get_system_info()
