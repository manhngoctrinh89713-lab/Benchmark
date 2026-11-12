from typing import Literal
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def git_remote(repo_id: str, operation: Literal['list', 'add', 'remove'] = 'list', name: str | None = None, url: str | None = None) -> dict:
        """列出、添加或移除本地模拟远程；只保存 URL 和引用，不联网。"""
        return store.git_remote(repo_id, operation, name, url)
