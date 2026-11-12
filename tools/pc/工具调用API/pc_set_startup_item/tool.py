from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def pc_set_startup_item(item_id: str, enabled: StrictBool):
        '启用或禁用登记启动项；不修改真实注册表或启动文件夹。'
        return store.pc_set_startup_item(item_id=item_id, enabled=enabled)
