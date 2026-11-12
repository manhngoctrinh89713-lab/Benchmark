from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def git_log(repo_id: str, revision: str = "HEAD", limit: int = 20) -> dict:
        """读取提交历史，limit为1..100。"""
        return store.git_log(repo_id, revision, limit)
