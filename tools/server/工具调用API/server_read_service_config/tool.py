from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_read_service_config(service_id: str):
        '读取登记服务配置的真实UTF-8文本和SHA-256，不读取宿主机/etc。'
        return store.server_read_service_config(service_id=service_id)
