from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_get_process(pid: StrictInt):
        '读取场景PID详情、服务关联及资源，包含已终止进程。'
        return store.server_get_process(pid=pid)
