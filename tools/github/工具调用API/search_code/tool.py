from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def search_code(repo_id: str, query: str, ref: str | None = None, path_prefix: str = "", offset: int = 0, limit: int = 20) -> dict:
        """在指定提交版本的UTF-8代码中按字面子串搜索，返回文件、行号和文本；不是GitHub高级搜索语法。"""
        return store.search_code(repo_id, query, ref, path_prefix, offset, limit)
