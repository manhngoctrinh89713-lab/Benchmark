from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def git_branches(repo_id: str) -> dict:
        """列出本地分支、SHA和当前分支。"""
        return store.git_branches(repo_id)
