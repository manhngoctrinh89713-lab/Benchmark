from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def pc_get_disk_usage():
        '按模拟卷统计系统基础占用、应用、真实场景文件和ZIP备份占用。'
        return store.pc_get_disk_usage()
