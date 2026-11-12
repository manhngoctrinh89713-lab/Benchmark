from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_read_file(path: str):
        '读取登记挂载点内的UTF-8场景文件、大小和哈希；最多200000字节。'
        return store.server_read_file(path=path)
