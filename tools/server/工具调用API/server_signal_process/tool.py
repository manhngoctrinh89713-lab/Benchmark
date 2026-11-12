from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_signal_process(pid: StrictInt, signal: Literal['TERM', 'KILL', 'STOP', 'CONT'] = 'TERM'):
        '向模拟进程发送TERM/KILL/STOP/CONT；主进程终止会使关联服务失败并写日志。'
        return store.server_signal_process(pid=pid, signal=signal)
