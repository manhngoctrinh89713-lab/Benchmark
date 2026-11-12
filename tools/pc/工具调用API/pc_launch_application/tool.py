from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def pc_launch_application(app_id: str):
        '为已安装应用创建本地模拟进程；不执行其命令或程序。'
        return store.pc_launch_application(app_id=app_id)
