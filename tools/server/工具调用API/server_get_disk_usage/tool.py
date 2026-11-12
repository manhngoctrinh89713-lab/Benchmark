from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_get_disk_usage():
        '读取模拟挂载点的基础、真实配置/日志/数据文件及备份占用。'
        return store.server_get_disk_usage()
