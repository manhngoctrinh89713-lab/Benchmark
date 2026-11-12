from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_change_service(service_id: str, operation: Literal['start', 'stop', 'restart', 'reload', 'enable', 'disable']):
        '模拟start/stop/restart/reload/enable/disable，联动进程和日志；启动校验配置及依赖。'
        return store.server_change_service(service_id=service_id, operation=operation)
