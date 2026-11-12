from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_cache_locations():
        '列出可清理的登记缓存位置、实际文件数量和占用。'
        return store.pc_list_cache_locations()
