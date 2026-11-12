from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def git_commit(repo_id: str, message: str) -> dict:
        """提交暂存区，返回真实提交SHA；无暂存变化时报错，不自动暂存。"""
        return store.git_commit(repo_id, message)
