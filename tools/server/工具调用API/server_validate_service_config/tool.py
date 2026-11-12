from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_validate_service_config(service_id: str):
        '按场景声明的JSON/INI/ENV语法和必填字段规则校验真实配置；不运行服务二进制。'
        return store.server_validate_service_config(service_id=service_id)
