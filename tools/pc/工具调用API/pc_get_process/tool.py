from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_get_process(pid: StrictInt):
        '读取指定场景PID的状态、应用关联、资源和打开文件；含已终止记录。'
        return store.pc_get_process(pid=pid)
