from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def list_projects():
        '查看本轮可操作的代码项目、真实根目录、结构分析和语义分析支持的语言。'
        return store.list_projects()
