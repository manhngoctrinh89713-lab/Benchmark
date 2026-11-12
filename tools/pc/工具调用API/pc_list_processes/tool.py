from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_list_processes(query: str = '', sort_by: Literal['memory', 'cpu', 'pid'] = 'memory', offset: StrictInt = 0, limit: StrictInt = 20):
        '按名称搜索当前进程并按内存、CPU或PID排序；使用提取的上游进程过滤逻辑。'
        return store.pc_list_processes(query=query, sort_by=sort_by, offset=offset, limit=limit)
