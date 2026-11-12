from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def search_repositories(query: str = "", offset: int = 0, limit: int = 20) -> dict:
        """按ID、名称、owner及描述的大小写不敏感子串查询本地仓库。"""
        return store.search_repositories(query, offset, limit)
