from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def git_checkout(repo_id: str, branch: str) -> dict:
        """切换已有本地分支，要求工作区和暂存区干净。"""
        return store.git_checkout(repo_id, branch)
