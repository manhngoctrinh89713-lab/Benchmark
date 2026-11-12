from typing import Any
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def rename_symbol(project_id: str, path: str, line: int, column: int, new_name: str, dry_run: bool = False):
        '仅Python：由Jedi计算项目内符号引用的跨文件重命名，先检查全部输出并检查语法，再作为一次修改发布；不重命名模块/文件。'
        return store.rename_symbol(project_id=project_id, path=path, line=line, column=column, new_name=new_name, dry_run=dry_run)
