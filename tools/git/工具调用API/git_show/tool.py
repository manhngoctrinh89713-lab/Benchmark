from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def git_show(repo_id: str, revision: str = "HEAD") -> dict:
        """查看指定提交内容及差异。"""
        return store.git_show(repo_id, revision)
