from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def list_code_files(project_id: str, pattern: str = "*", offset: int = 0, limit: int = 50):
        '分页列出项目文件；pattern为区分大小写的相对路径glob，跳过Git、虚拟环境和依赖目录。'
        return store.list_code_files(project_id=project_id, pattern=pattern, offset=offset, limit=limit)
