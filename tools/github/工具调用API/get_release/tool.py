from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_release(repo_id: str, tag: str) -> dict:
        """按tag读取本地模拟Release详情。"""
        return store.get_release(repo_id, tag)
