from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_repository(repo_id: str) -> dict:
        """读取仓库的平台元数据、可见性、默认分支和合并要求。"""
        return store.get_repository(repo_id)
