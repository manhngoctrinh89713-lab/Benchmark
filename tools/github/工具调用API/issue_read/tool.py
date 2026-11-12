from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def issue_read(repo_id: str, number: int) -> dict:
        """读取Issue及评论。"""
        return store.issue_read(repo_id, number)
