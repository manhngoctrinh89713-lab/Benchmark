from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_list_backups(offset: StrictInt = 0, limit: StrictInt = 20):
        '分页列出当前服务器的本地备份记录。'
        return store.server_list_backups(offset=offset, limit=limit)
