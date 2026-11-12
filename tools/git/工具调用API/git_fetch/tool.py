from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def git_fetch(repo_id: str, remote: str, branch: str | None = None, prune: bool = False) -> dict:
        """从本地模拟远程更新远程跟踪引用；prune 删除远程已不存在的引用。"""
        return store.git_fetch(repo_id, remote, branch, prune)
