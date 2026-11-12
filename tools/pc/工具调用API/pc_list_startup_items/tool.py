from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_startup_items(offset: StrictInt = 0, limit: StrictInt = 20):
        '列出模拟Windows开机启动项、来源、应用和启用状态。'
        return store.pc_list_startup_items(offset=offset, limit=limit)
