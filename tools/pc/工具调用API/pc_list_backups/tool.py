from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_backups(offset: StrictInt = 0, limit: StrictInt = 20):
        '分页列出当前电脑的备份记录及归档哈希。'
        return store.pc_list_backups(offset=offset, limit=limit)
