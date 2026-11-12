from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_change_process(pid: StrictInt, operation: Literal['terminate', 'suspend', 'resume']):
        '挂起、恢复或终止指定模拟进程；保护系统进程，不使用宿主机PID。'
        return store.pc_change_process(pid=pid, operation=operation)
