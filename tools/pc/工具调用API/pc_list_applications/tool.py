from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_applications(query: str = '', installed_only: StrictBool = True, offset: StrictInt = 0, limit: StrictInt = 20):
        '搜索应用目录；默认只看已安装应用，可查询可安装版本和占用。'
        return store.pc_list_applications(query=query, installed_only=installed_only, offset=offset, limit=limit)
