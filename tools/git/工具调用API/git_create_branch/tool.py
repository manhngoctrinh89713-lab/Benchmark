from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def git_create_branch(repo_id: str, branch: str, base: str = "HEAD") -> dict:
        """从已有提交创建本地分支，不切换。"""
        return store.git_create_branch(repo_id, branch, base)
