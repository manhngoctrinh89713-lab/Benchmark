from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_list_services(state: Literal['active', 'inactive', 'failed', None] = None, query: str = '', offset: StrictInt = 0, limit: StrictInt = 20):
        '按active/inactive/failed和名称搜索本服务器的systemd服务。'
        return store.server_list_services(state=state, query=query, offset=offset, limit=limit)
