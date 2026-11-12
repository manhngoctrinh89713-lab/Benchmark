from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def get_diagnostics(project_id: str, path: str):
        '返回真实语法诊断。Python编译但不执行代码；其他支持语言使用Tree-sitter。不是类型检查、lint或测试结果。'
        return store.get_diagnostics(project_id=project_id, path=path)
