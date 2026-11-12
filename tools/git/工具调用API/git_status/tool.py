from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def git_status(repo_id: str) -> dict:
        """读取真实Git工作区和暂存区状态。"""
        return store.git_status(repo_id)
