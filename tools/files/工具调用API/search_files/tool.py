from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def search_files(path: str = ".", pattern: str = "*", exclude_patterns: list[str] | None = None, offset: int = 0, limit: int = 100) -> dict:
        """递归按文件名或相对搜索起点的路径匹配glob；忽略大小写，支持*、?和字符组。*可跨目录分隔符，无特殊**语义。排除命中的目录不再遍历。"""
        return store.search_files(path, pattern, exclude_patterns, offset, limit)
