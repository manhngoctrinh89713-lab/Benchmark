from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def search_content(query: str, path: str = ".", pattern: str = "*", case_sensitive: bool = False, offset: int = 0, limit: int = 20) -> dict:
        """递归搜索UTF-8文本正文的字面子串，返回路径、行号和匹配行。二进制或不能读取的文件在skipped中报告；Office/PDF请先转换为Markdown再搜索。匹配行最多返回2000字符。"""
        return store.search_content(query, path, pattern, case_sensitive, offset, limit)
