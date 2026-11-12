from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def git_reset(repo_id: str) -> dict:
        """仅取消全部暂存，保留工作文件和提交；不提供hard reset。"""
        return store.git_reset(repo_id)
