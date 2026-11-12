from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_directory(path: str = ".", offset: int = 0, limit: int = 100) -> dict:
        """列出直接子项，目录优先、名称排序。path相对files根目录，支持offset分页，limit为1..100。返回名称、类型、大小、时间及文件SHA-256。"""
        return store.list_directory(path, offset, limit)
