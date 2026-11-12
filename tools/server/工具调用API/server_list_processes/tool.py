from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_list_processes(query: str = '', sort_by: Literal['memory', 'cpu', 'pid'] = 'memory', offset: StrictInt = 0, limit: StrictInt = 20):
        '搜索当前进程命令并排序；初始进程由提取的Linux MCP ps解析器读入。'
        return store.server_list_processes(query=query, sort_by=sort_by, offset=offset, limit=limit)
