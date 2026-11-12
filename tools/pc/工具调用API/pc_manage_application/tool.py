from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_manage_application(app_id: str, operation: Literal['install', 'update', 'uninstall'], version: str | None = None):
        '在本地状态中安装、更新或卸载登记应用；运行中应用须先退出，磁盘占用同步变化。'
        return store.pc_manage_application(app_id=app_id, operation=operation, version=version)
